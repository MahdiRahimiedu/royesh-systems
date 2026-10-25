from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select
from shared.auth import AuthSession, User, hash_password
from shared.models import utcnow

API = '/api/v1'


def test_admin_user_management_search_deactivation_and_audit(clients, headers):
    for service, c in clients.items():
        h = headers[service]
        body = {'username': 'audituser', 'full_name': 'کاربر ممیزی', 'password': 'Strong-Password-2026', 'role': 'staff'}
        created = c.post(API + '/users', headers=h, json=body)
        assert created.status_code == 201, created.text
        row = created.json()
        assert 'password_hash' not in row
        assert c.post(API + '/users', headers=h, json=body).status_code == 409
        assert c.get(API + '/users?q=ممیزی', headers=h).json()['total'] == 1
        token = c.post(API + '/auth/login', json={'username': 'audituser', 'password': body['password']}).json()['access_token']
        account = {'Authorization': 'Bearer ' + token}
        assert c.get(API + '/users', headers=account).status_code == 403
        assert c.patch(API + '/users/' + row['id'], headers=h, json={'role': 'manager', 'full_name': 'کارشناس ممیزی'}).status_code == 200
        assert c.get(API + '/auth/me', headers=account).json()['role'] == 'manager'
        assert c.patch(API + '/users/' + row['id'], headers=h, json={'is_active': False}).status_code == 200
        assert c.get(API + '/auth/me', headers=account).status_code == 401
        assert c.post(API + '/auth/login', json={'username': 'audituser', 'password': body['password']}).status_code == 401
        assert c.get(API + '/audit-logs?q=' + row['id'], headers=h).json()['total'] >= 3


def test_password_whitespace_preserved_and_revoked_token(clients, headers):
    c, h = clients['personnel'], headers['personnel']
    password = '  Exact-Password-2026  '
    created = c.post(API + '/users', headers=h, json={'username': 'spaces', 'full_name': 'کاربر آزمون', 'password': password})
    assert created.status_code == 201, created.text
    assert c.post(API + '/auth/login', json={'username': 'spaces', 'password': password.strip()}).status_code == 401
    login = c.post(API + '/auth/login', json={'username': 'spaces', 'password': password})
    assert login.status_code == 200
    account = {'Authorization': 'Bearer ' + login.json()['access_token']}
    new_password = ' Another-Exact-Password-2026 '
    assert c.post(API + '/auth/change-password', headers=account, json={'current_password': password, 'new_password': new_password}).status_code == 200
    assert c.get(API + '/auth/me', headers=account).status_code == 401
    assert c.post(API + '/auth/login', json={'username': 'spaces', 'password': new_password}).status_code == 200


def test_link_validation_and_role_escalation_rejection(clients, headers, staff_headers):
    c, h = clients['personnel'], headers['personnel']
    payload = {'username': 'linked', 'full_name': 'کاربر مرتبط', 'password': 'Password-2026'}
    assert c.post(API + '/users', headers=h, json={**payload, 'employee_id': 'EMP-001'}).status_code == 422
    assert c.post(API + '/users', headers=h, json={**payload, 'employee_id': str(uuid4())}).status_code == 422
    employee_id = c.get(API + '/auth/me', headers=staff_headers['personnel']).json()['employee_id']
    assert c.post(API + '/users', headers=h, json={**payload, 'employee_id': employee_id}).status_code == 201
    assert c.post(API + '/users', headers=staff_headers['personnel'], json={**payload, 'username': 'escalated', 'role': 'admin'}).status_code == 403


def test_expiry_rate_limit_and_cors(clients, headers):
    c, h = clients['personnel'], headers['personnel']
    with c.app.state.SessionLocal() as db:
        session = db.scalar(select(AuthSession))
        session.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert c.get(API + '/auth/me', headers=h).status_code == 401
    for _ in range(9):
        assert c.post(API + '/auth/login', json={'username': 'unknown', 'password': 'wrong'}).status_code == 401
    assert c.post(API + '/auth/login', json={'username': 'unknown', 'password': 'wrong'}).status_code == 429
    allowed = c.options(API + '/employees', headers={'Origin': 'http://localhost:3001', 'Access-Control-Request-Method': 'GET', 'Access-Control-Request-Headers': 'authorization'})
    assert allowed.headers['access-control-allow-origin'] == 'http://localhost:3001'
    denied = c.options(API + '/employees', headers={'Origin': 'https://unapproved.example', 'Access-Control-Request-Method': 'GET'})
    assert 'access-control-allow-origin' not in denied.headers
