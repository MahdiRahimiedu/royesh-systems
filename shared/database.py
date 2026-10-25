"""One database per service. SQLite needs no installation; DATABASE_URL selects PostgreSQL."""
import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from fastapi import Request


class Base(DeclarativeBase):
    pass


def make_database(service):
    data = Path(os.getenv('DATA_DIR', 'data'))
    data.mkdir(parents=True, exist_ok=True)
    url = os.getenv(f'{service.upper()}_DATABASE_URL') or os.getenv('DATABASE_URL') or f'sqlite:///{(data / (service + ".db")).as_posix()}'
    engine = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 30} if url.startswith('sqlite') else {}, pool_pre_ping=True)
    if url.startswith('sqlite'):
        @event.listens_for(engine, 'connect')
        def configure_sqlite(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA journal_mode=WAL')
    return engine, sessionmaker(bind=engine, expire_on_commit=False), Base


def get_db(request: Request):
    with request.app.state.SessionLocal() as db:
        try:
            yield db
        except Exception:
            db.rollback()
            raise
