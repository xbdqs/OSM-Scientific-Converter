#!/usr/bin/env python3
"""Round-2 reproducible comparison of targeted extraction with minimal GDAL baseline.

Run from the OSM Scientific Converter v0.4.2.dev1 Windows development project:
  python tools/round2_run_brazil_benchmark.py --pbf D:\\OSM\\data\\sudeste-260901.osm.pbf

Does NOT claim equal processing workloads. Does not download inputs or modify software.
Requires psutil (already a converter dependency). Never sends data externally.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import os
import platform
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone

try:
    import psutil
except ImportError:
    raise SystemExit('Please install psutil in the active environment')


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def table_for_gpkg(db):
    tables = db.execute("SELECT table_name FROM gpkg_contents WHERE data_type='features'").fetchall()
    if len(tables) != 1:
        raise ValueError(f'Expected exactly one feature layer, found: {tables}')
    name = tables[0][0]
    if '"' in name:
        raise ValueError('Unexpected quoted table name')
    return '"' + name + '"'


def gpkg_overview(path, *, targeted):
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        tbl = table_for_gpkg(db)
        names = {a[1] for a in db.execute(f'PRAGMA table_info({tbl})')}
        expected = {'osm_id', 'geom'} | ({'canonical_osm_id', 'source_layer', 'category', 'profile_sha256'} if targeted else set())
        missing = expected - names
        if missing:
            raise ValueError(f'Missing expected fields in {path.name}: {missing}')
        count = db.execute(f'SELECT COUNT(*) FROM {tbl}').fetchone()[0]
        null_geom = db.execute(f'SELECT COUNT(*) FROM {tbl} WHERE geom IS NULL').fetchone()[0]
        layer = db.execute('SELECT geometry_type_name,srs_id FROM gpkg_geometry_columns').fetchall()
        invalid_provenance = None
        categories = {}
        if targeted:
            invalid_provenance = db.execute(
                f"SELECT COUNT(*) FROM {tbl} WHERE source_layer != 'lines' OR osm_type != 'way' "
                "OR canonical_osm_id != ('way/' || CAST(osm_id AS TEXT)) "
                "OR canonical_osm_id IS NULL OR category IS NULL OR profile_sha256 IS NULL"
            ).fetchone()[0]
            categories = dict(db.execute(f'SELECT category, COUNT(*) FROM {tbl} GROUP BY category'))
        return {'count': count, 'null_geometry_count': null_geom,
                'declared_geometry_and_srs': layer, 'invalid_targeted_provenance_rows': invalid_provenance,
                'category_counts': categories}
    finally:
        db.close()


def compare_ids_streaming(a_path, b_path):
    """OSM IDs sorted in SQLite TEMP storage; avoids Python set of millions of IDs."""
    a = sqlite3.connect(a_path.as_uri() + '?mode=ro', uri=True)
    b = sqlite3.connect(b_path.as_uri() + '?mode=ro', uri=True)
    try:
        a.execute('PRAGMA temp_store=FILE'); b.execute('PRAGMA temp_store=FILE')
        ta, tb = table_for_gpkg(a), table_for_gpkg(b)
        cur_a = a.execute(f'SELECT canonical_osm_id FROM {ta} ORDER BY canonical_osm_id')
        cur_b = b.execute(f"SELECT 'way/' || CAST(osm_id AS TEXT) AS canonical FROM {tb} ORDER BY canonical")
        differing = 0
        sample = []
        count = 0
        for aa, bb in itertools.zip_longest(cur_a, cur_b):
            count += 1
            ia = aa[0] if aa is not None else None
            ib = bb[0] if bb is not None else None
            if ia != ib:
                differing += 1
                if len(sample) < 10:
                    sample.append({'converter': ia, 'gdal': ib})
        return {'canonical_id_multisets_equal': differing == 0,
                'rows_compared': count, 'different_sorted_positions': differing,
                'difference_sample': sample,
                'scope': 'canonical ID multiset only; not geometry/attributes/quality-audit equivalence'}
    finally:
        a.close(); b.close()


def process_tree_rss(pid):
    try:
        main = psutil.Process(pid)
        procs = [main] + main.children(recursive=True)
        total = 0
        for proc in procs:
            try:
                total += proc.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return total
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return 0


def run_command(command, logbase):
    started = time.perf_counter()
    peak_rss = 0
    with (logbase.with_suffix('.stdout.txt')).open('w', encoding='utf-8') as out, \
         (logbase.with_suffix('.stderr.txt')).open('w', encoding='utf-8') as err:
        proc = subprocess.Popen(command, stdout=out, stderr=err)
        while proc.poll() is None:
            peak_rss = max(peak_rss, process_tree_rss(proc.pid))
            time.sleep(.2)
        code = proc.wait()
    return {'returncode': code, 'wall_seconds': round(time.perf_counter() - started, 3),
            'sampled_peak_process_tree_rss_mib': round(peak_rss / 1024**2, 1),
            'note': 'RSS sampled every 0.2 s; a short-lived peak may be missed. Includes child GDAL process when observed.'}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--pbf', type=Path, required=True, help='Fixed, local OSM PBF file')
    cli.add_argument('--repo', type=Path, default=Path.cwd(), help='v0.4.2.dev1 project root')
    cli.add_argument('--out', type=Path, default=None, help='New benchmark results directory')
    cli.add_argument('--repeats', type=int, default=1, help='Start with 1; use 3 only after initial success')
    args = cli.parse_args()
    root = args.repo.resolve(); pbf = args.pbf.resolve()
    dest = (args.out or root / 'round2_brazil_benchmark').resolve()
    if not pbf.is_file(): cli.error('PBF file does not exist')
    if pbf.suffix.lower() != '.pbf': cli.error('Expected local .pbf file')
    if args.repeats not in (1, 2, 3): cli.error('--repeats must be 1, 2, or 3')
    if dest.exists(): cli.error(f'Output folder already exists: {dest} (choose --out)')
    rules = root/'examples/round2_road_extraction_rules.json'
    config = root/'src/osm_scientific_converter/resources/osmconf.ini'
    baseline = root/'tools/round2_direct_gdal_baseline.py'
    for path in (rules, config, baseline):
        if not path.is_file(): cli.error(f'Required project file missing: {path}')
    dest.mkdir(parents=True)
    total, used, free = psutil.disk_usage(str(dest)).total, psutil.disk_usage(str(dest)).used, psutil.disk_usage(str(dest)).free
    print('Input:', pbf.name, f'({pbf.stat().st_size / 2**20:.1f} MiB)')
    print('Computing input SHA-256 (outside timed runs)...', flush=True)
    digest = sha256(pbf)
    print('Input SHA-256:', digest, flush=True)
    report = {
        'experiment': 'round2_sudeste_targeted_vs_direct_gdal_minimal',
        'experiment_started_utc': datetime.now(timezone.utc).isoformat(),
        'input_name': pbf.name, 'input_size_bytes': pbf.stat().st_size,
        'input_sha256': digest, 'rules_sha256': sha256(rules),
        'software_version_expected': '0.4.2.dev1',
        'machine': {'os': platform.platform(), 'cpu': platform.processor(),
                    'logical_cpu_count': os.cpu_count(),
                    'ram_gib': round(psutil.virtual_memory().total / 1024**3, 2),
                    'python': sys.version.split()[0],
                    'free_disk_gib_before': round(free/1024**3, 2)},
        'design_notes': [
            'Same fixed PBF, same 13 highway values, exact lines source layer, same GeoPackage output format.',
            'Direct GDAL baseline does not do category/provenance enrichment, input-hash binding or full inventory.',
            'Targeted mode has no full vocabulary inventory or complete pre-export quality audit.',
            'Timed runs include file hashing performed by each workflow; initial experiment hash is excluded.',
            'Order alternates to expose warm-cache/order effects; sample RSS is approximate.',
            'No evidence this is the same exact PBF as used by the reviewer without review input SHA-256.'
        ],
        'runs': []
    }
    (dest/'summary.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    for n in range(1, args.repeats + 1):
        run_folder = dest/f'run_{n:02d}'
        run_folder.mkdir()
        # Alternate command order to mitigate caching effects, not a cold-cache control.
        order = ('gdal', 'targeted') if n % 2 == 1 else ('targeted', 'gdal')
        record = {'run_index': n, 'run_order': list(order)}
        path_quick = run_folder/'targeted_roads.gpkg'
        path_gdal = run_folder/'gdal_baseline.gpkg'
        for label in order:
            if label == 'targeted':
                command = ['osm-sci', 'quick-extract', str(pbf), '--rules', str(rules), '--output', str(path_quick)]
                result = run_command(command, run_folder/'targeted')
                auditpath = path_quick.with_name(path_quick.name + '.audit.json')
                if auditpath.is_file():
                    audit = json.loads(auditpath.read_text(encoding='utf-8'))
                    result['audit_status'] = audit.get('status')
                    result['audit_counts'] = audit.get('feature_count')
                    result['internal_timings_seconds'] = audit.get('timings_seconds', {})
                    result['audit_sha256_matches_input'] = audit.get('input_sha256') == digest
                    result['audit_profile_sha256'] = audit.get('profile_sha256')
            else:
                command = [sys.executable, str(baseline), '--input', str(pbf), '--rules', str(rules),
                           '--base-config', str(config), '--output', str(path_gdal),
                           '--report', str(run_folder/'gdal_report.json')]
                result = run_command(command, run_folder/'gdal')
                gdal_report = run_folder/'gdal_report.json'
                if gdal_report.is_file():
                    contents = json.loads(gdal_report.read_text(encoding='utf-8'))
                    result['gdal_report_exit_code'] = contents.get('exit_code')
                    result['input_hash_matches'] = contents.get('input_sha256') == digest
            record[label] = result
            print(f'Run {n} [{label}]: {result["wall_seconds"]} s, exit={result["returncode"]}', flush=True)
            if result['returncode'] != 0:
                record['status'] = 'FAILED'
                report['runs'].append(record)
                (dest/'summary.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
                raise SystemExit(f'Workflow failed. See log: {run_folder / label}.stderr.txt')
        try:
            record['targeted_gpkg'] = gpkg_overview(path_quick, targeted=True)
            record['gdal_gpkg'] = gpkg_overview(path_gdal, targeted=False)
            record['identity_comparison'] = compare_ids_streaming(path_quick, path_gdal)
            rec_a, rec_b = record['targeted_gpkg'], record['gdal_gpkg']
            rec_c = record['identity_comparison']
            record['status'] = ('PASS' if rec_c['canonical_id_multisets_equal']
                                and rec_a['count'] == rec_b['count']
                                and rec_a['null_geometry_count'] == 0
                                and rec_b['null_geometry_count'] == 0
                                and rec_a['invalid_targeted_provenance_rows'] == 0
                                and record['targeted'].get('audit_sha256_matches_input')
                                and record['gdal'].get('input_hash_matches') else 'CHECK')
        except Exception as exc:
            record['status'] = 'CHECK'
            record['comparison_error'] = f'{type(exc).__name__}: {exc}'
        report['runs'].append(record)
        (dest/'summary.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print('Count and canonical-ID comparison:', record['status'], flush=True)
    print('Results:', dest/'summary.json')
    print('Do not upload large GeoPackages; upload summary.json and both *.audit.json / gdal_report.json if requested.')
    if any(r['status'] != 'PASS' for r in report['runs']):
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
