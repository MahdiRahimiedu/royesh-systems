from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

API = '/api/v1'


def post(client, path, headers, body):
    response = client.post(API + path, headers=headers, json=body)
    assert response.status_code in (200, 201), response.text
    return response.json()


def employee(client, headers):
    return post(client, '/employees', headers, {'personnel_code': 'TEST', 'first_name': 'آزمون', 'last_name': 'پرسنلی', 'job_title': 'توسعه‌دهنده', 'hire_date': '2025-01-01', 'base_salary': 10_000_000})


def test_payroll_snapshot_and_single_payment(clients, headers):
    c, h = clients['personnel'], headers['personnel']
    e = employee(c, h)
    post(c, '/adjustments', h, {'employee_id': e['id'], 'kind': 'reward', 'amount': 500_000, 'reason': 'تحویل پروژه', 'date': '2026-11-10'})
    post(c, '/adjustments', h, {'employee_id': e['id'], 'kind': 'penalty', 'amount': 100_000, 'reason': 'کسور آموزشی', 'date': '2026-11-11'})
    payload = {'employee_id': e['id'], 'period': '2026-11', 'bonus': 200_000, 'deduction': 50_000}
    payroll = post(c, '/payrolls', h, payload)
    assert payroll['total'] == 10_550_000
    assert c.post(API + '/payrolls', headers=h, json=payload).status_code == 409
    assert c.post(API + '/adjustments', headers=h, json={'employee_id': e['id'], 'kind': 'reward', 'amount': 1, 'reason': 'دیرهنگام', 'date': '2026-11-12'}).status_code == 409
    post(c, f"/payrolls/{payroll['id']}/pay", h, {})
    assert c.post(API + f"/payrolls/{payroll['id']}/pay", headers=h, json={}).status_code == 409
    c.patch(API + '/employees/' + e['id'], headers=h, json={'base_salary': 20_000_000})
    saved = c.get(API + '/payrolls', headers=h).json()['items'][0]
    assert saved['base_salary'] == 10_000_000


def test_staff_scope_and_approval_permissions(clients, headers, staff_headers):
    c, h, staff = clients['personnel'], headers['personnel'], staff_headers['personnel']
    e = employee(c, h)
    own = c.get(API + '/auth/me', headers=staff).json()['employee_id']
    assert c.get(API + '/employees/' + e['id'], headers=staff).status_code == 403
    records = c.get(API + '/employees', headers=staff).json()['items']
    assert all(x['id'] == own for x in records)
    payload = {'employee_id': own, 'type': 'annual', 'start_date': '2027-01-05', 'end_date': '2027-01-06', 'reason': 'امور شخصی'}
    request = post(c, '/leaves', staff, payload)
    assert c.post(API + f"/leaves/{request['id']}/decision", headers=staff, json={'status': 'approved'}).status_code == 403
    assert c.post(API + '/leaves', headers=staff, json={**payload, 'employee_id': e['id']}).status_code == 403
    post(c, f"/leaves/{request['id']}/decision", h, {'status': 'approved'})
    assert c.post(API + f"/leaves/{request['id']}/decision", headers=h, json={'status': 'rejected'}).status_code == 409
    assert c.post(API + '/missions', headers=h, json={'employee_id': own, 'title': 'جلسه', 'destination': 'تهران', 'start_date': '2027-01-06', 'end_date': '2027-01-06'}).status_code == 409


def test_input_dates_and_inactive_employee(clients, headers):
    c, h = clients['personnel'], headers['personnel']
    e = employee(c, h)
    assert c.post(API + '/leaves', headers=h, json={'employee_id': e['id'], 'start_date': '2027-02-02', 'end_date': '2027-02-01', 'reason': 'معکوس'}).status_code == 422
    assert c.patch(API + '/employees/' + e['id'], headers=h, json={'base_salary': None}).status_code == 422
    assert c.patch(API + '/employees/' + e['id'], headers=h, json={'email': 'invalid'}).status_code == 422
    assert c.patch(API + '/employees/' + e['id'], headers=h, json={'job_title': 'a' * 151}).status_code == 422
    assert c.post(API + '/departments', headers=h, json={'name': 'a' * 151}).status_code == 422
    assert c.post(API + '/payrolls', headers=h, json={'employee_id': e['id'], 'period': '2026-13'}).status_code == 422
    c.patch(API + '/employees/' + e['id'], headers=h, json={'status': 'terminated'})
    assert c.post(API + '/payrolls', headers=h, json={'employee_id': e['id'], 'period': '2027-01'}).status_code == 409


def test_concurrent_approval_prevents_overlap(clients, headers):
    c, h = clients['personnel'], headers['personnel']
    e = employee(c, h)
    payload = {'employee_id': e['id'], 'start_date': '2027-05-01', 'end_date': '2027-05-03', 'reason': 'آزمون هم‌زمانی'}
    requests = [post(c, '/leaves', h, payload) for _ in range(2)]
    def approve(row):
        return c.post(API + f"/leaves/{row['id']}/decision", headers=h, json={'status': 'approved'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(approve, requests))
    assert sorted(statuses) == [200, 409]


def test_lookup_never_exposes_salary(clients, headers):
    result = clients['personnel'].get(API + '/employees/lookup', headers=headers['personnel']).json()
    assert result['items']
    assert all('base_salary' not in row and 'email' not in row for row in result['items'])
