"""Inventory records. Stock counters are changed only through business operations."""
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base
from shared.models import Record


class Item(Record, Base):
    __tablename__ = "inv_items"
    __table_args__ = (
        CheckConstraint("quantity_available >= 0", name="inv_stock_nonnegative"),
        CheckConstraint("quantity_total >= quantity_available", name="inv_stock_total"),
        CheckConstraint("min_stock >= 0", name="inv_min_stock_valid"),
        CheckConstraint("tracking_type IN ('quantity', 'serialized')", name="inv_tracking_valid"),
    )
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(100))
    unit: Mapped[str] = mapped_column(String(40), default="عدد")
    tracking_type: Mapped[str] = mapped_column(String(20), default="quantity")
    min_stock: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(Text, default="")
    quantity_available: Mapped[int] = mapped_column(Integer, default=0)
    quantity_total: Mapped[int] = mapped_column(Integer, default=0)


class Supplier(Record, Base):
    __tablename__ = "inv_suppliers"
    name: Mapped[str] = mapped_column(String(200), index=True)
    contact_name: Mapped[str] = mapped_column(String(150), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    email: Mapped[str] = mapped_column(String(254), default="")
    address: Mapped[str] = mapped_column(Text, default="")


class Purchase(Record, Base):
    __tablename__ = "inv_purchases"
    __table_args__ = (
        CheckConstraint("quantity > 0 AND unit_price >= 0", name="inv_purchase_valid"),
        CheckConstraint("status IN ('pending', 'approved', 'received', 'cancelled')", name="inv_purchase_status"),
    )
    supplier_id: Mapped[str] = mapped_column(ForeignKey("inv_suppliers.id"), index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("inv_items.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[int] = mapped_column(BigInteger)
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Asset(Record, Base):
    __tablename__ = "inv_assets"
    __table_args__ = (
        CheckConstraint("status IN ('available', 'assigned', 'retired')", name="inv_asset_status"),
        CheckConstraint("(status = 'assigned' AND current_assignment_id IS NOT NULL) OR "
                        "(status <> 'assigned' AND current_assignment_id IS NULL)", name="inv_asset_custody"),
    )
    item_id: Mapped[str] = mapped_column(ForeignKey("inv_items.id"), index=True)
    serial_number: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="available", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    current_assignment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Assignment(Record, Base):
    __tablename__ = "inv_assignments"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="inv_assignment_quantity"),
        CheckConstraint("asset_id IS NULL OR quantity = 1", name="inv_asset_assignment_quantity"),
        CheckConstraint("status IN ('active', 'returned')", name="inv_assignment_status"),
    )
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("inv_assets.id"), nullable=True, index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("inv_items.id"), index=True)
    employee_id: Mapped[str] = mapped_column(String(36), index=True)
    employee_name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Movement(Record, Base):
    __tablename__ = "inv_movements"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="inv_movement_quantity"),
        CheckConstraint("type IN ('in', 'out')", name="inv_movement_type"),
    )
    item_id: Mapped[str] = mapped_column(ForeignKey("inv_items.id"), index=True)
    type: Mapped[str] = mapped_column(String(10), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(500))
    reference: Mapped[str] = mapped_column(String(200), default="")
    serial_numbers: Mapped[list[str]] = mapped_column(JSON, default=list)
