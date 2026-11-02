"""Render an approved BSL diff review without modifying the bundled renderer.

Python 3.10+, Git. No external dependencies.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args()
    source = args.spec.resolve()
    target = args.out.resolve()
    runtime = Path(__file__).resolve().parents[1] / 'assets' / 'runtime'
    if target == source or target in runtime.iterdir():
        parser.error('output must not replace the spec or bundled runtime')
    if target.exists() and not args.overwrite:
        parser.error('output exists; use a new path or --overwrite')
    spec = json.loads(source.read_text(encoding='utf-8-sig'))
    if 'repo' not in spec:
        parser.error('spec requires repo')
    repo = Path(spec['repo']).expanduser()
    spec['repo'] = str((source.parent / repo).resolve() if not repo.is_absolute() else repo.resolve())
    # Keep the immutable renderer's default output inside a temporary workspace.
    # Publish only after both rendering and validation succeed.
    with tempfile.TemporaryDirectory(prefix='av-diff-review-') as folder:
        stage = Path(folder)
        spec['out'] = str(stage / 'review.html')
        normalized = stage / 'spec.json'
        normalized.write_text(json.dumps(spec, ensure_ascii=False), encoding='utf-8')
        subprocess.run([sys.executable, '-I', str(runtime / 'build-review.py'), str(normalized)], check=True)
        subprocess.run([sys.executable, '-I', str(runtime / 'check-review.py'), spec['out']], check=True)
        content = Path(spec['out']).read_bytes()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('wb' if args.overwrite else 'xb') as stream:
            stream.write(content)
    print(json.dumps({'output': str(target), 'bytes': len(content)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
