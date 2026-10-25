"""Consistent online SQLite snapshots, no destructive operations."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from manage import environment

root = Path(__file__).resolve().parents[1]
env = environment()
data = Path(env.get('DATA_DIR', 'data'))
if not data.is_absolute():
    data = root / data
target = root / 'artifacts' / 'backups' / datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
target.mkdir(parents=True, exist_ok=False)
for service in ('personnel', 'inventory', 'commerce'):
    configured_url = env.get(f'{service.upper()}_DATABASE_URL') or env.get('DATABASE_URL')
    if configured_url:
        print(f'{service}: explicit DATABASE_URL configured; use its database backup tool (pg_dump for PostgreSQL). No local SQLite copy claimed.')
        continue
    source = data / f'{service}.db'
    if source.exists():
        with sqlite3.connect(f'file:{source.as_posix()}?mode=ro', uri=True) as connection:
            with sqlite3.connect(target / source.name) as destination:
                connection.backup(destination)
        print(f'Backed up {service}: {target / source.name}')
