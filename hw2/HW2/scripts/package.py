#!/usr/bin/env python3
"""Create a self-contained submission without hidden workspace metadata."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import json

ROOT = Path(__file__).resolve().parents[1]


def main():
    for mode in ['ecmp', 'packet', 'flowlet']:
        s = json.loads((ROOT/'results'/mode/'summary.json').read_text())
        if not all(s['checks'].values()):
            raise ValueError(f'Cannot package failed {mode} results')
    files = [ROOT/name for name in ['Makefile', 'README.md', 'topology.json', 'report.pdf',
             'report.md', 'run_milestone1.sh', 'run_milestone2.sh', 'run_milestone3.sh']]
    for directory in ['p4', 'scripts', 'tests', 'commands', 'results', 'build']:
        files.extend(p for p in (ROOT/directory).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts
                     and p.name not in ['ready', 'stop'])
    path = ROOT/'HW2-submission.zip'
    with ZipFile(path, 'w', ZIP_DEFLATED) as z:
        for file in sorted(files):
            z.write(file, Path('HW2')/file.relative_to(ROOT))
    with ZipFile(path) as z:
        if z.testzip() is not None:
            raise ValueError('ZIP integrity check failed')
    print(f'Created {path.name}: {len(files)} files, {path.stat().st_size:,} bytes')


if __name__ == '__main__':
    main()
