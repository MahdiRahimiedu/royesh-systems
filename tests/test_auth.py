def test_auth_revocation_and_access_control(clients, headers, staff_headers):
    for service, c in clients.items():
        assert c.get('/api/v1/dashboard').status_code == 401
        assert c.get('/api/v1/users', headers=staff_headers[service]).status_code == 403
        assert c.get('/api/v1/users', headers=headers[service]).status_code == 200
        for user in c.get('/api/v1/users', headers=headers[service]).json()['items']:
            assert 'password_hash' not in user
        assert c.post('/api/v1/auth/logout', headers=staff_headers[service]).status_code == 200
        assert c.get('/api/v1/auth/me', headers=staff_headers[service]).status_code == 401


def test_session_cannot_cross_services(clients, headers):
    assert clients['inventory'].get('/api/v1/auth/me', headers=headers['personnel']).status_code == 401


def test_password_change_revokes_all_sessions(clients, headers):
    for service, c in clients.items():
        res = c.post('/api/v1/auth/change-password', headers=headers[service], json={'current_password': 'admin12345', 'new_password': 'A-new-password-2026'})
        assert res.status_code == 200
        assert c.get('/api/v1/auth/me', headers=headers[service]).status_code == 401
        assert c.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'admin12345'}).status_code == 401
        assert c.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'A-new-password-2026'}).status_code == 200


def test_admin_cannot_lock_self_out(clients, headers):
    c, h = clients['personnel'], headers['personnel']
    me = c.get('/api/v1/auth/me', headers=h).json()
    assert c.patch('/api/v1/users/' + me['id'], headers=h, json={'role': 'staff'}).status_code == 409
    assert c.patch('/api/v1/users/' + me['id'], headers=h, json={'is_active': False}).status_code == 409


def test_pagination_rejects_overflowing_offsets(clients, headers):
    for service, client in clients.items():
        assert client.get('/api/v1/users?page=' + '9' * 50, headers=headers[service]).status_code == 422
        assert client.get('/api/v1/audit-logs?page=' + '9' * 50, headers=headers[service]).status_code == 422
    assert clients['personnel'].get('/api/v1/employees?page=' + '9' * 50, headers=headers['personnel']).status_code == 422
