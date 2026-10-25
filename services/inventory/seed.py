"""Fictional demonstration data. Existing business records are never overwritten."""
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import select

from .models import Asset, Assignment, Item, Movement, Purchase, Supplier

EMPLOYEE_ID = "10000000-0000-4000-8000-000000000001"


def seed(db):
    definitions = [
        ("LAP-001", "لپ‌تاپ تیم توسعه", "تجهیزات رایانه", "serialized", 2, 5),
        ("MON-001", "نمایشگر ۲۴ اینچ", "تجهیزات رایانه", "serialized", 1, 3),
        ("CAB-001", "کابل شبکه دو متری", "ملزومات شبکه", "quantity", 8, 24),
        ("NOTE-001", "دفتر یادداشت", "ملزومات اداری", "quantity", 5, 4),
    ]
    marker = lambda sku: f"DEMO-INITIAL-{sku}"
    demo_id = lambda kind, name: str(uuid5(NAMESPACE_URL, f"rooyesh:inventory:demo:{kind}:{name}"))
    supplier = db.get(Supplier, demo_id("supplier", "main"))
    # Legacy databases used random IDs. Ledger markers survive a user's rename.
    if supplier is None:
        supplier = db.scalar(select(Supplier).join(Purchase).join(Item, Purchase.item_id == Item.id)
                             .join(Movement, Movement.item_id == Item.id)
                             .where(Movement.reference.in_([marker(row[0]) for row in definitions])).limit(1))
    if supplier is None:
        supplier = db.scalar(select(Supplier).where(Supplier.name == "تجهیزپرداز نمونه"))
    if supplier is None:
        supplier = Supplier(id=demo_id("supplier", "main"), name="تجهیزپرداز نمونه", contact_name="مریم صالحی",
                            phone="02100000000", email="sales@example.com",
                            address="تهران، نشانی فرضی جهت نمایش دانشگاهی")
        db.add(supplier)
        db.flush()

    for sku, name, category, tracking, minimum, quantity in definitions:
        existing = db.get(Item, demo_id("item", sku))
        if existing is None:
            existing = db.scalar(select(Item).join(Movement).where(Movement.reference == marker(sku)).limit(1))
        if existing is not None or db.scalar(select(Item.id).where(Item.sku == sku)):
            continue
        item = Item(id=demo_id("item", sku), sku=sku, name=name, category=category, unit="عدد", tracking_type=tracking,
                    min_stock=minimum, description="داده فرضی برای آموزش و نمایش پروژه",
                    quantity_available=quantity, quantity_total=quantity)
        db.add(item)
        db.flush()
        serials = [f"DEMO-{sku}-{index + 1:03}" for index in range(quantity)] if tracking == "serialized" else []
        # Record the initial receipt before any assignment, preserving ledger order.
        db.add(Movement(item_id=item.id, type="in", quantity=quantity, reason="موجودی اولیه نمونه",
                        reference=marker(sku), serial_numbers=serials))
        db.flush()
        for index in range(quantity if tracking == "serialized" else 0):
            serial = serials[index]
            asset = Asset(item_id=item.id, serial_number=serial, status="available", notes="تجهیز نمونه")
            db.add(asset)
            db.flush()
            if sku == "LAP-001" and index == 0:
                assignment = Assignment(id=str(uuid4()), item_id=item.id, asset_id=asset.id,
                                        employee_id=EMPLOYEE_ID, employee_name="نگار احمدی", quantity=1,
                                        notes="تحویل برای پروژه وب شرکت؛ داده فرضی", status="active")
                db.add(assignment)
                asset.status = "assigned"
                asset.current_assignment_id = assignment.id
                item.quantity_available -= 1
                db.add(Movement(item_id=item.id, type="out", quantity=1, reason="تحویل به نگار احمدی",
                                reference=assignment.id, serial_numbers=[serial]))
        demo_prices = {"LAP-001": 45_000_000, "MON-001": 9_000_000, "CAB-001": 90_000, "NOTE-001": 150_000}
        db.add(Purchase(supplier_id=supplier.id, item_id=item.id, quantity=2 if tracking == "serialized" else 10,
                        unit_price=demo_prices[sku],
                        status="pending", notes="درخواست خرید نمونه برای توسعه تیم"))
    db.flush()
