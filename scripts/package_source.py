"""Portable source package without credentials, local databases or installed dependencies."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parents[1]
target = root / 'artifacts' / 'royesh-source.zip'
target.parent.mkdir(exist_ok=True)
excluded = {'.git', '.venv', 'node_modules', 'data', '.runtime', 'artifacts', '__pycache__', '.pytest_cache'}
with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
    for path in root.rglob('*'):
        relative = path.relative_to(root)
        if any(part in excluded or part.startswith('.next') for part in relative.parts):
            continue
        if (not path.is_file() or path.is_symlink()
                or (path.name.startswith('.env') and path.name != '.env.example')
                or path.name.endswith('.local') or path.suffix in {'.pyc', '.tsbuildinfo'}):
            continue
        archive.write(path, Path('royesh') / relative)
print(target)
