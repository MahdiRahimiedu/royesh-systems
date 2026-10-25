"""Real HTTP requests against three apps, isolated file-backed SQLite databases per test."""
from contextlib import ExitStack
from importlib import import_module
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from shared.database import Base
from pathlib import Path
import json

ROUTE_CATALOG = {}
ROUTE_OBSERVATIONS = {}


@pytest.fixture
def clients(tmp_path, monkeypatch):
    monkeypatch.setenv('SEED_DEMO', 'true')
    modules = {service: import_module(f'services.{service}.app') for service in ('personnel', 'inventory', 'commerce')}
    result = {}
    with ExitStack() as stack:
        for service, module in modules.items():
            engine = create_engine(f'sqlite:///{(tmp_path / (service + ".db")).as_posix()}', connect_args={'check_same_thread': False, 'timeout': 30})
            @event.listens_for(engine, 'connect')
            def configure_sqlite(connection, _):
                connection.execute('PRAGMA foreign_keys=ON')
                connection.execute('PRAGMA journal_mode=WAL')
            sessions = sessionmaker(bind=engine, expire_on_commit=False)
            # create_app closes over its startup DB, so override startup by creating a fresh app with same routes.
            from shared.app import create_app
            fresh = create_app(service, module.app.title, Base, engine, sessions, module.seed)
            fresh.include_router(module.router)
            for path, operations in fresh.openapi()['paths'].items():
                for method in operations:
                    if method.upper() in ('GET', 'POST', 'PATCH', 'DELETE', 'PUT'):
                        ROUTE_CATALOG[f'{service} {method.upper()} {path}'] = True
            # Record route templates and status codes only, never payloads or credentials.
            @fresh.middleware('http')
            async def observe_route(request, call_next, service=service):
                response = await call_next(request)
                route = request.scope.get('route')
                if route:
                    key = f'{service} {request.method} {route.path}'
                    ROUTE_OBSERVATIONS.setdefault(key, set()).add(response.status_code)
                return response
            result[service] = stack.enter_context(TestClient(fresh))
        yield result
    for client in result.values():
        client.app.state.engine.dispose()


def pytest_sessionfinish(session, exitstatus):
    if ROUTE_CATALOG:
        target = Path(__file__).resolve().parents[1] / 'artifacts' / 'api-coverage.json'
        target.parent.mkdir(exist_ok=True)
        rows = [{'route': key, 'statuses': sorted(ROUTE_OBSERVATIONS.get(key, [])),
                 'success': any(200 <= value < 300 for value in ROUTE_OBSERVATIONS.get(key, []))}
                for key in sorted(ROUTE_CATALOG)]
        target.write_text(json.dumps({'exit_status': exitstatus, 'routes': rows}, indent=2), encoding='utf-8')


@pytest.fixture
def headers(clients):
    result = {}
    for service, client in clients.items():
        response = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'admin12345'})
        assert response.status_code == 200, response.text
        result[service] = {'Authorization': 'Bearer ' + response.json()['access_token']}
    return result


@pytest.fixture
def staff_headers(clients):
    result = {}
    for service, client in clients.items():
        response = client.post('/api/v1/auth/login', json={'username': 'staff', 'password': 'staff12345'})
        assert response.status_code == 200, response.text
        result[service] = {'Authorization': 'Bearer ' + response.json()['access_token']}
    return result
