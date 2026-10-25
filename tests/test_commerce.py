"""Money and workflow invariants tested through the public HTTP API."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from uuid import uuid4

import pytest

API = "/api/v1"


def post(client, path, headers, body):
    response = client.post(API + path, headers=headers, json=body)
    assert response.status_code in (200, 201), response.text
    return response.json()


def customer(client, headers):
    return post(client, "/customers", headers, {"name": "مشتری آزمون " + uuid4().hex[:8]})


def active_contract(client, headers, amount=1_000):
    buyer = customer(client, headers)
    obj = post(client, "/contracts", headers, {"customer_id": buyer["id"], "title": "قرارداد آزمون", "start_date": date.today().isoformat(), "amount": amount})
    return post(client, f"/contracts/{obj['id']}/status", headers, {"status": "active"})


def invoice(client, headers, contract, amount=1_000):
    return post(client, "/invoices", headers, {"contract_id": contract["id"], "issue_date": date.today().isoformat(), "due_date": (date.today() + timedelta(days=7)).isoformat(), "amount": amount})


def payment_payload(bill, amount, reference=None):
    return {"invoice_id": bill["id"], "amount": amount, "paid_date": date.today().isoformat(), "method": "bank", "reference": reference}


def quotation(client, auth, buyer, **changes):
    body = {"customer_id": buyer["id"], "title": "پیشنهاد آزمون", "valid_until": (date.today() + timedelta(days=7)).isoformat(), "lines": [{"description": "توسعه", "quantity": 1, "unit_price": 1_000}]}
    return post(client, "/quotations", auth, {**body, **changes})


def test_quote_conversion_preserves_customer_and_can_happen_once(clients, headers):
    client, auth = clients["commerce"], headers["commerce"]
    buyer = customer(client, auth)
    other = customer(client, auth)
    quote = post(client, "/quotations", auth, {"customer_id": buyer["id"], "title": "طراحی نرم‌افزار", "valid_until": (date.today() + timedelta(days=10)).isoformat(), "lines": [{"description": "تحلیل", "quantity": 2, "unit_price": 250}, {"description": "توسعه", "quantity": 1, "unit_price": 500}]})
    assert quote["total"] == 1_000
    assert len(quote["lines"]) == 2
    body = {"customer_id": buyer["id"], "quotation_id": quote["id"], "title": "قرارداد توسعه", "start_date": date.today().isoformat(), "amount": 1_000}
    assert client.post(API + "/contracts", headers=auth, json=body).status_code == 409
    post(client, f"/quotations/{quote['id']}/status", auth, {"status": "sent"})
    post(client, f"/quotations/{quote['id']}/status", auth, {"status": "accepted"})
    assert client.post(API + "/contracts", headers=auth, json={**body, "customer_id": other["id"]}).status_code == 409
    assert client.post(API + "/contracts", headers=auth, json={**body, "amount": 999}).status_code == 409
    contract = post(client, "/contracts", auth, body)
    assert client.post(API + "/contracts", headers=auth, json=body).status_code == 409
    assert client.patch(API + f"/contracts/{contract['id']}", headers=auth, json={"customer_id": other["id"]}).status_code == 409
    assert client.post(API + f"/quotations/{quote['id']}/status", headers=auth, json={"status": "draft"}).status_code == 409


def test_receipts_reject_overpayment_and_preserve_balances(clients, headers):
    client, auth = clients["commerce"], headers["commerce"]
    contract = active_contract(client, auth)
    bill = invoice(client, auth, contract)
    first = post(client, "/payments", auth, payment_payload(bill, 400))
    assert first["invoice_balance"] == 600
    assert first["invoice_status"] == "partial"
    searched = client.get(API + "/payments", headers=auth, params={"q": first["customer_name"], "invoice_id": bill["id"]})
    assert searched.status_code == 200, searched.text
    assert searched.json()["items"][0]["contract_title"] == contract["title"]
    assert client.post(API + "/payments", headers=auth, json=payment_payload(bill, 601)).status_code == 409
    assert client.post(API + f"/invoices/{bill['id']}/void", headers=auth, json={}).status_code == 409
    final = post(client, "/payments", auth, payment_payload(bill, 600))
    assert final["invoice_balance"] == 0
    assert final["invoice_status"] == "paid"
    assert client.post(API + "/payments", headers=auth, json=payment_payload(bill, 1)).status_code == 409
    state = client.get(API + f"/invoices/{bill['id']}", headers=auth).json()
    assert state["paid_amount"] == 1_000
    assert state["balance"] == 0


def test_void_releases_contract_ceiling_without_erasing_invoice(clients, headers):
    client, auth = clients["commerce"], headers["commerce"]
    contract = active_contract(client, auth)
    bill = invoice(client, auth, contract, 700)
    too_much = {"contract_id": contract["id"], "issue_date": date.today().isoformat(), "due_date": date.today().isoformat(), "amount": 301}
    assert client.post(API + "/invoices", headers=auth, json=too_much).status_code == 409
    assert client.post(API + f"/contracts/{contract['id']}/status", headers=auth, json={"status": "cancelled"}).status_code == 409
    voided = post(client, f"/invoices/{bill['id']}/void", auth, {})
    assert voided["status"] == "void" and voided["balance"] == 0
    assert client.post(API + f"/invoices/{bill['id']}/void", headers=auth, json={}).status_code == 409
    assert client.post(API + "/payments", headers=auth, json=payment_payload(bill, 1)).status_code == 409
    invoice(client, auth, contract, 1_000)
    current = client.get(API + f"/contracts/{contract['id']}", headers=auth).json()
    assert current["invoiced_amount"] == 1_000
    assert current["remaining_amount"] == 0


def test_reference_duplicate_does_not_increment_invoice(clients, headers):
    client, auth = clients["commerce"], headers["commerce"]
    bill = invoice(client, auth, active_contract(client, auth))
    reference = "TEST-" + uuid4().hex
    post(client, "/payments", auth, payment_payload(bill, 200, reference))
    assert client.post(API + "/payments", headers=auth, json=payment_payload(bill, 200, reference)).status_code == 409
    current = client.get(API + f"/invoices/{bill['id']}", headers=auth).json()
    assert current["paid_amount"] == 200


def test_active_contract_keeps_financial_terms_but_allows_metadata(clients, headers):
    client, auth = clients["commerce"], headers["commerce"]
    contract = active_contract(client, auth)
    changed = client.patch(API + f"/contracts/{contract['id']}", headers=auth, json={"amount": 999})
    assert changed.status_code == 409
    updated = client.patch(API + f"/contracts/{contract['id']}", headers=auth, json={"title": "عنوان اصلاح‌شده", "amount": contract["amount"], "customer_id": contract["customer_id"], "start_date": contract["start_date"], "end_date": None, "employee_id": None, "employee_name": ""})
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "عنوان اصلاح‌شده"


def test_concurrent_receipts_cannot_overpay(clients, headers):
    client, auth = clients["commerce"], headers["commerce"]
    bill = invoice(client, auth, active_contract(client, auth))
    def pay(_):
        return client.post(API + "/payments", headers=auth, json=payment_payload(bill, 700)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(pay, range(2)))
    assert sorted(results) == [201, 409]
    current = client.get(API + f"/invoices/{bill['id']}", headers=auth).json()
    assert current["paid_amount"] == 700
    assert current["balance"] == 300


def test_concurrent_invoices_cannot_exceed_contract(clients, headers):
    client, auth = clients["commerce"], headers["commerce"]
    contract = active_contract(client, auth)
    payload = {"contract_id": contract["id"], "issue_date": date.today().isoformat(), "due_date": date.today().isoformat(), "amount": 700}
    def issue(_):
        return client.post(API + "/invoices", headers=auth, json=payload).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(issue, range(2)))
    assert sorted(results) == [201, 409]
    current = client.get(API + f"/contracts/{contract['id']}", headers=auth).json()
    assert current["invoiced_amount"] == 700


def test_concurrent_duplicate_reference_rolls_back_losing_receipt(clients, headers):
    client, auth = clients["commerce"], headers["commerce"]
    contract = active_contract(client, auth)
    bills = [invoice(client, auth, contract, 500), invoice(client, auth, contract, 500)]
    reference = "CONCURRENT-" + uuid4().hex
    def pay(bill):
        return client.post(API + "/payments", headers=auth, json=payment_payload(bill, 200, reference)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(pay, bills))
    assert sorted(results) == [201, 409]
    totals = [client.get(API + f"/invoices/{bill['id']}", headers=auth).json()["paid_amount"] for bill in bills]
    assert sorted(totals) == [0, 200]


@pytest.mark.parametrize("amount", [0, -1, True, 1.5, "100", 1_000_000_000_000_001])
def test_amount_requires_positive_bounded_integer(clients, headers, amount):
    response = clients["commerce"].post(API + "/offerings", headers=headers["commerce"], json={"name": "خدمت", "unit_price": amount})
    assert response.status_code == 422


def test_staff_read_only_and_unknown_fields_rejected(clients, headers, staff_headers):
    client, auth = clients["commerce"], headers["commerce"]
    assert client.get(API + "/customers", headers=staff_headers["commerce"]).status_code == 200
    assert client.post(API + "/customers", headers=staff_headers["commerce"], json={"name": "مشتری"}).status_code == 403
    assert client.post(API + "/customers", headers=auth, json={"name": "مشتری", "balance": 999}).status_code == 422
    buyer = customer(client, auth)
    assert client.patch(API + f"/customers/{buyer['id']}", headers=auth, json={"name": None}).status_code == 422
    assert client.post(API + "/contracts", headers=auth, json={"customer_id": buyer["id"], "title": "نامعتبر", "start_date": "2026-10-23", "end_date": "2026-10-22", "amount": 100}).status_code == 422


def test_quote_quantity_and_total_are_validated_before_persistence(clients, headers):
    client, auth = clients["commerce"], headers["commerce"]
    buyer = customer(client, auth)
    body = {"customer_id": buyer["id"], "title": "ورودی نامعتبر", "valid_until": (date.today() + timedelta(days=5)).isoformat()}
    for quantity in (0, -1, True, 1.5, "2"):
        response = client.post(API + "/quotations", headers=auth, json={**body, "lines": [{"description": "شرح", "quantity": quantity, "unit_price": 1}]})
        assert response.status_code == 422
    response = client.post(API + "/quotations", headers=auth, json={**body, "lines": [{"description": "شرح", "quantity": 2, "unit_price": 1_000_000_000_000_000}]})
    assert response.status_code == 422
    assert client.get(API + "/quotations", headers=auth, params={"customer_id": buyer["id"]}).json()["total"] == 0


def test_inactive_customer_cannot_send_or_accept_new_business(clients, headers):
    client, auth = clients["commerce"], headers["commerce"]
    buyer = customer(client, auth)
    draft = quotation(client, auth, buyer)
    sent = quotation(client, auth, buyer)
    post(client, f"/quotations/{sent['id']}/status", auth, {"status": "sent"})
    changed = client.patch(API + f"/customers/{buyer['id']}", headers=auth, json={"status": "inactive"})
    assert changed.status_code == 200
    assert client.post(API + f"/quotations/{draft['id']}/status", headers=auth, json={"status": "sent"}).status_code == 409
    assert client.post(API + f"/quotations/{sent['id']}/status", headers=auth, json={"status": "accepted"}).status_code == 409
    assert post(client, f"/quotations/{sent['id']}/status", auth, {"status": "rejected"})["status"] == "rejected"


def test_future_financial_dates_do_not_recognize_receipts_early(clients, headers):
    client, auth = clients["commerce"], headers["commerce"]
    contract = active_contract(client, auth)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    future_bill = {"contract_id": contract["id"], "issue_date": tomorrow, "due_date": tomorrow, "amount": 1_000}
    assert client.post(API + "/invoices", headers=auth, json=future_bill).status_code == 422
    bill = invoice(client, auth, contract)
    future_payment = {**payment_payload(bill, 1_000), "paid_date": tomorrow}
    assert client.post(API + "/payments", headers=auth, json=future_payment).status_code == 422
    state = client.get(API + f"/invoices/{bill['id']}", headers=auth).json()
    assert state["paid_amount"] == 0 and state["status"] == "unpaid"


def test_search_covers_contact_and_customer_labels_and_validates_filters(clients, headers):
    client, auth = clients["commerce"], headers["commerce"]
    token = uuid4().hex
    buyer = post(client, "/customers", auth, {"name": "شرکت " + token, "email": token + "@example.test", "phone": "0999" + token[:8]})
    quote = quotation(client, auth, buyer)
    contract = post(client, "/contracts", auth, {"customer_id": buyer["id"], "title": "طراحی", "start_date": date.today().isoformat(), "amount": 1_000})
    for search in (buyer["phone"], buyer["email"]):
        assert client.get(API + "/customers", headers=auth, params={"q": search}).json()["items"][0]["id"] == buyer["id"]
    assert client.get(API + "/quotations", headers=auth, params={"q": buyer["name"]}).json()["items"][0]["id"] == quote["id"]
    assert client.get(API + "/contracts", headers=auth, params={"q": buyer["name"]}).json()["items"][0]["id"] == contract["id"]
    for endpoint in ("customers", "quotations", "contracts", "invoices"):
        assert client.get(API + "/" + endpoint, headers=auth, params={"status": "typo"}).status_code == 422


def test_draft_quotation_can_be_corrected_without_changing_issued_history(clients, headers):
    client, auth = clients["commerce"], headers["commerce"]
    buyer = customer(client, auth)
    quote = quotation(client, auth, buyer)
    correction = {"title": "عنوان اصلاح‌شده", "lines": [{"description": "تحلیل", "quantity": 2, "unit_price": 750}, {"description": "آزمون", "quantity": 1, "unit_price": 500}]}
    response = client.patch(API + f"/quotations/{quote['id']}", headers=auth, json=correction)
    assert response.status_code == 200, response.text
    revised = response.json()
    assert revised["total"] == 2_000 and len(revised["lines"]) == 2
    assert revised["title"] == correction["title"]
    invalid = {"lines": [{"description": "نامعتبر", "quantity": 0, "unit_price": 1}]}
    assert client.patch(API + f"/quotations/{quote['id']}", headers=auth, json=invalid).status_code == 422
    unchanged = client.get(API + f"/quotations/{quote['id']}", headers=auth).json()
    assert unchanged["total"] == 2_000 and len(unchanged["lines"]) == 2
    post(client, f"/quotations/{quote['id']}/status", auth, {"status": "sent"})
    assert client.patch(API + f"/quotations/{quote['id']}", headers=auth, json={"notes": "تغییر پس از ارسال"}).status_code == 409
    audit = client.get(API + "/audit-logs", headers=auth).json()["items"]
    previous = [entry for entry in audit if entry["entity_id"] == quote["id"] and entry["action"] == "update"]
    assert previous and 'previous_draft' in previous[0]["details"]


def test_catalog_edits_snapshot_prices_and_preserve_inactive_history(clients, headers):
    client, auth = clients["commerce"], headers["commerce"]
    buyer = customer(client, auth)
    service = post(client, "/offerings", auth, {"name": "خدمت آزمون", "description": uuid4().hex, "unit_price": 100})
    assert client.get(API + f"/offerings/{service['id']}", headers=auth).json()["unit_price"] == 100
    assert client.get(API + "/offerings", headers=auth, params={"q": service["description"]}).json()["items"][0]["id"] == service["id"]
    quote = quotation(client, auth, buyer, lines=[{"offering_id": service["id"], "description": "نسخه اول", "quantity": 2, "unit_price": 100}])
    assert client.patch(API + f"/offerings/{service['id']}", headers=auth, json={"unit_price": 300, "is_active": False}).status_code == 200
    assert client.get(API + f"/quotations/{quote['id']}", headers=auth).json()["total"] == 200
    body = {"customer_id": buyer["id"], "title": "خدمت غیرفعال", "valid_until": date.today().isoformat(), "lines": [{"offering_id": service["id"], "description": "غیرفعال", "quantity": 1, "unit_price": 100}]}
    assert client.post(API + "/quotations", headers=auth, json=body).status_code == 409
    assert service["id"] in {item["id"] for item in client.get(API + "/offerings", headers=auth, params={"is_active": False}).json()["items"]}
    # Disabling a catalog entry does not rewrite an existing price snapshot.
    post(client, f"/quotations/{quote['id']}/status", auth, {"status": "sent"})
    draft = quotation(client, auth, buyer)
    contract = post(client, "/contracts", auth, {"customer_id": buyer["id"], "title": "سابقه موجود", "start_date": date.today().isoformat(), "amount": 500})
    post(client, f"/contracts/{contract['id']}/status", auth, {"status": "active"})
    assert client.patch(API + f"/customers/{buyer['id']}", headers=auth, json={"status": "inactive", "address": "نشانی اصلاح‌شده"}).status_code == 200
    assert client.get(API + f"/customers/{buyer['id']}", headers=auth).json()["address"] == "نشانی اصلاح‌شده"
    page = client.get(API + "/customers", headers=auth, params={"status": "inactive", "q": buyer["name"], "page_size": 1}).json()
    assert page["total"] == 1 and page["items"][0]["id"] == buyer["id"]
    assert client.get(API + "/customers", headers=auth, params={"status": "inactive", "q": buyer["name"], "page_size": 1, "page": 2}).json()["items"] == []
    assert client.get(API + "/customers", headers=auth, params={"page": 10**30}).status_code == 422
    assert client.get(API + "/quotations", headers=auth, params={"customer_id": buyer["id"], "status": "sent"}).json()["items"][0]["id"] == quote["id"]
    assert client.get(API + "/contracts", headers=auth, params={"customer_id": buyer["id"], "status": "active"}).json()["items"][0]["id"] == contract["id"]
    assert client.patch(API + f"/contracts/{contract['id']}", headers=auth, json={"customer_id": buyer["id"], "notes": "پیگیری سابقه"}).status_code == 200
    assert client.patch(API + f"/quotations/{draft['id']}", headers=auth, json={"customer_id": buyer["id"], "notes": "اصلاح سابقه"}).status_code == 200
    assert client.post(API + "/quotations", headers=auth, json={**body, "lines": [{"description": "جدید", "quantity": 1, "unit_price": 100}]}).status_code == 409


def test_expiry_and_terminal_transitions_use_company_calendar(clients, headers, monkeypatch):
    from importlib import import_module
    module = import_module("services.commerce.app")
    client, auth = clients["commerce"], headers["commerce"]
    buyer = customer(client, auth)
    today = date.today()
    draft = quotation(client, auth, buyer, valid_until=today.isoformat())
    accepted = quotation(client, auth, buyer, valid_until=today.isoformat())
    post(client, f"/quotations/{accepted['id']}/status", auth, {"status": "sent"})
    post(client, f"/quotations/{accepted['id']}/status", auth, {"status": "accepted"})
    monkeypatch.setattr(module, "business_today", lambda: today + timedelta(days=1))
    assert client.post(API + f"/quotations/{draft['id']}/status", headers=auth, json={"status": "sent"}).status_code == 409
    assert client.post(API + "/quotations", headers=auth, json={"customer_id": buyer["id"], "title": "منقضی", "valid_until": today.isoformat(), "lines": [{"description": "شرح", "quantity": 1, "unit_price": 100}]}).status_code == 422
    contract = post(client, "/contracts", auth, {"customer_id": buyer["id"], "quotation_id": accepted["id"], "title": "قبول در زمان اعتبار", "start_date": today.isoformat(), "amount": accepted["total"]})
    post(client, f"/contracts/{contract['id']}/status", auth, {"status": "cancelled"})
    assert client.patch(API + f"/contracts/{contract['id']}", headers=auth, json={"notes": "تغییر نهایی"}).status_code == 409
    assert client.post(API + f"/contracts/{contract['id']}/status", headers=auth, json={"status": "active"}).status_code == 409
    assert client.post(API + "/invoices", headers=auth, json={"contract_id": contract["id"], "issue_date": today.isoformat(), "due_date": today.isoformat(), "amount": 100}).status_code == 409
    completed = active_contract(client, auth)
    post(client, f"/contracts/{completed['id']}/status", auth, {"status": "completed"})
    assert invoice(client, auth, completed)["amount"] == 1_000
    assert client.patch(API + f"/contracts/{completed['id']}", headers=auth, json={"title": "ویرایش"}).status_code == 409
    assert client.post(API + f"/contracts/{completed['id']}/status", headers=auth, json={"status": "cancelled"}).status_code == 409


def test_reports_and_dashboard_reconcile_partial_paid_and_void_invoices(clients, headers):
    client, auth = clients["commerce"], headers["commerce"]
    initial = {item["label"]: item["value"] for item in client.get(API + "/dashboard", headers=auth).json()["metrics"]}
    buyer = customer(client, auth)
    today = date.today()
    contract = post(client, "/contracts", auth, {"customer_id": buyer["id"], "title": "گزارش مطالبات", "start_date": (today - timedelta(days=10)).isoformat(), "amount": 1_000})
    post(client, f"/contracts/{contract['id']}/status", auth, {"status": "active"})
    bills = []
    for amount, due_offset in ((500, -1), (200, 2), (300, 0)):
        bills.append(post(client, "/invoices", auth, {"contract_id": contract["id"], "issue_date": (today - timedelta(days=2)).isoformat(), "due_date": (today + timedelta(days=due_offset)).isoformat(), "amount": amount, "description": "آزمون گزارش"}))
    assert client.post(API + "/payments", headers=auth, json={**payment_payload(bills[0], 100), "paid_date": (today - timedelta(days=3)).isoformat()}).status_code == 422
    post(client, "/payments", auth, payment_payload(bills[0], 100))
    post(client, f"/invoices/{bills[1]['id']}/void", auth, {})
    post(client, "/payments", auth, payment_payload(bills[2], 300))
    for overdue in (False, True):
        report = client.get(API + "/reports/receivables", headers=auth, params={"q": buyer["name"], "overdue": overdue}).json()
        assert report["total"] == 1 and report["items"][0]["balance"] == 400
    voids = client.get(API + "/invoices", headers=auth, params={"status": "void", "contract_id": contract["id"], "q": buyer["name"]}).json()
    assert voids["total"] == 1 and voids["items"][0]["id"] == bills[1]["id"]
    metrics = {item["label"]: item["value"] for item in client.get(API + "/dashboard", headers=auth).json()["metrics"]}
    assert metrics["مانده مطالبات"] == initial["مانده مطالبات"] + 400
    assert metrics["صورتحساب معوق"] == initial["صورتحساب معوق"] + 1
    assert client.get(API + "/reports/receivables", headers=auth, params={"q": uuid4().hex}).json()["total"] == 0


def test_all_commerce_business_routes_enforce_staff_and_anonymous_access(clients, headers, staff_headers):
    client, auth, staff = clients["commerce"], headers["commerce"], staff_headers["commerce"]
    buyer = customer(client, auth)
    service = post(client, "/offerings", auth, {"name": "مجوزها", "unit_price": 100})
    quote = quotation(client, auth, buyer)
    contract = active_contract(client, auth)
    bill = invoice(client, auth, contract)
    reads = ["/customers", f"/customers/{buyer['id']}", "/offerings", f"/offerings/{service['id']}", "/quotations", f"/quotations/{quote['id']}", "/contracts", f"/contracts/{contract['id']}", "/invoices", f"/invoices/{bill['id']}", "/payments", "/reports/receivables", "/dashboard"]
    for path in reads:
        assert client.get(API + path, headers=staff).status_code == 200, path
        assert client.get(API + path).status_code == 401, path
    writes = [("POST", "/customers", {"name": "ردشده"}), ("PATCH", f"/customers/{buyer['id']}", {"name": "ردشده"}), ("POST", "/offerings", {"name": "ردشده", "unit_price": 100}), ("PATCH", f"/offerings/{service['id']}", {"name": "ردشده"}), ("POST", "/quotations", {"customer_id": buyer["id"], "title": "ردشده", "valid_until": date.today().isoformat(), "lines": [{"description": "شرح", "quantity": 1, "unit_price": 100}]}), ("PATCH", f"/quotations/{quote['id']}", {"notes": "ردشده"}), ("POST", f"/quotations/{quote['id']}/status", {"status": "sent"}), ("POST", "/contracts", {"customer_id": buyer["id"], "title": "ردشده", "start_date": date.today().isoformat(), "amount": 100}), ("PATCH", f"/contracts/{contract['id']}", {"notes": "ردشده"}), ("POST", f"/contracts/{contract['id']}/status", {"status": "completed"}), ("POST", "/invoices", {"contract_id": contract["id"], "issue_date": date.today().isoformat(), "due_date": date.today().isoformat(), "amount": 100}), ("POST", f"/invoices/{bill['id']}/void", {}), ("POST", "/payments", payment_payload(bill, 100))]
    for method, path, body in writes:
        assert client.request(method, API + path, headers=staff, json=body).status_code == 403, path
        assert client.request(method, API + path, json=body).status_code == 401, path
    for path in ("customers", "offerings", "quotations", "contracts", "invoices"):
        assert client.get(API + f"/{path}/{uuid4()}", headers=auth).status_code == 404
    # The API intentionally offers no history-deleting operation.
    assert client.delete(API + f"/invoices/{bill['id']}", headers=auth).status_code == 405


def test_concurrent_receipt_and_void_have_only_one_winner(clients, headers):
    client, auth = clients["commerce"], headers["commerce"]
    contract = active_contract(client, auth)
    bill = invoice(client, auth, contract)
    def action(kind):
        if kind == "void":
            return client.post(API + f"/invoices/{bill['id']}/void", headers=auth, json={}).status_code
        return client.post(API + "/payments", headers=auth, json=payment_payload(bill, 100)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(action, ["void", "payment"]))
    assert outcomes in ([200, 409], [409, 201])
    current = client.get(API + f"/invoices/{bill['id']}", headers=auth).json()
    total = client.get(API + f"/contracts/{contract['id']}", headers=auth).json()["invoiced_amount"]
    assert (current["status"], current["paid_amount"], total) in (("void", 0, 0), ("partial", 100, 1_000))


def test_concurrent_quote_conversion_and_revision_remain_atomic(clients, headers):
    client, auth = clients["commerce"], headers["commerce"]
    buyer = customer(client, auth)
    quote = quotation(client, auth, buyer)
    def revise(amount):
        return client.patch(API + f"/quotations/{quote['id']}", headers=auth, json={"lines": [{"description": str(amount), "quantity": 1, "unit_price": amount}]}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(revise, [600, 800]))
    assert 200 in outcomes and set(outcomes) <= {200, 409}
    current = client.get(API + f"/quotations/{quote['id']}", headers=auth).json()
    assert len(current["lines"]) == 1 and current["total"] in (600, 800)
    assert sum(line["quantity"] * line["unit_price"] for line in current["lines"]) == current["total"]
    post(client, f"/quotations/{quote['id']}/status", auth, {"status": "sent"})
    post(client, f"/quotations/{quote['id']}/status", auth, {"status": "accepted"})
    body = {"customer_id": buyer["id"], "quotation_id": quote["id"], "title": "تبدیل هم‌زمان", "start_date": date.today().isoformat(), "amount": current["total"]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        converted = list(pool.map(lambda _: client.post(API + "/contracts", headers=auth, json=body).status_code, range(2)))
    assert sorted(converted) == [201, 409]
    assert client.get(API + "/contracts", headers=auth, params={"customer_id": buyer["id"]}).json()["total"] == 1
