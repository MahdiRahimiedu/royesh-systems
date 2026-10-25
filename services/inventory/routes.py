"""Inventory API: all stock changes and their ledger entries commit together.

Conditional UPDATE statements prevent two requests from spending the same stock,
receiving the same purchase, assigning the same asset, or returning a loan twice.
"""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, column, func, or_, select, update
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import current_user, require_manager
from shared.database import get_db
from shared.utils import serialize

from .models import Asset, Assignment, Item, Movement, Purchase, Supplier
from .schemas import (
    AssetCreate, AssetPatch, AssignmentCreate, Empty, ItemCreate, ItemPatch,
    MovementCreate, PurchaseCreate, SerialNumbers, SupplierCreate, SupplierPatch,
)

router = APIRouter(prefix="/api/v1")
MAX_STOCK = 1_000_000_000  # Fits PostgreSQL INTEGER and exact browser arithmetic.


def now():
    return datetime.now(timezone.utc)


def record(db, model, record_id, label):
    obj = db.get(model, str(record_id))
    if obj is None:
        raise HTTPException(404, f"{label} پیدا نشد")
    return obj


def page_result(db, statement, page, page_size, enrich=None):
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    model = statement.column_descriptions[0]["entity"]
    rows = db.scalars(statement.order_by(model.created_at.desc(), model.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [enrich(row) if enrich else serialize(row) for row in rows],
            "total": total, "page": page, "page_size": page_size}


def search(statement, q, *columns, extra_conditions=()):
    if q:
        statement = statement.where(or_(*(col.contains(q.strip(), autoescape=True) for col in columns), *extra_conditions))
    return statement


def stock_change(db, item_id, available_delta, total_delta=0):
    """The check and write are one SQL statement, even under concurrent requests."""
    result = db.execute(update(Item).where(
        Item.id == item_id,
        Item.quantity_available + available_delta >= 0,
        Item.quantity_total + total_delta >= Item.quantity_available + available_delta,
        Item.quantity_total + total_delta <= MAX_STOCK,
    ).values(quantity_available=Item.quantity_available + available_delta,
             quantity_total=Item.quantity_total + total_delta, updated_at=now())
      .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        detail = ("موجودی کل هر کالا نمی‌تواند از یک میلیارد واحد بیشتر شود"
                  if total_delta > 0 else "موجودی قابل استفاده برای این عملیات کافی نیست")
        raise HTTPException(409, detail)


def ledger(db, item_id, kind, quantity, reason, reference="", serial_numbers=None):
    db.add(Movement(item_id=item_id, type=kind, quantity=quantity, reason=reason,
                    reference=reference, serial_numbers=serial_numbers or []))


def add_serials(db, item, serials, quantity):
    if item.tracking_type == "serialized":
        if len(serials) != quantity:
            raise HTTPException(422, "برای هر تجهیز دقیقاً یک شماره سریال وارد کنید")
        if db.scalar(select(Asset.id).where(Asset.serial_number.in_(serials)).limit(1)):
            raise HTTPException(409, "حداقل یکی از شماره سریال‌ها قبلاً ثبت شده است")
        for serial in serials:
            db.add(Asset(item_id=item.id, serial_number=serial, status="available", notes=""))
    elif serials:
        raise HTTPException(422, "کالای تعدادی شماره سریال ندارد")


def purchase_view(db, row):
    return serialize(row, item_name=record(db, Item, row.item_id, "کالا").name,
                     supplier_name=record(db, Supplier, row.supplier_id, "تأمین‌کننده").name,
                     total_amount=row.quantity * row.unit_price)


def asset_view(db, row):
    item = record(db, Item, row.item_id, "کالا")
    return serialize(row, item_name=item.name, sku=item.sku)


def assignment_view(db, row):
    asset = db.get(Asset, row.asset_id) if row.asset_id else None
    return serialize(row, item_name=record(db, Item, row.item_id, "کالا").name,
                     serial_number=asset.serial_number if asset else None)


@router.get("/items", tags=["کالاها"])
def list_items(q: str = Query("", max_length=100), page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100),
               db: Session = Depends(get_db), user=Depends(current_user)):
    return page_result(db, search(select(Item), q, Item.name, Item.sku, Item.category), page, page_size)


@router.post("/items", status_code=201, tags=["کالاها"])
def create_item(body: ItemCreate, db: Session = Depends(get_db), user=Depends(require_manager)):
    if db.scalar(select(Item.id).where(Item.sku == body.sku)):
        raise HTTPException(409, "کد کالا قبلاً ثبت شده است")
    obj = Item(**body.model_dump())
    db.add(obj)
    db.flush()
    log_action(db, user, "create", "item", obj.id, obj.name)
    db.commit()
    db.refresh(obj)
    return serialize(obj)


@router.get("/items/{item_id}", tags=["کالاها"])
def get_item(item_id: str, db: Session = Depends(get_db), user=Depends(current_user)):
    return serialize(record(db, Item, item_id, "کالا"))


@router.patch("/items/{item_id}", tags=["کالاها"])
def patch_item(item_id: str, body: ItemPatch, db: Session = Depends(get_db), user=Depends(require_manager)):
    obj = record(db, Item, item_id, "کالا")
    values = body.model_dump(exclude_unset=True)
    if "tracking_type" in values and values["tracking_type"] != obj.tracking_type:
        raise HTTPException(409, "روش رهگیری کالا قابل تغییر نیست؛ کالای جدید تعریف کنید")
    if "sku" in values and db.scalar(select(Item.id).where(Item.sku == values["sku"], Item.id != obj.id)):
        raise HTTPException(409, "کد کالا قبلاً ثبت شده است")
    for key, value in values.items():
        setattr(obj, key, value)
    log_action(db, user, "update", "item", obj.id, obj.name)
    db.commit()
    db.refresh(obj)
    return serialize(obj)


@router.get("/suppliers", tags=["تأمین‌کنندگان"])
def list_suppliers(q: str = Query("", max_length=100), page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100),
                   db: Session = Depends(get_db), user=Depends(require_manager)):
    return page_result(db, search(select(Supplier), q, Supplier.name, Supplier.contact_name, Supplier.phone), page, page_size)


@router.post("/suppliers", status_code=201, tags=["تأمین‌کنندگان"])
def create_supplier(body: SupplierCreate, db: Session = Depends(get_db), user=Depends(require_manager)):
    obj = Supplier(**body.model_dump())
    db.add(obj)
    db.flush()
    log_action(db, user, "create", "supplier", obj.id, obj.name)
    db.commit()
    db.refresh(obj)
    return serialize(obj)


@router.patch("/suppliers/{supplier_id}", tags=["تأمین‌کنندگان"])
def patch_supplier(supplier_id: str, body: SupplierPatch, db: Session = Depends(get_db), user=Depends(require_manager)):
    obj = record(db, Supplier, supplier_id, "تأمین‌کننده")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    log_action(db, user, "update", "supplier", obj.id, obj.name)
    db.commit()
    db.refresh(obj)
    return serialize(obj)


@router.get("/purchases", tags=["خرید"])
def list_purchases(q: str = Query("", max_length=100), status: Literal["pending", "approved", "received", "cancelled"] | None = None, item_id: str | None = None,
                   page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100),
                   db: Session = Depends(get_db), user=Depends(require_manager)):
    statement = select(Purchase).join(Item).join(Supplier, Purchase.supplier_id == Supplier.id)
    statement = search(statement, q, Item.name, Item.sku, Supplier.name, Purchase.notes)
    if status:
        statement = statement.where(Purchase.status == status)
    if item_id:
        statement = statement.where(Purchase.item_id == item_id)
    return page_result(db, statement, page, page_size, lambda row: purchase_view(db, row))


@router.post("/purchases", status_code=201, tags=["خرید"])
def create_purchase(body: PurchaseCreate, db: Session = Depends(get_db), user=Depends(require_manager)):
    record(db, Supplier, body.supplier_id, "تأمین‌کننده")
    item = record(db, Item, body.item_id, "کالا")
    if item.tracking_type == "serialized" and body.quantity > 10_000:
        raise HTTPException(422, "هر سفارش تجهیز سریال‌دار حداکثر ۱۰ هزار تجهیز دارد")
    obj = Purchase(**body.model_dump(mode="json"), status="pending")
    db.add(obj)
    db.flush()
    log_action(db, user, "create", "purchase", obj.id)
    db.commit()
    db.refresh(obj)
    return purchase_view(db, obj)


@router.post("/purchases/{purchase_id}/approve", tags=["خرید"])
def approve_purchase(purchase_id: str, body: Empty, db: Session = Depends(get_db), user=Depends(require_manager)):
    obj = record(db, Purchase, purchase_id, "خرید")
    result = db.execute(update(Purchase).where(Purchase.id == purchase_id, Purchase.status == "pending")
                        .values(status="approved", updated_at=now()).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, "فقط درخواست خرید در انتظار قابل تأیید است")
    log_action(db, user, "approve", "purchase", obj.id)
    db.commit()
    db.refresh(obj)
    return purchase_view(db, obj)


@router.post("/purchases/{purchase_id}/cancel", tags=["خرید"])
def cancel_purchase(purchase_id: str, body: Empty, db: Session = Depends(get_db), user=Depends(require_manager)):
    obj = record(db, Purchase, purchase_id, "خرید")
    result = db.execute(update(Purchase).where(Purchase.id == purchase_id, Purchase.status.in_(["pending", "approved"]))
                        .values(status="cancelled", updated_at=now()).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, "خرید دریافت‌شده یا لغوشده قابل لغو نیست")
    log_action(db, user, "cancel", "purchase", obj.id)
    db.commit()
    db.refresh(obj)
    return purchase_view(db, obj)


@router.post("/purchases/{purchase_id}/receive", tags=["خرید"])
def receive_purchase(purchase_id: str, body: SerialNumbers, db: Session = Depends(get_db), user=Depends(require_manager)):
    obj = record(db, Purchase, purchase_id, "خرید")
    result = db.execute(update(Purchase).where(Purchase.id == purchase_id, Purchase.status == "approved")
                        .values(status="received", received_at=now(), updated_at=now())
                        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, "خرید باید تأیید شده باشد و فقط یک بار دریافت می‌شود")
    item = record(db, Item, obj.item_id, "کالا")
    add_serials(db, item, body.serial_numbers, obj.quantity)
    stock_change(db, item.id, obj.quantity, obj.quantity)
    ledger(db, item.id, "in", obj.quantity, "دریافت سفارش خرید", obj.id, body.serial_numbers)
    log_action(db, user, "receive", "purchase", obj.id)
    db.commit()
    db.refresh(obj)
    return purchase_view(db, obj)


@router.get("/movements", tags=["گردش کالا"])
def list_movements(q: str = Query("", max_length=100), type: Literal["in", "out"] | None = None, item_id: str | None = None,
                   page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100),
                   db: Session = Depends(get_db), user=Depends(require_manager)):
    # Search decoded JSON values: a text cast misses Persian/quoted serials.
    serial_conditions = []
    if q:
        expand = func.json_each if db.get_bind().dialect.name == "sqlite" else func.json_array_elements_text
        serials = expand(Movement.serial_numbers).table_valued(column("value", String))
        serial_conditions.append(select(1).select_from(serials)
                                 .where(serials.c.value.contains(q.strip(), autoescape=True))
                                 .correlate(Movement).exists())
    statement = search(select(Movement).join(Item), q, Item.name, Item.sku, Movement.reason,
                       Movement.reference, extra_conditions=serial_conditions)
    if type:
        statement = statement.where(Movement.type == type)
    if item_id:
        statement = statement.where(Movement.item_id == item_id)
    return page_result(db, statement, page, page_size,
                       lambda row: serialize(row, item_name=record(db, Item, row.item_id, "کالا").name))


@router.post("/movements", status_code=201, tags=["گردش کالا"])
def create_movement(body: MovementCreate, db: Session = Depends(get_db), user=Depends(require_manager)):
    item = record(db, Item, body.item_id, "کالا")
    if body.type == "out" and item.tracking_type == "serialized":
        raise HTTPException(422, "خروج تجهیز سریال‌دار از طریق تحویل تجهیز یا اسقاط ثبت می‌شود")
    if body.type == "out" and body.serial_numbers:
        raise HTTPException(422, "خروج کالای تعدادی شماره سریال ندارد")
    if body.type == "in":
        add_serials(db, item, body.serial_numbers, body.quantity)
    sign = 1 if body.type == "in" else -1
    stock_change(db, item.id, sign * body.quantity, sign * body.quantity)
    obj = Movement(**body.model_dump(mode="json"))
    db.add(obj)
    db.flush()
    log_action(db, user, "create", "movement", obj.id, body.reason)
    db.commit()
    db.refresh(obj)
    return serialize(obj, item_name=item.name)


@router.get("/assets", tags=["تجهیزات"])
def list_assets(q: str = Query("", max_length=100), status: Literal["available", "assigned", "retired"] | None = None, item_id: str | None = None,
                page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100),
                db: Session = Depends(get_db), user=Depends(require_manager)):
    statement = search(select(Asset).join(Item), q, Item.name, Item.sku, Asset.serial_number, Asset.notes)
    if status:
        statement = statement.where(Asset.status == status)
    if item_id:
        statement = statement.where(Asset.item_id == item_id)
    return page_result(db, statement, page, page_size, lambda row: asset_view(db, row))


@router.post("/assets", status_code=201, tags=["تجهیزات"])
def create_asset(body: AssetCreate, db: Session = Depends(get_db), user=Depends(require_manager)):
    item = record(db, Item, body.item_id, "کالا")
    if item.tracking_type != "serialized":
        raise HTTPException(422, "فقط کالای سریال‌دار می‌تواند تجهیز مستقل داشته باشد")
    if db.scalar(select(Asset.id).where(Asset.serial_number == body.serial_number)):
        raise HTTPException(409, "شماره سریال قبلاً ثبت شده است")
    obj = Asset(**body.model_dump(mode="json"))
    db.add(obj)
    stock_change(db, item.id, 1, 1)
    db.flush()
    ledger(db, item.id, "in", 1, "ثبت تجهیز اولیه", obj.id, [obj.serial_number])
    log_action(db, user, "create", "asset", obj.id, obj.serial_number)
    db.commit()
    db.refresh(obj)
    return asset_view(db, obj)


@router.patch("/assets/{asset_id}", tags=["تجهیزات"])
def patch_asset(asset_id: str, body: AssetPatch, db: Session = Depends(get_db), user=Depends(require_manager)):
    obj = record(db, Asset, asset_id, "تجهیز")
    values = body.model_dump(exclude_unset=True)
    if "status" in values and values["status"] != obj.status:
        if values["status"] != "retired":
            raise HTTPException(409, "تغییر وضعیت تجهیز فقط از مسیر تحویل، بازگشت یا اسقاط انجام می‌شود")
        result = db.execute(update(Asset).where(Asset.id == asset_id, Asset.status == "available")
                            .values(status="retired", updated_at=now()).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise HTTPException(409, "فقط تجهیز موجود در انبار قابل اسقاط است؛ ابتدا بازگشت را ثبت کنید")
        stock_change(db, obj.item_id, -1, -1)
        ledger(db, obj.item_id, "out", 1, "اسقاط تجهیز", obj.id, [obj.serial_number])
    if "notes" in values:
        obj.notes = values["notes"]
    log_action(db, user, "update", "asset", obj.id)
    db.commit()
    db.refresh(obj)
    return asset_view(db, obj)


@router.get("/assignments", tags=["تحویل و بازگشت"])
def list_assignments(q: str = Query("", max_length=100), status: Literal["active", "returned"] | None = None, employee_id: str | None = None,
                     page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100),
                     db: Session = Depends(get_db), user=Depends(require_manager)):
    statement = search(select(Assignment).join(Item).outerjoin(Asset, Assignment.asset_id == Asset.id),
                       q, Item.name, Item.sku, Assignment.employee_name, Assignment.employee_id,
                       Assignment.notes, Asset.serial_number)
    if status:
        statement = statement.where(Assignment.status == status)
    if employee_id:
        statement = statement.where(Assignment.employee_id == employee_id)
    return page_result(db, statement, page, page_size, lambda row: assignment_view(db, row))


@router.post("/assignments", status_code=201, tags=["تحویل و بازگشت"])
def create_assignment(body: AssignmentCreate, db: Session = Depends(get_db), user=Depends(require_manager)):
    assignment_id = str(uuid4())
    serials = []
    if body.asset_id:
        asset = record(db, Asset, body.asset_id, "تجهیز")
        item = record(db, Item, asset.item_id, "کالا")
        changed = db.execute(update(Asset).where(Asset.id == asset.id, Asset.status == "available")
                             .values(status="assigned", current_assignment_id=assignment_id, updated_at=now())
                             .execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            raise HTTPException(409, "این تجهیز موجود نیست یا قبلاً تحویل داده شده است")
        serials = [asset.serial_number]
    else:
        item = record(db, Item, body.item_id, "کالا")
        if item.tracking_type != "quantity":
            raise HTTPException(422, "برای کالای سریال‌دار باید asset_id تجهیز را انتخاب کنید")
    stock_change(db, item.id, -body.quantity)
    obj = Assignment(id=assignment_id, asset_id=str(body.asset_id) if body.asset_id else None,
                     item_id=item.id, employee_id=str(body.employee_id), employee_name=body.employee_name,
                     quantity=body.quantity, notes=body.notes, status="active")
    db.add(obj)
    ledger(db, item.id, "out", obj.quantity, f"تحویل به {obj.employee_name}", obj.id, serials)
    log_action(db, user, "assign", "assignment", obj.id, obj.employee_name)
    db.commit()
    db.refresh(obj)
    return assignment_view(db, obj)


@router.post("/assignments/{assignment_id}/return", tags=["تحویل و بازگشت"])
def return_assignment(assignment_id: str, body: Empty, db: Session = Depends(get_db), user=Depends(require_manager)):
    obj = record(db, Assignment, assignment_id, "تحویل")
    result = db.execute(update(Assignment).where(Assignment.id == assignment_id, Assignment.status == "active")
                        .values(status="returned", returned_at=now(), updated_at=now())
                        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, "بازگشت این تحویل قبلاً ثبت شده است")
    serials = []
    if obj.asset_id:
        asset = record(db, Asset, obj.asset_id, "تجهیز")
        changed = db.execute(update(Asset).where(Asset.id == asset.id, Asset.status == "assigned",
                                                Asset.current_assignment_id == obj.id)
                             .values(status="available", current_assignment_id=None, updated_at=now())
                             .execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            raise HTTPException(409, "وضعیت تجهیز با این تحویل سازگار نیست")
        serials = [asset.serial_number]
    stock_change(db, obj.item_id, obj.quantity)
    ledger(db, obj.item_id, "in", obj.quantity, f"بازگشت از {obj.employee_name}", obj.id, serials)
    log_action(db, user, "return", "assignment", obj.id)
    db.commit()
    db.refresh(obj)
    return assignment_view(db, obj)


@router.get("/reports/stock", tags=["گزارش‌ها"])
def stock_report(q: str = Query("", max_length=100), low_stock: bool = False, page: int = Query(1, ge=1, le=1_000_000),
                 page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db),
                 user=Depends(require_manager)):
    statement = search(select(Item), q, Item.name, Item.sku, Item.category)
    if low_stock:
        statement = statement.where(Item.quantity_available <= Item.min_stock)
    return page_result(db, statement, page, page_size,
                       lambda row: serialize(row, quantity_assigned=row.quantity_total - row.quantity_available,
                                             is_low_stock=row.quantity_available <= row.min_stock))


@router.get("/dashboard", tags=["داشبورد"])
def dashboard(db: Session = Depends(get_db), user=Depends(current_user)):
    count = lambda model, *conditions: db.scalar(select(func.count()).select_from(model).where(*conditions))
    low_items = db.scalars(select(Item).where(Item.quantity_available <= Item.min_stock).order_by(Item.name).limit(5)).all()
    metrics = [{"label": "انواع کالا", "value": count(Item), "unit": "قلم"},
               {"label": "تجهیزات موجود", "value": count(Asset, Asset.status == "available"), "unit": "دستگاه"},
               {"label": "کالای کم‌موجود", "value": count(Item, Item.quantity_available <= Item.min_stock), "unit": "قلم"}]
    recent = []
    if user.role in ("admin", "manager"):
        metrics.append({"label": "خرید در انتظار", "value": count(Purchase, Purchase.status == "pending"), "unit": "درخواست"})
        rows = db.scalars(select(Movement).order_by(Movement.created_at.desc(), Movement.id.desc()).limit(5)).all()
        recent = [{"title": record(db, Item, row.item_id, "کالا").name, "subtitle": row.reason,
                   "status": row.type, "date": serialize(row)["created_at"]} for row in rows]
    notices = [{"title": f"موجودی کم: {item.name}",
                "detail": f"موجودی قابل استفاده {item.quantity_available} {item.unit}؛ حداقل {item.min_stock}"}
               for item in low_items]
    return {"metrics": metrics, "recent": recent, "notices": notices}
