"""Commerce owns its customers, quotes, contracts and receivables.

Money is stored as integer toman. The two cached totals are changed by atomic
SQL updates, in the same transaction as their financial record.
"""

from datetime import date

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base
from shared.models import Record


class Customer(Record, Base):
    __tablename__ = "commerce_customers"
    name: Mapped[str] = mapped_column(String(160))
    company_name: Mapped[str] = mapped_column(String(160), default="")
    contact_name: Mapped[str] = mapped_column(String(160), default="")
    email: Mapped[str] = mapped_column(String(254), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)


class Offering(Record, Base):
    __tablename__ = "commerce_offerings"
    __table_args__ = (CheckConstraint("unit_price > 0", name="commerce_offering_price_positive"),)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    unit_price: Mapped[int] = mapped_column(BigInteger)
    unit: Mapped[str] = mapped_column(String(20), default="project")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Quotation(Record, Base):
    __tablename__ = "commerce_quotations"
    __table_args__ = (CheckConstraint("total > 0", name="commerce_quote_total_positive"),)
    customer_id: Mapped[str] = mapped_column(ForeignKey("commerce_customers.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    valid_until: Mapped[date] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    total: Mapped[int] = mapped_column(BigInteger)


class QuotationLine(Record, Base):
    __tablename__ = "commerce_quotation_lines"
    __table_args__ = (CheckConstraint("quantity > 0 AND unit_price > 0", name="commerce_quote_line_positive"),)
    quotation_id: Mapped[str] = mapped_column(ForeignKey("commerce_quotations.id"), index=True)
    offering_id: Mapped[str | None] = mapped_column(ForeignKey("commerce_offerings.id"), nullable=True)
    description: Mapped[str] = mapped_column(String(1000))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[int] = mapped_column(BigInteger)
    position: Mapped[int] = mapped_column(Integer)


class ProjectContract(Record, Base):
    __tablename__ = "commerce_contracts"
    __table_args__ = (
        CheckConstraint("amount > 0 AND invoiced_amount >= 0 AND invoiced_amount <= amount", name="commerce_contract_invoice_ceiling"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="commerce_contract_date_order"),
    )
    customer_id: Mapped[str] = mapped_column(ForeignKey("commerce_customers.id"), index=True)
    quotation_id: Mapped[str | None] = mapped_column(ForeignKey("commerce_quotations.id"), nullable=True, unique=True)
    title: Mapped[str] = mapped_column(String(200))
    # Personnel is an external service; its identifier has no local FK.
    employee_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    employee_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    invoiced_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class Invoice(Record, Base):
    __tablename__ = "commerce_invoices"
    __table_args__ = (
        CheckConstraint("amount > 0 AND paid_amount >= 0 AND paid_amount <= amount", name="commerce_invoice_payment_ceiling"),
        CheckConstraint("due_date >= issue_date", name="commerce_invoice_date_order"),
    )
    contract_id: Mapped[str] = mapped_column(ForeignKey("commerce_contracts.id"), index=True)
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="unpaid", index=True)
    paid_amount: Mapped[int] = mapped_column(BigInteger, default=0)


class Payment(Record, Base):
    __tablename__ = "commerce_payments"
    __table_args__ = (CheckConstraint("amount > 0", name="commerce_payment_positive"),)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("commerce_invoices.id"), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    paid_date: Mapped[date] = mapped_column(Date)
    method: Mapped[str] = mapped_column(String(20))
    # NULL allows multiple payments without a bank reference, but a given
    # nonempty reference can never create two receipts.
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    notes: Mapped[str] = mapped_column(Text, default="")
