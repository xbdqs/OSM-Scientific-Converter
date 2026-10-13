"""Run a *locally provided* benchmark command and record wall time/RSS.

The process tree is sampled every 0.2 s. Peak RSS is a sampled upper snapshot,
not a complete instantaneous maximum. The tool does not benchmark itself.
Run separate cases for comparable outputs and record input hashes separately.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', required=True)
    parser.add_argument('--out', type=Path, default=Path('round2_benchmark_logs'))
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('expected a command after --')
    args.out.mkdir(parents=True, exist_ok=True)
    if not all(c.isalnum() or c in '._-' for c in args.label):
        parser.error('label must only contain A-Z, a-z, numbers, dot, underscore or hyphen')
    stdout_path = args.out / (args.label + '.log')
    report_path = args.out / (args.label + '.json')
    start_utc = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    peak_rss = 0
    observations = 0
    code = None
    with stdout_path.open('w', encoding='utf-8', errors='replace') as handle:
        try:
            process = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT)
            root = psutil.Process(process.pid)
            while process.poll() is None:
                try:
                    members = [root, *root.children(recursive=True)]
                    mem = sum(p.memory_info().rss for p in members if p.is_running())
                    peak_rss = max(peak_rss, mem)
                    observations += 1
                except (psutil.Error, OSError):
                    pass
                time.sleep(0.2)
            code = process.wait()
        except OSError as error:
            handle.write(f'ERROR: could not start process: {error}\n')
            code = 127
    report = {
        'schema_version': '1.0', 'label': args.label,
        'command': command, 'started_utc': start_utc,
        'finished_utc': datetime.now(timezone.utc).isoformat(),
        'wall_seconds': round(time.perf_counter() - start, 3),
        'peak_sampled_process_tree_rss_bytes': peak_rss,
        'sampling_interval_seconds': 0.2,
        'rss_observations': observations, 'exit_code': code,
        'note': 'Scope includes main process and sampled children. Command may contain private local paths: do not publish raw logs without review.'
    }
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if code == 0 else 2


if __name__ == '__main__':
    sys.exit(main())
