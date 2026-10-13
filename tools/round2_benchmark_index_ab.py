#!/usr/bin/env python3
"""Round-2 controlled paired benchmark: default vs deferred GeoPackage spatial index.

Run from v0.4.2.dev1 Windows project folder. Requires packaged
round2_ab_helpers.py alongside this file, plus psutil and GDAL env.
This benchmark never alters the converter code or the input PBF.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sqlite3
import statistics
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from round2_ab_helpers import (
    sha256, gpkg_overview, compare_ids_streaming, run_command, table_for_gpkg
)

EXPECTED_SNAPSHOT_SHA256 = 'e850eeafc2ec1d94d5b6014b89b923f239a95415e663301cbe21907fa805dfc8'
EXPECTED_SNAPSHOT_COUNT = 2067117


def save_json(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(path.suffix + '.partial')
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    tmp.replace(path)


def index_check(path: Path) -> dict:
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as conn:
        table = table_for_gpkg(conn).strip('"')
        rtree = 'rtree_' + table + '_geom'
        if not all(x.isalnum() or x == '_' for x in rtree):
            raise ValueError('Unexpected spatial index identifier')
        index_exists = conn.execute(
            'SELECT COUNT(*) FROM sqlite_master WHERE type=\'table\' AND name=?', (rtree,)
        ).fetchone()[0] == 1
        trigger_count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE ?",
            (rtree + '_%',)
        ).fetchone()[0]
        features = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        nonnull = conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE geom IS NOT NULL').fetchone()[0]
        indexed = conn.execute(f'SELECT COUNT(*) FROM "{rtree}"').fetchone()[0] if index_exists else None
        quick_check = conn.execute('PRAGMA quick_check(1)').fetchone()[0]
        return {
            'feature_rows': features, 'non_null_geometry_rows': nonnull,
            'rtree_exists': index_exists, 'rtree_rows': indexed,
            'trigger_count': trigger_count, 'sqlite_quick_check': quick_check,
            'pass': bool(index_exists and trigger_count >= 3 and indexed == nonnull
                         and nonnull == features and quick_check == 'ok')
        }


def sample_geometry_binary_hashes(path: Path, limit: int = 32) -> dict[str, str]:
    # Deterministic spread of FIDs; avoids sorting 2 million geometry blobs.
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as conn:
        table = table_for_gpkg(conn)
        maximum_fid = conn.execute(f'SELECT MAX(fid) FROM {table}').fetchone()[0] or 0
        if not maximum_fid:
            return {}
        selected = sorted({1 + (maximum_fid - 1) * i // max(limit - 1, 1)
                           for i in range(limit)})
        placeholders = ','.join('?' for _ in selected)
        rows = conn.execute(
            f'SELECT canonical_osm_id, geom FROM {table} '
            f'WHERE fid IN ({placeholders}) ORDER BY fid', selected
        ).fetchall()
        return {str(k): hashlib.sha256(bytes(geom)).hexdigest() for k, geom in rows if geom}


def validate_run(path: Path, audit_path: Path, *, mode: str, digest: str, profile_hash: str) -> dict:
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    overview = gpkg_overview(path, targeted=True)
    idx = index_check(path)
    expected_mode = 'deferred_then_created' if mode == 'deferred' else 'default_gdal_creation'
    true_flag = mode == 'deferred'
    issues = []
    if audit.get('status') != 'success': issues.append('audit status not success')
    if audit.get('input_sha256') != digest: issues.append('input SHA-256 differs')
    if audit.get('profile_sha256') != profile_hash: issues.append('profile SHA-256 differs')
    if audit.get('experimental_deferred_index') is not true_flag:
        issues.append('experimental flag did not propagate')
    if audit.get('spatial_index', {}).get('mode') != expected_mode:
        issues.append('spatial index mode unexpected')
    if audit.get('feature_count') != overview['count']:
        issues.append('feature_count != GPKG row count')
    if overview['null_geometry_count'] != 0: issues.append('null geometries present')
    if overview['invalid_targeted_provenance_rows'] != 0:
        issues.append('invalid provenance detected')
    if [tuple(row) for row in overview['declared_geometry_and_srs']] != [('LINESTRING', 4326)]:
        issues.append('expected exactly one LINESTRING EPSG:4326 geometry column')
    if not idx['pass']: issues.append('GeoPackage RTree/trigger/quick_check validation failed')
    if digest == EXPECTED_SNAPSHOT_SHA256 and overview['count'] != EXPECTED_SNAPSHOT_COUNT:
        issues.append('unexpected feature count for recorded fixed snapshot')
    return {
        'audit_feature_count': audit.get('feature_count'),
        'matched_id_sha256': audit.get('matched_id_sha256'),
        'category_counts': overview['category_counts'],
        'overview': overview, 'spatial_index': idx,
        'internal_stage_seconds': audit.get('timings_seconds', {}),
        'validation_status': 'PASS' if not issues else 'CHECK',
        'validation_issues': issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pbf', type=Path, required=True)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--out', type=Path, default=None)
    parser.add_argument('--repeats', type=int, default=1, choices=[1, 2, 3, 4])
    args = parser.parse_args()
    repo, pbf = args.repo.resolve(), args.pbf.resolve()
    dest = (args.out or repo / 'round2_deferred_index_ab').resolve()
    rules = repo / 'examples' / 'round2_road_extraction_rules.json'
    if not pbf.is_file(): parser.error(f'PBF file not found: {pbf}')
    if not rules.is_file(): parser.error(f'Rules not found: {rules}')
    if dest.exists(): parser.error(f'Result directory exists; pass a NEW --out path: {dest}')
    import psutil
    free = psutil.disk_usage(str(dest.parent)).free / 2**30
    if free < 12: parser.error('At least 12 GiB of free space is recommended before starting')
    dest.mkdir(parents=True, exist_ok=False)
    print('Input:', pbf, flush=True)
    print('Computing SHA-256 before timed runs...', flush=True)
    digest, profile_hash = sha256(pbf), sha256(rules)
    print('SHA-256:', digest, flush=True)
    report = {
        'experiment': 'round2_default_vs_deferred_spatial_index_paired',
        'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'input_file': pbf.name, 'input_size_bytes': pbf.stat().st_size,
        'input_sha256': digest, 'rules_sha256': profile_hash,
        'machine': {'platform': platform.platform(), 'processor': platform.processor(),
                    'logical_cpu_count': os.cpu_count(), 'ram_gib': round(psutil.virtual_memory().total/2**30,2),
                    'python': sys.version.split()[0], 'free_disk_gib_before': round(free, 2)},
        'design': ['Same input file, exact highway whitelist, same converter build and GeoPackage format.',
                   'Only treatment difference: experimental deferred spatial index on/off.',
                   'Order alternates between repeated pairs; cache/temperature effects are not eliminated.',
                   'External wall time includes staging/copy; process-tree RSS is sampled every 0.2 s.',
                   'Integrity and ID validation run after timed commands.',
                   'No assertion of full geometry equivalence; representative GPKG binary geometries sampled.',
                   'Do not compare internal total_end_to_end with external wall time; internal timing excludes final copying.'],
        'runs': []
    }
    summary_path = dest / 'summary.json'
    save_json(summary_path, report)
    for i in range(1, args.repeats+1):
        out_dir = dest / f'pair_{i:02d}'
        out_dir.mkdir()
        order = ['default', 'deferred'] if i % 2 else ['deferred', 'default']
        rec = {'pair': i, 'order': order, 'variants': {}}
        for label in order:
            outgpkg = out_dir / f'{label}_roads.gpkg'
            command = ['osm-sci', 'quick-extract', str(pbf), '--rules', str(rules),
                       '--output', str(outgpkg)]
            if label == 'deferred': command.append('--experimental-deferred-index')
            print(f'Pair {i} [{label}] running...', flush=True)
            timing = run_command(command, out_dir / label)
            result = {'timing': timing, 'gpkg_filename': outgpkg.name,
                      'audit_filename': outgpkg.name + '.audit.json'}
            rec['variants'][label] = result
            auditpath = Path(str(outgpkg) + '.audit.json')
            if timing['returncode'] != 0 or not outgpkg.is_file() or not auditpath.is_file():
                result['validation_status'] = 'FAILED'
                rec['status'] = 'FAILED'
                report['runs'].append(rec); save_json(summary_path, report)
                print(f'FAILED; inspect {out_dir / label}.stderr.txt; preserved completed outputs', flush=True)
                return 2
            try:
                result['validation'] = validate_run(
                    outgpkg, auditpath, mode=label, digest=digest, profile_hash=profile_hash
                )
                result['validation_status'] = result['validation']['validation_status']
            except Exception as exc:
                result['validation_status'] = 'CHECK'
                result['error'] = f'{type(exc).__name__}: {exc}'
            print(f'Pair {i} [{label}] wall={timing["wall_seconds"]:.3f}s, '
                  f'validation={result["validation_status"]}', flush=True)
            if result['validation_status'] != 'PASS':
                rec['status'] = 'CHECK'; report['runs'].append(rec); save_json(summary_path, report)
                print('STOP: validation did not pass; do not use timing for conclusions.', flush=True)
                return 2
        try:
            default = out_dir / 'default_roads.gpkg'
            deferred = out_dir / 'deferred_roads.gpkg'
            rec['id_comparison'] = compare_ids_streaming(default, deferred)
            rec['sampled_geometry_blob_equal'] = (
                sample_geometry_binary_hashes(default) == sample_geometry_binary_hashes(deferred))
            a = rec['variants']['default']['validation']
            b = rec['variants']['deferred']['validation']
            rec['status'] = ('PASS' if rec['id_comparison']['canonical_id_multisets_equal']
                             and rec['sampled_geometry_blob_equal']
                             and a['audit_feature_count'] == b['audit_feature_count']
                             and a['matched_id_sha256'] == b['matched_id_sha256']
                             and a['category_counts'] == b['category_counts'] else 'CHECK')
        except Exception as exc:
            rec['status'] = 'CHECK'; rec['comparison_error'] = f'{type(exc).__name__}: {exc}'
        rec['default_minus_deferred_seconds'] = round(
            rec['variants']['default']['timing']['wall_seconds'] -
            rec['variants']['deferred']['timing']['wall_seconds'], 3)
        report['runs'].append(rec)
        save_json(summary_path, report)
        print(f'Pair {i} result: {rec["status"]}; default - deferred = '
              f'{rec["default_minus_deferred_seconds"]:+.3f}s', flush=True)
        if rec['status'] != 'PASS': return 2
    times_a = [r['variants']['default']['timing']['wall_seconds'] for r in report['runs']]
    times_b = [r['variants']['deferred']['timing']['wall_seconds'] for r in report['runs']]
    report['descriptive_comparison'] = {
        'completed_pairs': len(times_a),
        'default_median_seconds': round(statistics.median(times_a), 3),
        'deferred_median_seconds': round(statistics.median(times_b), 3),
        'default_minus_deferred_paired_differences_seconds':
            [r['default_minus_deferred_seconds'] for r in report['runs']],
        'note': 'Descriptive only; especially with <3 pairs do not claim statistically stable speedup.'
    }
    save_json(summary_path, report)
    print('Complete:', summary_path, flush=True)
    print('Upload summary.json and the audit JSON from pair_01; retain GPKG locally.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
