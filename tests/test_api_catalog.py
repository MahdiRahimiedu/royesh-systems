"""Every documented read surface must be usable, protected and consistent with list IDs."""
from uuid import uuid4


def test_all_documented_get_endpoints_are_reachable_and_private(clients, headers):
    for service, c in clients.items():
        paths = c.app.openapi()['paths']
        for path, operations in paths.items():
            if 'get' not in operations or '{' in path:
                continue
            response = c.get(path, headers=headers[service])
            assert response.status_code == 200, f'{service} {path}: {response.text}'
            if path != '/health':
                assert c.get(path).status_code == 401, f'Anonymous access: {service} {path}'
            body = response.json()
            if isinstance(body, dict) and 'items' in body:
                assert body['page'] == 1 and body['page_size'] == 20
                assert body['total'] >= len(body['items'])
                # Link any documented detail GET back to IDs returned in its catalog.
                for detail in paths:
                    if detail.startswith(path + '/{') and detail.count('/') == path.count('/') + 1 and 'get' in paths[detail]:
                        if body['items']:
                            row = body['items'][0]
                            found = c.get(path + '/' + row['id'], headers=headers[service])
                            assert found.status_code == 200, found.text
                            assert found.json()['id'] == row['id']
                        assert c.get(path + '/' + str(uuid4()), headers=headers[service]).status_code == 404


def test_manager_role_has_business_access_without_user_administration(clients):
    for service, c in clients.items():
        login = c.post('/api/v1/auth/login', json={'username': 'manager', 'password': 'manager12345'})
        assert login.status_code == 200
        h = {'Authorization': 'Bearer ' + login.json()['access_token']}
        assert c.get('/api/v1/dashboard', headers=h).status_code == 200
        assert c.get('/api/v1/audit-logs', headers=h).status_code == 200
        assert c.get('/api/v1/users', headers=h).status_code == 403
        assert c.post('/api/v1/users', headers=h, json={'username': 'forbidden', 'full_name': 'حساب آزمون', 'password': 'Password-2026'}).status_code == 403
