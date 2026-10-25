"""Audit coverage for complete HR workflows, corrections and record history."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest

API = '/api/v1'


def post(c, endpoint, h, payload):
    response = c.post(API + endpoint, headers=h, json=payload)
    assert response.status_code in (200, 201), response.text
    return response.json()


def employee(c, h, **changes):
    return post(c, '/employees', h, {'personnel_code': 'AUD-' + uuid4().hex[:6], 'first_name': 'بهار', 'last_name': 'دانشجو', 'job_title': 'آزمونگر', 'hire_date': '2025-01-01', 'base_salary': 5_000_000, **changes})


def test_department_employee_full_crud_search_and_unique_codes(clients, headers):
    c, h = clients['personnel'], headers['personnel']
    department = post(c, '/departments', h, {'name': 'گروه داده', 'description': 'زیرساخت تحلیلی'})
    assert c.get(API + '/departments?q=تحلیلی', headers=h).json()['total'] == 1
    assert c.patch(API + '/departments/' + department['id'], headers=h, json={'description': 'تحلیل و گزارش'}).status_code == 200
    e = employee(c, h, department_id=department['id'], email='audit-hr@example.com', phone='09121112222')
    assert e['department_name'] == 'گروه داده'
    for q in ('بهار دانشجو', 'audit-hr@example.com', '09121112222'):
        assert c.get(API + '/employees', params={'q': q}, headers=h).json()['items'][0]['id'] == e['id']
    assert c.get(API + '/employees/lookup?q=بهار دانشجو', headers=h).json()['items'][0]['id'] == e['id']
    assert c.patch(API + '/employees/' + e['id'], headers=h, json={'department_id': None, 'phone': '09123334444'}).status_code == 200
    assert c.get(API + '/employees/' + e['id'], headers=h).json()['department_name'] == ''
    assert c.post(API + '/employees', headers=h, json={k: e[k] for k in ('personnel_code', 'first_name', 'last_name', 'hire_date', 'job_title')}).status_code == 409
    assert c.get(API + '/employees', headers=h, params={'q': '%'}).json()['total'] == 0
    assert c.get(API + '/employees', headers=h, params={'q': 'x' * 101}).status_code == 422
    assert c.get(API + '/employees/does-not-exist', headers=h).status_code == 404


def test_employment_contract_history_and_overlap(clients, headers):
    c, h = clients['personnel'], headers['personnel']
    e = employee(c, h)
    body = {'employee_id': e['id'], 'title': 'همکاری داده', 'start_date': '2026-01-01', 'end_date': '2026-12-31', 'base_salary': 5_000_000}
    assert c.post(API + '/employment-contracts', headers=h, json={**body, 'start_date': '2024-01-01'}).status_code == 422
    contract = post(c, '/employment-contracts', h, body)
    assert c.get(API + '/employment-contracts?q=همکاری داده', headers=h).json()['total'] == 1
    assert c.post(API + '/employment-contracts', headers=h, json=body).status_code == 409
    next_contract = post(c, '/employment-contracts', h, {**body, 'start_date': '2027-01-01', 'end_date': '2027-12-31'})
    assert c.patch(API + '/employment-contracts/' + contract['id'], headers=h, json={'end_date': '2027-01-01'}).status_code == 409
    assert c.patch(API + '/employment-contracts/' + contract['id'], headers=h, json={'title': 'عنوان اصلاح‌شده'}).status_code == 200
    assert c.patch(API + '/employees/' + e['id'], headers=h, json={'hire_date': '2026-06-01'}).status_code == 409
    assert c.patch(API + '/employment-contracts/' + contract['id'], headers=h, json={'status': 'ended'}).status_code == 200
    assert c.patch(API + '/employment-contracts/' + contract['id'], headers=h, json={'notes': 'تغییر دیرهنگام'}).status_code == 409


def test_concurrent_contracts_only_one_overlapping_active_contract(clients, headers):
    c, h = clients['personnel'], headers['personnel']
    e = employee(c, h)
    body = {'employee_id': e['id'], 'title': 'همکاری', 'start_date': '2027-01-01', 'base_salary': 1_000_000}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: c.post(API + '/employment-contracts', headers=h, json=body).status_code, range(2)))
    assert sorted(results) == [201, 409]


def test_manager_can_set_allowance_on_staff_mission_approval(clients, headers, staff_headers):
    c, h, staff = clients['personnel'], headers['personnel'], staff_headers['personnel']
    own = c.get(API + '/auth/me', headers=staff).json()['employee_id']
    mission = post(c, '/missions', staff, {'employee_id': own, 'title': 'راه‌اندازی سرویس', 'destination': 'دفتر مشتری', 'start_date': '2027-05-02', 'end_date': '2027-05-02', 'allowance': 0})
    assert c.get(API + '/dashboard', headers=staff).json()['metrics'][0]['value'] == 1
    assert c.post(API + f"/missions/{mission['id']}/decision", headers=staff, json={'status': 'approved', 'allowance': 1_000_000}).status_code == 403
    approved = post(c, f"/missions/{mission['id']}/decision", h, {'status': 'approved', 'allowance': 1_000_000, 'comment': 'هزینه رفت‌وآمد'})
    assert approved['allowance'] == 1_000_000
    assert c.get(API + '/missions?q=راه‌اندازی', headers=h).json()['total'] == 1
    payroll = post(c, '/payrolls', h, {'employee_id': own, 'period': '2027-05'})
    assert payroll['mission_allowance'] == 1_000_000
    assert c.get(API + '/payrolls?q=2027-05', headers=h).json()['total'] == 1


def test_allowance_cannot_be_injected_into_leave_or_rejection(clients, headers):
    c, h = clients['personnel'], headers['personnel']
    e = employee(c, h)
    leave = post(c, '/leaves', h, {'employee_id': e['id'], 'start_date': '2027-06-01', 'end_date': '2027-06-01', 'reason': 'امور شخصی'})
    assert c.post(API + f"/leaves/{leave['id']}/decision", headers=h, json={'status': 'approved', 'allowance': 1}).status_code == 422
    assert leave['id'] in {row['id'] for row in c.get(API + '/leaves?q=امور شخصی', headers=h).json()['items']}
    rejected = post(c, f"/leaves/{leave['id']}/decision", h, {'status': 'rejected', 'comment': 'بازه دیگر انتخاب شود'})
    assert rejected['decision_comment'] == 'بازه دیگر انتخاب شود'


def test_draft_payroll_correction_and_paid_immutability(clients, headers, staff_headers):
    c, h = clients['personnel'], headers['personnel']
    e = employee(c, h)
    row = post(c, '/payrolls', h, {'employee_id': e['id'], 'period': '2027-07', 'bonus': 10, 'deduction': 5})
    corrected = c.patch(API + '/payrolls/' + row['id'], headers=h, json={'bonus': 200, 'deduction': 100})
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()['total'] == e['base_salary'] + 100
    assert c.patch(API + '/payrolls/' + row['id'], headers=h, json={'base_salary': 1}).status_code == 422
    assert c.patch(API + '/payrolls/' + row['id'], headers=staff_headers['personnel'], json={'bonus': 1}).status_code == 403
    assert c.patch(API + '/payrolls/' + row['id'], headers=h, json={'deduction': 10_000_000}).status_code == 422
    post(c, f"/payrolls/{row['id']}/pay", h, {})
    assert c.patch(API + '/payrolls/' + row['id'], headers=h, json={'bonus': 300}).status_code == 409


def test_zero_cost_mission_can_be_approved_without_changing_issued_payroll(clients, headers):
    c, h = clients['personnel'], headers['personnel']
    e = employee(c, h)
    payroll = post(c, '/payrolls', h, {'employee_id': e['id'], 'period': '2027-09'})
    row = post(c, '/missions', h, {'employee_id': e['id'], 'title': 'جلسه مجازی', 'destination': 'آنلاین', 'start_date': '2027-09-02', 'end_date': '2027-09-02'})
    assert c.post(API + f"/missions/{row['id']}/decision", headers=h, json={'status': 'approved', 'allowance': 5}).status_code == 409
    post(c, f"/missions/{row['id']}/decision", h, {'status': 'approved', 'allowance': 0})
    assert c.get(API + '/payrolls?q=2027-09', headers=h).json()['items'][0]['total'] == payroll['total']


@pytest.mark.parametrize('endpoint', ['employees', 'employment-contracts', 'leaves', 'missions', 'payrolls'])
def test_invalid_status_filter_is_rejected(clients, headers, endpoint):
    assert clients['personnel'].get(API + '/' + endpoint, headers=headers['personnel'], params={'status': 'imaginary'}).status_code == 422


def test_adjustment_date_and_all_staff_read_scopes(clients, headers, staff_headers):
    c, h, staff = clients['personnel'], headers['personnel'], staff_headers['personnel']
    e = employee(c, h)
    assert c.post(API + '/adjustments', headers=h, json={'employee_id': e['id'], 'kind': 'reward', 'amount': 100, 'date': '2024-12-31', 'reason': 'قبل استخدام'}).status_code == 422
    own = c.get(API + '/auth/me', headers=staff).json()['employee_id']
    for endpoint in ('employment-contracts', 'leaves', 'missions', 'adjustments', 'payrolls'):
        response = c.get(API + '/' + endpoint, headers=staff)
        assert response.status_code == 200
        assert all(row['employee_id'] == own for row in response.json()['items'])


def test_inactive_employee_cannot_be_approved_but_request_can_be_rejected(clients, headers):
    c, h = clients['personnel'], headers['personnel']
    e = employee(c, h)
    leave = post(c, '/leaves', h, {'employee_id': e['id'], 'start_date': '2027-01-01', 'end_date': '2027-01-01', 'reason': 'درخواست نمونه'})
    c.patch(API + '/employees/' + e['id'], headers=h, json={'status': 'terminated'})
    assert c.post(API + f"/leaves/{leave['id']}/decision", headers=h, json={'status': 'approved'}).status_code == 409
    post(c, f"/leaves/{leave['id']}/decision", h, {'status': 'rejected'})
