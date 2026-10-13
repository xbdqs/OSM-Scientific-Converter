"""Audit actual OSM source layers after the reviewer road extraction.

Usage: python tools/round2_check_classification.py PATH_TO_PROJECT
This checks the classification DB; GeoPackage export needs further independent
OGR layer/geometry verification before any reviewer claim of correctness.
"""
import argparse
import json
import sqlite3
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("--required-layer", default="lines")
    parser.add_argument("--min-matches", type=int, default=1)
    args = parser.parse_args()
    summary = args.project / 'classification' / 'classification_summary.json'
    db = args.project / 'classification' / 'classification.sqlite'
    if not (summary.is_file() and db.is_file()):
        parser.error('classification summary or sqlite is missing')
    stats = json.loads(summary.read_text(encoding='utf-8'))
    with sqlite3.connect(db) as connection:
        observed = dict(connection.execute('SELECT source_layer, COUNT(*) FROM objects GROUP BY source_layer'))
        integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
    expected = stats.get('classification_scope', {}).get('source_layers', [])
    errors = []
    if stats.get('classification_scope', {}).get('restricted') is not True:
        errors.append('missing restricted scope in summary')
    if expected != [args.required_layer]:
        errors.append(f'expected only {args.required_layer}, recorded scope is {expected}')
    if any(layer != args.required_layer for layer in observed):
        errors.append(f'unexpected source layers in matched database: {observed}')
    if int(stats.get('counts', {}).get('matched_objects', 0)) < args.min_matches:
        errors.append(f'matched_objects below required minimum {args.min_matches}')
    if integrity != 'ok':
        errors.append(f'failed SQLite integrity check: {integrity}')
    result = {
        'status': 'PASS' if not errors else 'FAIL',
        'classification_source_layers': expected,
        'observed_source_layers': observed,
        'matched_objects': stats.get('counts', {}).get('matched_objects'),
        'sqlite_integrity_check': integrity,
        'errors': errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not errors else 2)


if __name__ == '__main__':
    main()
