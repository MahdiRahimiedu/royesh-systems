"""Business invariants: inventory must remain correct after rejected/repeated work."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from services.inventory.models import Asset, Assignment, Item, Movement, Purchase, Supplier
from services.inventory.routes import MAX_STOCK


@pytest.fixture
def inventory_api(clients, headers):
    client = clients["inventory"]
    return client, headers["inventory"]


def create_item(api, tracking="quantity", stock=0):
    client, headers = api
    response = client.post("/api/v1/items", headers=headers, json={
        "sku": f"TEST-{uuid4().hex[:16]}", "name": "کالای آزمایشی", "category": "آزمون",
        "unit": "عدد", "tracking_type": tracking, "min_stock": 2,
    })
    assert response.status_code == 201, response.text
    item = response.json()
    if stock:
        response = client.post("/api/v1/movements", headers=headers, json={
            "item_id": item["id"], "type": "in", "quantity": stock, "reason": "آماده‌سازی آزمون",
        })
        assert response.status_code == 201, response.text
    return item


def create_purchase(api, item, quantity=3):
    client, headers = api
    supplier = client.post("/api/v1/suppliers", headers=headers, json={"name": "تأمین‌کننده آزمایش"})
    assert supplier.status_code == 201, supplier.text
    result = client.post("/api/v1/purchases", headers=headers, json={
        "supplier_id": supplier.json()["id"], "item_id": item["id"], "quantity": quantity, "unit_price": 100_000,
    })
    assert result.status_code == 201, result.text
    return result.json()


def test_purchase_requires_approval_and_receives_once(inventory_api):
    client, headers = inventory_api
    item = create_item(inventory_api)
    purchase = create_purchase(inventory_api, item)
    url = f"/api/v1/purchases/{purchase['id']}"
    assert client.post(f"{url}/receive", headers=headers, json={}).status_code == 409
    assert client.post(f"{url}/approve", headers=headers, json={}).status_code == 200
    assert client.post(f"{url}/receive", headers=headers, json={}).status_code == 200
    assert client.post(f"{url}/receive", headers=headers, json={}).status_code == 409
    assert client.post(f"{url}/cancel", headers=headers, json={}).status_code == 409
    stock = client.get(f"/api/v1/items/{item['id']}", headers=headers).json()
    assert stock["quantity_total"] == stock["quantity_available"] == 3
    movements = client.get("/api/v1/movements", params={"item_id": item["id"]}, headers=headers).json()
    assert movements["total"] == 1


def test_invalid_serial_receipt_rolls_back_purchase_and_stock(inventory_api):
    client, headers = inventory_api
    item = create_item(inventory_api, tracking="serialized")
    serial = f"TEST-{uuid4()}"
    asset = client.post("/api/v1/assets", headers=headers, json={"item_id": item["id"], "serial_number": serial})
    assert asset.status_code == 201, asset.text
    purchase = create_purchase(inventory_api, item, quantity=2)
    url = f"/api/v1/purchases/{purchase['id']}"
    assert client.post(f"{url}/approve", headers=headers, json={}).status_code == 200
    assert client.post(f"{url}/receive", headers=headers, json={"serial_numbers": [serial, f"NEW-{uuid4()}"]}).status_code == 409
    listed = client.get("/api/v1/purchases", headers=headers, params={"item_id": item["id"]}).json()["items"]
    assert listed[0]["status"] == "approved"
    stock = client.get(f"/api/v1/items/{item['id']}", headers=headers).json()
    assert stock["quantity_total"] == stock["quantity_available"] == 1
    assert client.post(f"{url}/receive", headers=headers, json={"serial_numbers": [f"NEW-{uuid4()}", f"NEW-{uuid4()}"]}).status_code == 200


def test_assignment_return_preserves_owned_stock_and_prevents_double_return(inventory_api):
    client, headers = inventory_api
    item = create_item(inventory_api, stock=5)
    result = client.post("/api/v1/assignments", headers=headers, json={
        "item_id": item["id"], "employee_id": str(uuid4()), "employee_name": "کارمند آزمایش", "quantity": 3,
    })
    assert result.status_code == 201, result.text
    assignment = result.json()
    stock = client.get(f"/api/v1/items/{item['id']}", headers=headers).json()
    assert (stock["quantity_total"], stock["quantity_available"]) == (5, 2)
    url = f"/api/v1/assignments/{assignment['id']}/return"
    assert client.post(url, headers=headers, json={}).status_code == 200
    assert client.post(url, headers=headers, json={}).status_code == 409
    stock = client.get(f"/api/v1/items/{item['id']}", headers=headers).json()
    assert stock["quantity_total"] == stock["quantity_available"] == 5
    assert client.get("/api/v1/movements", params={"item_id": item["id"]}, headers=headers).json()["total"] == 3


def test_serial_asset_has_one_custodian_and_retirement_is_terminal(inventory_api):
    client, headers = inventory_api
    item = create_item(inventory_api, tracking="serialized")
    asset = client.post("/api/v1/assets", headers=headers, json={
        "item_id": item["id"], "serial_number": f"SERIAL-{uuid4()}",
    }).json()
    payload = {"asset_id": asset["id"], "employee_id": str(uuid4()), "employee_name": "آزمایشگر", "quantity": 1}
    first = client.post("/api/v1/assignments", headers=headers, json=payload)
    assert first.status_code == 201, first.text
    assert client.post("/api/v1/assignments", headers=headers, json=payload).status_code == 409
    assert client.patch(f"/api/v1/assets/{asset['id']}", headers=headers, json={"status": "retired"}).status_code == 409
    assert client.post(f"/api/v1/assignments/{first.json()['id']}/return", headers=headers, json={}).status_code == 200
    assert client.patch(f"/api/v1/assets/{asset['id']}", headers=headers, json={"status": "retired"}).status_code == 200
    assert client.post("/api/v1/assignments", headers=headers, json=payload).status_code == 409
    assert client.patch(f"/api/v1/assets/{asset['id']}", headers=headers, json={"status": "available"}).status_code == 409
    stock = client.get(f"/api/v1/items/{item['id']}", headers=headers).json()
    assert stock["quantity_available"] == stock["quantity_total"] == 0


def test_outgoing_stock_is_atomic_under_concurrent_requests(inventory_api):
    client, headers = inventory_api
    item = create_item(inventory_api, stock=5)
    payload = {"item_id": item["id"], "type": "out", "quantity": 4, "reason": "مصرف همزمان"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post("/api/v1/movements", headers=headers, json=payload), range(2)))
    assert sorted(result.status_code for result in results) == [201, 409]
    stock = client.get(f"/api/v1/items/{item['id']}", headers=headers).json()
    assert stock["quantity_available"] == stock["quantity_total"] == 1
    assert client.get("/api/v1/movements", params={"item_id": item["id"]}, headers=headers).json()["total"] == 2


def test_concurrent_receipts_create_one_incoming_ledger_entry(inventory_api):
    client, headers = inventory_api
    item = create_item(inventory_api)
    purchase = create_purchase(inventory_api, item, quantity=2)
    url = f"/api/v1/purchases/{purchase['id']}"
    assert client.post(f"{url}/approve", headers=headers, json={}).status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post(f"{url}/receive", headers=headers, json={}), range(2)))
    assert sorted(result.status_code for result in results) == [200, 409]
    stock = client.get(f"/api/v1/items/{item['id']}", headers=headers).json()
    assert stock["quantity_available"] == stock["quantity_total"] == 2
    assert client.get("/api/v1/movements", params={"item_id": item["id"]}, headers=headers).json()["total"] == 1


def test_concurrent_assignments_cannot_take_same_serial_asset(inventory_api):
    client, headers = inventory_api
    item = create_item(inventory_api, tracking="serialized")
    asset = client.post("/api/v1/assets", headers=headers, json={
        "item_id": item["id"], "serial_number": f"RACE-{uuid4()}",
    }).json()
    payload = {"asset_id": asset["id"], "employee_id": str(uuid4()), "employee_name": "آزمون رقابت"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post("/api/v1/assignments", headers=headers, json=payload), range(2)))
    assert sorted(result.status_code for result in results) == [201, 409]
    stock = client.get(f"/api/v1/items/{item['id']}", headers=headers).json()
    assert (stock["quantity_total"], stock["quantity_available"]) == (1, 0)
    loans = client.get("/api/v1/assignments", params={"q": "آزمون رقابت"}, headers=headers).json()
    assert loans["total"] == 1


def test_serial_purchase_quantity_and_numeric_types_are_validated(inventory_api):
    client, headers = inventory_api
    item = create_item(inventory_api, tracking="serialized")
    purchase = create_purchase(inventory_api, item, quantity=2)
    url = f"/api/v1/purchases/{purchase['id']}"
    client.post(f"{url}/approve", headers=headers, json={})
    assert client.post(f"{url}/receive", headers=headers, json={"serial_numbers": ["ONLY-ONE"]}).status_code == 422
    assert client.post(f"{url}/receive", headers=headers, json={"serial_numbers": ["DUPLICATE", "DUPLICATE"]}).status_code == 422
    assert client.post("/api/v1/movements", headers=headers, json={
        "item_id": item["id"], "type": "in", "quantity": 1.5, "reason": "تعداد اعشاری",
    }).status_code == 422
    assert client.post("/api/v1/movements", headers=headers, json={
        "item_id": item["id"], "type": "in", "quantity": True, "reason": "نوع نادرست",
    }).status_code == 422
    assert client.patch(f"/api/v1/items/{item['id']}", headers=headers, json={"min_stock": None}).status_code == 422
    assert client.patch(f"/api/v1/items/{item['id']}", headers=headers, json={"quantity_available": 99}).status_code == 422
    assert client.get("/api/v1/items", params={"page_size": 1000}, headers=headers).status_code == 422
    assert client.get("/api/v1/items", params={"page": 10 ** 30}, headers=headers).status_code == 422
    assert client.get("/api/v1/items", params={"q": "x" * 101}, headers=headers).status_code == 422


def test_asset_form_status_cannot_bypass_custody(inventory_api):
    client, headers = inventory_api
    item = create_item(inventory_api, tracking="serialized")
    result = client.post("/api/v1/assets", headers=headers, json={
        "item_id": item["id"], "serial_number": f"FORM-{uuid4()}", "status": "available",
    })
    assert result.status_code == 201, result.text
    asset = result.json()
    assert client.patch(f"/api/v1/assets/{asset['id']}", headers=headers, json={"status": "assigned"}).status_code == 409
    loan = client.post("/api/v1/assignments", headers=headers, json={
        "asset_id": asset["id"], "employee_id": str(uuid4()), "employee_name": "کارمند آزمون",
    })
    assert loan.status_code == 201, loan.text
    edited = client.patch(f"/api/v1/assets/{asset['id']}", headers=headers, json={"status": "assigned", "notes": "برچسب جدید"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["status"] == "assigned"
    assert edited.json()["notes"] == "برچسب جدید"
    assert client.patch(f"/api/v1/assets/{asset['id']}", headers=headers, json={"status": "available"}).status_code == 409


def test_purchase_total_is_exact_for_web_clients(inventory_api):
    client, headers = inventory_api
    item = create_item(inventory_api)
    supplier = client.post("/api/v1/suppliers", headers=headers, json={"name": "تأمین‌کننده آزمون سقف"}).json()
    result = client.post("/api/v1/purchases", headers=headers, json={
        "item_id": item["id"], "supplier_id": supplier["id"], "quantity": 1_000_000, "unit_price": 1_000_000_000_000,
    })
    assert result.status_code == 422


def test_staff_can_read_catalog_but_cannot_read_or_change_operations(clients, staff_headers):
    client = clients["inventory"]
    headers = staff_headers["inventory"]
    assert client.get("/api/v1/items", headers=headers).status_code == 200
    assert client.get("/api/v1/dashboard", headers=headers).status_code == 200
    for endpoint in ("purchases", "assignments", "movements", "suppliers", "assets", "reports/stock"):
        assert client.get(f"/api/v1/{endpoint}", headers=headers).status_code == 403
    assert client.post("/api/v1/items", headers=headers, json={
        "sku": "STAFF-DENIED", "name": "غیرمجاز", "category": "آزمون",
    }).status_code == 403
    assert client.get("/api/v1/items").status_code == 401


def assert_reconciled(client):
    """Independently derive balances from the immutable ledger and open loans."""
    with client.app.state.SessionLocal() as db:
        for item in db.scalars(select(Item)):
            movements = db.scalars(select(Movement).where(Movement.item_id == item.id)).all()
            available_from_ledger = sum(row.quantity if row.type == "in" else -row.quantity for row in movements)
            open_loans = db.scalars(select(Assignment).where(Assignment.item_id == item.id, Assignment.status == "active")).all()
            assert item.quantity_available == available_from_ledger
            assert item.quantity_total == item.quantity_available + sum(row.quantity for row in open_loans)
            if item.tracking_type == "serialized":
                assets = db.scalars(select(Asset).where(Asset.item_id == item.id)).all()
                assert item.quantity_total == sum(asset.status != "retired" for asset in assets)
                assert item.quantity_available == sum(asset.status == "available" for asset in assets)
                for movement in movements:
                    assert len(movement.serial_numbers) == movement.quantity
                for asset in assets:
                    if asset.status == "assigned":
                        loan = db.get(Assignment, asset.current_assignment_id)
                        assert loan is not None and loan.status == "active" and loan.asset_id == asset.id
                    else:
                        assert asset.current_assignment_id is None


def test_stock_ledger_reconciles_after_mixed_workflows(inventory_api):
    client, headers = inventory_api
    quantity_item = create_item(inventory_api, stock=12)
    serial_item = create_item(inventory_api, tracking="serialized")
    serials = [f"LEDGER-{uuid4()}" for _ in range(2)]
    incoming = client.post("/api/v1/movements", headers=headers, json={
        "item_id": serial_item["id"], "type": "in", "quantity": 2, "reason": "خرید اولیه", "serial_numbers": serials,
    })
    assert incoming.status_code == 201, incoming.text
    assert client.post("/api/v1/movements", headers=headers, json={
        "item_id": quantity_item["id"], "type": "out", "quantity": 3, "reason": "مصرف اداری",
    }).status_code == 201
    payload = {"employee_id": str(uuid4()), "employee_name": "کارمند کنترل مانده"}
    loan = client.post("/api/v1/assignments", headers=headers, json={**payload, "item_id": quantity_item["id"], "quantity": 4})
    assert loan.status_code == 201, loan.text
    assert_reconciled(client)
    assert client.post(f"/api/v1/assignments/{loan.json()['id']}/return", headers=headers, json={}).status_code == 200
    assets = client.get("/api/v1/assets", headers=headers, params={"item_id": serial_item["id"]}).json()["items"]
    serial_loan = client.post("/api/v1/assignments", headers=headers, json={**payload, "asset_id": assets[0]["id"]})
    assert serial_loan.status_code == 201, serial_loan.text
    assert_reconciled(client)
    assert client.post(f"/api/v1/assignments/{serial_loan.json()['id']}/return", headers=headers, json={}).status_code == 200
    assert client.patch(f"/api/v1/assets/{assets[0]['id']}", headers=headers, json={"status": "retired"}).status_code == 200
    assert_reconciled(client)


def test_reseeding_after_user_renames_preserves_records_and_balances(inventory_api):
    from services.inventory.seed import seed
    client, headers = inventory_api
    items = client.get("/api/v1/items", headers=headers).json()["items"]
    supplier = client.get("/api/v1/suppliers", headers=headers).json()["items"][0]
    for item in items:
        result = client.patch(f"/api/v1/items/{item['id']}", headers=headers, json={"sku": f"RENAMED-{item['sku']}", "name": "نام ویرایش‌شده"})
        assert result.status_code == 200, result.text
    assert client.patch(f"/api/v1/suppliers/{supplier['id']}", headers=headers, json={"name": "تأمین‌کننده ویرایش‌شده"}).status_code == 200
    with client.app.state.SessionLocal() as db:
        models = (Item, Supplier, Asset, Assignment, Purchase, Movement)
        before = {model: db.scalar(select(func.count()).select_from(model)) for model in models}
        seed(db)
        db.commit()
        seed(db)
        db.commit()
        after = {model: db.scalar(select(func.count()).select_from(model)) for model in models}
        assert before == after
        assert db.get(Supplier, supplier["id"]).name == "تأمین‌کننده ویرایش‌شده"
        assert all(db.get(Item, item["id"]).sku.startswith("RENAMED-") for item in items)
    assert_reconciled(client)


def test_seed_receipt_precedes_assignment_in_ledger(clients):
    client = clients["inventory"]
    assert_reconciled(client)
    with client.app.state.SessionLocal() as db:
        for item in db.scalars(select(Item)):
            running = 0
            for movement in db.scalars(select(Movement).where(Movement.item_id == item.id).order_by(Movement.created_at)):
                running += movement.quantity if movement.type == "in" else -movement.quantity
                assert running >= 0


def test_search_serial_sku_and_literal_wildcards(inventory_api):
    client, headers = inventory_api
    item = create_item(inventory_api, tracking="serialized")
    serial = f"SER_%_{uuid4().hex}"
    asset = client.post("/api/v1/assets", headers=headers, json={"item_id": item["id"], "serial_number": serial}).json()
    loan = client.post("/api/v1/assignments", headers=headers, json={
        "asset_id": asset["id"], "employee_id": str(uuid4()), "employee_name": "پرسنل جست‌وجو",
    })
    assert loan.status_code == 201, loan.text
    for endpoint in ("assets", "assignments", "movements"):
        result = client.get(f"/api/v1/{endpoint}", headers=headers, params={"q": serial}).json()
        assert result["total"] >= 1
        result = client.get(f"/api/v1/{endpoint}", headers=headers, params={"q": item["sku"]}).json()
        assert result["total"] >= 1
    # A percent sign in user input is literal, not a request to match every row.
    result = client.get("/api/v1/assets", headers=headers, params={"q": "%"}).json()
    assert result["total"] == 1 and result["items"][0]["id"] == asset["id"]


@pytest.mark.parametrize("serial", ["رایانه-۱۲۳", 'SN-"quoted"', "SN-back\\slash"])
def test_movement_search_uses_decoded_json_serial_values(inventory_api, serial):
    client, headers = inventory_api
    item = create_item(inventory_api, tracking="serialized")
    unique_serial = f"{serial}-{uuid4().hex[:8]}"
    response = client.post("/api/v1/assets", headers=headers, json={"item_id": item["id"], "serial_number": unique_serial})
    assert response.status_code == 201, response.text
    result = client.get("/api/v1/movements", headers=headers, params={"q": unique_serial}).json()
    assert result["total"] == 1
    assert result["items"][0]["serial_numbers"] == [unique_serial]


@pytest.mark.parametrize("endpoint,param", [("purchases", "status"), ("assets", "status"), ("assignments", "status"), ("movements", "type")])
def test_invalid_filters_are_rejected(inventory_api, endpoint, param):
    client, headers = inventory_api
    result = client.get(f"/api/v1/{endpoint}", headers=headers, params={param: "invalid"})
    assert result.status_code == 422


def test_pagination_has_stable_tie_break_and_filtered_total(inventory_api):
    client, headers = inventory_api
    tag = f"PAGE-{uuid4().hex[:8]}"
    ids = []
    for _ in range(3):
        item = create_item(inventory_api)
        ids.append(item["id"])
        assert client.patch(f"/api/v1/items/{item['id']}", headers=headers, json={"name": tag}).status_code == 200
    with client.app.state.SessionLocal() as db:
        for item_id in ids:
            db.get(Item, item_id).created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        db.commit()
    fetched = []
    for page in (1, 2, 3):
        result = client.get("/api/v1/items", headers=headers, params={"q": tag, "page": page, "page_size": 1}).json()
        assert result["total"] == 3 and result["page"] == page
        fetched.append(result["items"][0]["id"])
    assert fetched == sorted(ids, reverse=True)
    assert client.get("/api/v1/items", headers=headers, params={"q": tag, "page": 4, "page_size": 1}).json()["items"] == []


def test_cumulative_stock_ceiling_rolls_back_receipt_and_purchase(inventory_api):
    client, headers = inventory_api
    item = create_item(inventory_api)
    with client.app.state.SessionLocal() as db:
        row = db.get(Item, item["id"])
        row.quantity_available = row.quantity_total = MAX_STOCK - 1
        db.add(Movement(item_id=row.id, type="in", quantity=MAX_STOCK - 1, reason="مانده آغاز آزمون سقف", reference="", serial_numbers=[]))
        db.commit()
    purchase = create_purchase(inventory_api, item, quantity=2)
    url = f"/api/v1/purchases/{purchase['id']}"
    assert client.post(f"{url}/approve", headers=headers, json={}).status_code == 200
    assert client.post(f"{url}/receive", headers=headers, json={}).status_code == 409
    listed = client.get("/api/v1/purchases", headers=headers, params={"item_id": item["id"]}).json()["items"]
    assert listed[0]["status"] == "approved"
    assert client.post("/api/v1/movements", headers=headers, json={
        "item_id": item["id"], "type": "in", "quantity": 2, "reason": "بیش از سقف",
    }).status_code == 409
    assert client.get(f"/api/v1/items/{item['id']}", headers=headers).json()["quantity_total"] == MAX_STOCK - 1
    assert_reconciled(client)


def test_cancelled_purchase_cannot_approve_receive_or_cancel_again(inventory_api):
    client, headers = inventory_api
    item = create_item(inventory_api)
    purchase = create_purchase(inventory_api, item)
    url = f"/api/v1/purchases/{purchase['id']}"
    assert client.post(f"{url}/cancel", headers=headers, json={}).status_code == 200
    for action in ("approve", "receive", "cancel"):
        assert client.post(f"{url}/{action}", headers=headers, json={}).status_code == 409
    assert client.get(f"/api/v1/items/{item['id']}", headers=headers).json()["quantity_total"] == 0
    assert client.get("/api/v1/movements", headers=headers, params={"item_id": item["id"]}).json()["total"] == 0


@pytest.mark.parametrize("email", ["@example.com", "a@@example.com", "a@example", "a b@example.com"])
def test_supplier_email_validation_on_create_and_patch(inventory_api, email):
    client, headers = inventory_api
    result = client.post("/api/v1/suppliers", headers=headers, json={"name": "آزمون ایمیل", "email": email})
    assert result.status_code == 422
    supplier = client.post("/api/v1/suppliers", headers=headers, json={"name": "نمونه معتبر", "email": "qa+inventory@example.com"}).json()
    assert client.patch(f"/api/v1/suppliers/{supplier['id']}", headers=headers, json={"email": email}).status_code == 422


def test_dashboard_dates_are_explicit_utc(inventory_api):
    client, headers = inventory_api
    result = client.get("/api/v1/dashboard", headers=headers).json()
    assert result["recent"]
    assert all(datetime.fromisoformat(row["date"]).utcoffset() == timedelta(0) for row in result["recent"])


def test_stock_report_filter_and_assignment_balance(inventory_api):
    client, headers = inventory_api
    item = create_item(inventory_api, stock=4)
    employee_id = str(uuid4())
    loan = client.post("/api/v1/assignments", headers=headers, json={
        "item_id": item["id"], "quantity": 3, "employee_id": employee_id, "employee_name": "آزمون گزارش",
    })
    assert loan.status_code == 201, loan.text
    result = client.get("/api/v1/reports/stock", headers=headers, params={"q": item["sku"], "low_stock": True, "page_size": 1}).json()
    assert result["total"] == 1 and result["page_size"] == 1
    row = result["items"][0]
    assert row["id"] == item["id"] and row["quantity_total"] == 4
    assert row["quantity_available"] == 1 and row["quantity_assigned"] == 3 and row["is_low_stock"] is True
    loans = client.get("/api/v1/assignments", headers=headers, params={"employee_id": employee_id, "status": "active"}).json()
    assert loans["total"] == 1 and loans["items"][0]["id"] == loan.json()["id"]
    assert client.post(f"/api/v1/assignments/{loan.json()['id']}/return", headers=headers, json={}).status_code == 200
    assert client.get("/api/v1/reports/stock", headers=headers, params={"q": item["sku"], "low_stock": True}).json()["total"] == 0
    returned = client.get("/api/v1/assignments", headers=headers, params={"employee_id": employee_id, "status": "returned"}).json()
    assert returned["total"] == 1
    assert_reconciled(client)


def test_every_inventory_write_requires_manager_and_manager_can_operate(inventory_api, staff_headers):
    client, admin_headers = inventory_api
    item = create_item(inventory_api, stock=5)
    serialized = create_item(inventory_api, tracking="serialized")
    asset = client.post("/api/v1/assets", headers=admin_headers, json={"item_id": serialized["id"], "serial_number": f"RBAC-{uuid4()}"}).json()
    purchase = create_purchase(inventory_api, item)
    loan = client.post("/api/v1/assignments", headers=admin_headers, json={
        "item_id": item["id"], "employee_id": str(uuid4()), "employee_name": "دسترسی آزمون", "quantity": 1,
    }).json()
    writes = [
        ("post", "/items", {"sku": f"DENIED-{uuid4()}", "name": "کالا", "category": "آزمون"}),
        ("patch", f"/items/{item['id']}", {"name": "غیرمجاز"}),
        ("post", "/suppliers", {"name": "غیرمجاز"}),
        ("patch", f"/suppliers/{purchase['supplier_id']}", {"name": "غیرمجاز"}),
        ("post", "/purchases", {"supplier_id": purchase["supplier_id"], "item_id": item["id"], "quantity": 1, "unit_price": 0}),
        ("post", f"/purchases/{purchase['id']}/approve", {}),
        ("post", f"/purchases/{purchase['id']}/receive", {}),
        ("post", f"/purchases/{purchase['id']}/cancel", {}),
        ("post", "/movements", {"item_id": item["id"], "type": "in", "quantity": 1, "reason": "غیرمجاز"}),
        ("post", "/assets", {"item_id": serialized["id"], "serial_number": f"DENIED-{uuid4()}"}),
        ("patch", f"/assets/{asset['id']}", {"notes": "غیرمجاز"}),
        ("post", "/assignments", {"asset_id": asset["id"], "employee_id": str(uuid4()), "employee_name": "غیرمجاز"}),
        ("post", f"/assignments/{loan['id']}/return", {}),
    ]
    for method, path, payload in writes:
        response = getattr(client, method)("/api/v1" + path, headers=staff_headers["inventory"], json=payload)
        assert response.status_code == 403, (path, response.text)
        response = getattr(client, method)("/api/v1" + path, json=payload)
        assert response.status_code == 401, (path, response.text)
    logged = client.post("/api/v1/auth/login", json={"username": "manager", "password": "manager12345"})
    assert logged.status_code == 200, logged.text
    manager = {"Authorization": f"Bearer {logged.json()['access_token']}"}
    for endpoint in ("items", "suppliers", "purchases", "movements", "assets", "assignments", "reports/stock", "dashboard"):
        assert client.get(f"/api/v1/{endpoint}", headers=manager).status_code == 200
    assert client.post(f"/api/v1/purchases/{purchase['id']}/approve", headers=manager, json={}).status_code == 200
    assert_reconciled(client)


def test_receive_and_cancel_race_has_one_consistent_outcome(inventory_api):
    client, headers = inventory_api
    item = create_item(inventory_api)
    purchase = create_purchase(inventory_api, item, quantity=2)
    url = f"/api/v1/purchases/{purchase['id']}"
    assert client.post(f"{url}/approve", headers=headers, json={}).status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda action: client.post(f"{url}/{action}", headers=headers, json={}), ("receive", "cancel")))
    assert sorted(result.status_code for result in results) == [200, 409]
    row = client.get("/api/v1/purchases", headers=headers, params={"item_id": item["id"]}).json()["items"][0]
    stock = client.get(f"/api/v1/items/{item['id']}", headers=headers).json()
    assert stock["quantity_total"] == (2 if row["status"] == "received" else 0)
    assert (row["received_at"] is not None) == (row["status"] == "received")
    assert_reconciled(client)


def test_legacy_demo_random_ids_can_be_reseeded_after_renaming(clients):
    """Existing laptop data predates stable IDs; preserve it on a code upgrade."""
    from services.inventory.seed import seed
    client = clients["inventory"]
    with client.app.state.SessionLocal() as db:
        for model in (Purchase, Movement, Assignment, Asset, Item, Supplier):
            db.query(model).delete(synchronize_session=False)
        supplier = Supplier(id=str(uuid4()), name="نام قدیمی ویرایش‌شده", contact_name="", phone="", email="", address="")
        db.add(supplier)
        db.flush()
        item = Item(id=str(uuid4()), sku="LEGACY-RENAMED", name="لپ‌تاپ قدیمی", category="آزمون", unit="عدد",
                    tracking_type="serialized", min_stock=0, description="", quantity_total=1, quantity_available=1)
        db.add(item)
        db.flush()
        db.add(Asset(item_id=item.id, serial_number="DEMO-LAP-001-001", status="available", notes=""))
        db.add(Movement(item_id=item.id, type="in", quantity=1, reason="داده قدیمی", reference="DEMO-INITIAL-LAP-001", serial_numbers=["DEMO-LAP-001-001"]))
        db.add(Purchase(item_id=item.id, supplier_id=supplier.id, quantity=1, unit_price=1, notes="قدیمی", status="pending"))
        db.commit()
        seed(db)
        db.commit()
        assert db.scalar(select(func.count()).select_from(Supplier)) == 1
        assert db.scalar(select(func.count()).select_from(Item)) == 4
        assert db.get(Item, item.id).sku == "LEGACY-RENAMED"
    assert_reconciled(client)
