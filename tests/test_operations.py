"""Data safety of export/backup and a clean non-demo deployment bootstrap."""
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from zipfile import ZipFile
import pytest

ROOT = Path(__file__).resolve().parents[1]


def copy_script(tmp_path, name):
    scripts = tmp_path / 'scripts'
    scripts.mkdir(exist_ok=True)
    shutil.copyfile(ROOT / 'scripts' / name, scripts / name)
    return scripts / name


def test_source_archive_excludes_all_environment_secrets_and_runtime_data(tmp_path):
    script = copy_script(tmp_path, 'package_source.py')
    for name in ('.env', '.env.production', '.env.staging', '.env.local'):
        (tmp_path / name).write_text('SECRET=do-not-package', encoding='utf-8')
    (tmp_path / '.env.example').write_text('SEED_DEMO=true', encoding='utf-8')
    (tmp_path / 'README.md').write_text('public documentation', encoding='utf-8')
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data' / 'private.db').write_bytes(b'private')
    subprocess.run([sys.executable, str(script)], check=True, capture_output=True)
    with ZipFile(tmp_path / 'artifacts' / 'royesh-source.zip') as archive:
        names = archive.namelist()
        assert 'royesh/.env.example' in names
        assert 'royesh/README.md' in names
        assert not any('private.db' in name or name.endswith(('.env', '.env.production', '.env.staging', '.env.local')) for name in names)


def test_backup_honors_custom_data_directory_and_has_valid_sqlite_snapshot(tmp_path):
    script = copy_script(tmp_path, 'backup.py')
    copy_script(tmp_path, 'manage.py')
    data = tmp_path / 'custom data'
    data.mkdir()
    with sqlite3.connect(data / 'personnel.db') as db:
        db.execute('CREATE TABLE example (value INTEGER)')
        db.execute('INSERT INTO example VALUES (7)')
    env = os.environ.copy()
    env['DATA_DIR'] = str(data)
    for key in ('DATABASE_URL', 'PERSONNEL_DATABASE_URL', 'INVENTORY_DATABASE_URL', 'COMMERCE_DATABASE_URL'):
        env.pop(key, None)
    subprocess.run([sys.executable, str(script)], env=env, check=True, capture_output=True)
    backups = list((tmp_path / 'artifacts' / 'backups').glob('*/personnel.db'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('SELECT value FROM example').fetchone()[0] == 7


def test_production_bootstrap_requires_secret_and_does_not_create_demo_users(tmp_path, monkeypatch):
    from importlib import import_module
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from shared.app import create_app
    from shared.database import Base
    module = import_module('services.personnel.app')
    engine = create_engine(f'sqlite:///{(tmp_path / "production.db").as_posix()}', connect_args={'check_same_thread': False})
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setenv('SEED_DEMO', 'false')
    monkeypatch.delenv('ADMIN_PASSWORD', raising=False)
    app = create_app('personnel', 'Production test', Base, engine, sessions, module.seed)
    with pytest.raises(RuntimeError, match='ADMIN_PASSWORD'):
        with TestClient(app):
            pass
    monkeypatch.setenv('ADMIN_PASSWORD', 'Private-admin-password-2026')
    app = create_app('personnel', 'Production test', Base, engine, sessions, module.seed)
    app.include_router(module.router)
    with TestClient(app) as c:
        assert c.get('/health').json()['demo'] is False
        assert c.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'admin12345'}).status_code == 401
        login = c.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'Private-admin-password-2026'})
        assert login.status_code == 200
        h = {'Authorization': 'Bearer ' + login.json()['access_token']}
        assert c.get('/api/v1/users', headers=h).json()['total'] == 1
        assert c.get('/api/v1/employees', headers=h).json()['total'] == 0
    engine.dispose()


def test_business_date_uses_company_timezone_at_midnight(monkeypatch):
    from datetime import datetime, timezone, date
    import shared.models as clock
    monkeypatch.setattr(clock, 'utcnow', lambda: datetime(2026, 10, 23, 21, 0, tzinfo=timezone.utc))
    monkeypatch.setenv('BUSINESS_TIMEZONE', 'Asia/Tehran')
    assert clock.business_today() == date(2026, 10, 24)
    monkeypatch.setenv('BUSINESS_TIMEZONE', 'UTC')
    assert clock.business_today() == date(2026, 10, 23)
