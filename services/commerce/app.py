"""FastAPI routes for commerce. Run from the repository root on port 8003."""

from datetime import timedelta
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.app import create_app
from shared.audit import log_action
from shared.auth import current_user, require_manager
from shared.database import Base, get_db, make_database
from shared.utils import serialize
from shared.models import business_today

from .models import Customer, Invoice, Offering, Payment, ProjectContract, Quotation, QuotationLine
from .schemas import (
    MAX_MONEY, ContractCreate, ContractPatch, ContractStatusChange,
    ContractStatus, CustomerCreate, CustomerPatch, CustomerStatus, EmptyRequest, InvoiceCreate, InvoiceStatus,
    OfferingCreate, OfferingPatch, PaymentCreate, QuotationCreate, QuotationPatch,
    QuotationStatusChange, QuoteStatus,
)

engine, SessionLocal, _ = make_database("commerce")


def seed_demo(db: Session):
    """Idempotent fictional examples; never call unless demo seed is enabled."""
    if db.scalar(select(Customer.id).limit(1)):
        return
    customer = Customer(name="آزمایشگاه نمونه سپهر", company_name="سپهر (داده نمایشی)", contact_name="نگار ساعی", phone="02100000001", email="demo@example.test", status="active", address="تهران ـ نشانی فرضی")
    second = Customer(name="فروشگاه نمونه آبان", company_name="آبان (داده نمایشی)", contact_name="آرمان نیک", phone="02100000002", status="active")
    offering = Offering(name="طراحی سامانه سازمانی", description="تحلیل، توسعه و تحویل نرم‌افزار تحت وب", unit_price=180_000_000, unit="project", is_active=True)
    support = Offering(name="پشتیبانی ماهانه", description="رفع خطا و نگهداری نرم‌افزار", unit_price=12_000_000, unit="month", is_active=True)
    db.add_all([customer, second, offering, support])
    db.flush()
    today = business_today()
    quote = Quotation(customer_id=customer.id, title="سامانه مدیریت خدمات سپهر", valid_until=today + timedelta(days=20), notes="تمام اطلاعات این نمونه ساختگی است.", status="accepted", total=180_000_000)
    db.add(quote)
    db.flush()
    db.add(QuotationLine(quotation_id=quote.id, offering_id=offering.id, description=offering.name, quantity=1, unit_price=180_000_000, position=0))
    contract = ProjectContract(customer_id=customer.id, quotation_id=quote.id, title="توسعه پنل خدمات سپهر", employee_id="10000000-0000-4000-8000-000000000001", employee_name="نگار احمدی", start_date=today - timedelta(days=30), end_date=today + timedelta(days=60), amount=180_000_000, invoiced_amount=60_000_000, status="active", notes="قرارداد نمایشی برای آموزش")
    db.add(contract)
    db.flush()
    invoice = Invoice(contract_id=contract.id, issue_date=today - timedelta(days=20), due_date=today - timedelta(days=2), amount=60_000_000, paid_amount=20_000_000, status="partial", description="پیش‌پرداخت مرحله تحلیل")
    db.add(invoice)
    db.flush()
    db.add(Payment(invoice_id=invoice.id, amount=20_000_000, paid_date=today - timedelta(days=10), method="bank", reference="DEMO-RECEIPT-001", notes="رسید ساختگی"))
    db.commit()


app = create_app("commerce", "سامانه بازرگانی رویش", Base, engine, SessionLocal, seed_demo)
PREFIX = "/api/v1"
router = APIRouter()
seed = seed_demo


def record(db: Session, model, identifier):
    value = db.get(model, str(identifier))
    if not value:
        raise HTTPException(404, "رکورد مورد نظر پیدا نشد")
    return value


def values(body, **kwargs):
    # UUID is a wire-level type; database columns store its canonical string.
    return {key: str(value) if isinstance(value, UUID) else value for key, value in body.model_dump(**kwargs).items()}


def finish(db: Session, user, action: str, entity: str, obj, details: str = ""):
    db.flush()
    log_action(db, user, action, entity, obj.id, details)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "رکورد تکراری است یا با اطلاعات وابسته سازگار نیست")
    db.refresh(obj)


def result_page(db: Session, statement, page: int, page_size: int, renderer=serialize):
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    model = statement.column_descriptions[0]["entity"]
    objects = db.scalars(statement.order_by(model.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [renderer(obj) for obj in objects], "total": total, "page": page, "page_size": page_size}


def customer_active(db, identifier):
    customer = record(db, Customer, identifier)
    if customer.status != "active":
        raise HTTPException(409, "مشتری غیرفعال است")
    return customer


def validate_quote_lines(db, lines):
    total = sum(line.quantity * line.unit_price for line in lines)
    if total > MAX_MONEY:
        raise HTTPException(422, "مجموع پیشنهاد از سقف مجاز بیشتر است")
    for line in lines:
        if line.offering_id and not record(db, Offering, line.offering_id).is_active:
            raise HTTPException(409, "خدمت انتخاب‌شده غیرفعال است")
    return total


def quote_view(db, quote):
    lines = db.scalars(select(QuotationLine).where(QuotationLine.quotation_id == quote.id).order_by(QuotationLine.position)).all()
    return serialize(quote, customer_name=record(db, Customer, quote.customer_id).name, lines=[serialize(line, total=line.quantity * line.unit_price) for line in lines])


def contract_view(db, contract):
    return serialize(contract, customer_name=record(db, Customer, contract.customer_id).name, remaining_amount=contract.amount - contract.invoiced_amount)


def invoice_view(db, invoice):
    contract = record(db, ProjectContract, invoice.contract_id)
    customer = record(db, Customer, contract.customer_id)
    return serialize(invoice, balance=0 if invoice.status == "void" else invoice.amount - invoice.paid_amount, customer_name=customer.name, customer_id=customer.id, contract_title=contract.title)


def payment_view(db, payment):
    invoice = record(db, Invoice, payment.invoice_id)
    contract = record(db, ProjectContract, invoice.contract_id)
    customer = record(db, Customer, contract.customer_id)
    return serialize(payment, customer_name=customer.name, contract_title=contract.title, invoice_balance=invoice.amount - invoice.paid_amount, invoice_status=invoice.status)


@router.get(PREFIX + "/customers", tags=["مشتریان"])
def list_customers(q: str = Query("", max_length=100), status: CustomerStatus | None = None, page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), user=Depends(current_user)):
    statement = select(Customer).order_by(Customer.created_at.desc())
    if q:
        statement = statement.where(or_(Customer.name.contains(q, autoescape=True), Customer.company_name.contains(q, autoescape=True), Customer.contact_name.contains(q, autoescape=True), Customer.email.contains(q, autoescape=True), Customer.phone.contains(q, autoescape=True)))
    if status:
        statement = statement.where(Customer.status == status)
    return result_page(db, statement, page, page_size)


@router.get(PREFIX + "/customers/{identifier}", tags=["مشتریان"])
def get_customer(identifier: UUID, db: Session = Depends(get_db), user=Depends(current_user)):
    return serialize(record(db, Customer, identifier))


@router.post(PREFIX + "/customers", status_code=201, tags=["مشتریان"])
def create_customer(body: CustomerCreate, db: Session = Depends(get_db), user=Depends(require_manager)):
    obj = Customer(**values(body))
    db.add(obj)
    finish(db, user, "create", "customer", obj)
    return serialize(obj)


@router.patch(PREFIX + "/customers/{identifier}", tags=["مشتریان"])
def patch_customer(identifier: UUID, body: CustomerPatch, db: Session = Depends(get_db), user=Depends(require_manager)):
    obj = record(db, Customer, identifier)
    for key, value in values(body, exclude_unset=True).items():
        setattr(obj, key, value)
    finish(db, user, "update", "customer", obj)
    return serialize(obj)


@router.get(PREFIX + "/offerings", tags=["خدمات"])
def list_offerings(q: str = Query("", max_length=100), is_active: bool | None = None, page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), user=Depends(current_user)):
    statement = select(Offering).order_by(Offering.created_at.desc())
    if q:
        statement = statement.where(or_(Offering.name.contains(q, autoescape=True), Offering.description.contains(q, autoescape=True)))
    if is_active is not None:
        statement = statement.where(Offering.is_active == is_active)
    return result_page(db, statement, page, page_size)


@router.get(PREFIX + "/offerings/{identifier}", tags=["خدمات"])
def get_offering(identifier: UUID, db: Session = Depends(get_db), user=Depends(current_user)):
    return serialize(record(db, Offering, identifier))


@router.post(PREFIX + "/offerings", status_code=201, tags=["خدمات"])
def create_offering(body: OfferingCreate, db: Session = Depends(get_db), user=Depends(require_manager)):
    obj = Offering(**values(body))
    db.add(obj)
    finish(db, user, "create", "offering", obj)
    return serialize(obj)


@router.patch(PREFIX + "/offerings/{identifier}", tags=["خدمات"])
def patch_offering(identifier: UUID, body: OfferingPatch, db: Session = Depends(get_db), user=Depends(require_manager)):
    obj = record(db, Offering, identifier)
    for key, value in values(body, exclude_unset=True).items():
        setattr(obj, key, value)
    finish(db, user, "update", "offering", obj)
    return serialize(obj)


@router.get(PREFIX + "/quotations", tags=["پیشنهاد قیمت"])
def list_quotations(q: str = Query("", max_length=100), status: QuoteStatus | None = None, customer_id: UUID | None = None, page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), user=Depends(current_user)):
    statement = select(Quotation).order_by(Quotation.created_at.desc())
    if q:
        statement = statement.join(Customer).where(or_(Quotation.title.contains(q, autoescape=True), Quotation.notes.contains(q, autoescape=True), Customer.name.contains(q, autoescape=True), Customer.company_name.contains(q, autoescape=True)))
    if status:
        statement = statement.where(Quotation.status == status)
    if customer_id:
        statement = statement.where(Quotation.customer_id == str(customer_id))
    return result_page(db, statement, page, page_size, lambda obj: quote_view(db, obj))


@router.get(PREFIX + "/quotations/{identifier}", tags=["پیشنهاد قیمت"])
def get_quotation(identifier: UUID, db: Session = Depends(get_db), user=Depends(current_user)):
    return quote_view(db, record(db, Quotation, identifier))


@router.post(PREFIX + "/quotations", status_code=201, tags=["پیشنهاد قیمت"])
def create_quotation(body: QuotationCreate, db: Session = Depends(get_db), user=Depends(require_manager)):
    customer_active(db, body.customer_id)
    if body.valid_until < business_today():
        raise HTTPException(422, "تاریخ اعتبار پیشنهاد قیمت گذشته است")
    total = validate_quote_lines(db, body.lines)
    obj = Quotation(**values(body, exclude={"lines"}), total=total, status="draft")
    db.add(obj)
    db.flush()
    for position, line in enumerate(body.lines):
        db.add(QuotationLine(quotation_id=obj.id, position=position, **values(line)))
    finish(db, user, "create", "quotation", obj)
    return quote_view(db, obj)


@router.patch(PREFIX + "/quotations/{identifier}", tags=["پیشنهاد قیمت"])
def patch_quotation(identifier: UUID, body: QuotationPatch, db: Session = Depends(get_db), user=Depends(require_manager)):
    obj = record(db, Quotation, identifier)
    if obj.status != "draft":
        raise HTTPException(409, "فقط پیشنهاد قیمت پیش‌نویس قابل ویرایش است")
    changes = values(body, exclude_unset=True, exclude={"lines"})
    if changes.get("customer_id", obj.customer_id) != obj.customer_id:
        customer_active(db, changes["customer_id"])
    if changes.get("valid_until", obj.valid_until) < business_today():
        raise HTTPException(422, "تاریخ اعتبار پیشنهاد قیمت گذشته است")
    total = validate_quote_lines(db, body.lines) if body.lines is not None else obj.total
    # Retain the previous draft in the audit ledger before replacing its lines.
    before = quote_view(db, obj)
    changed = db.execute(update(Quotation).where(
        Quotation.id == obj.id, Quotation.status == "draft", Quotation.updated_at == obj.updated_at,
    ).values(**changes, total=total).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise HTTPException(409, "پیشنهاد هم‌زمان ویرایش یا ارسال شده است؛ دوباره دریافت کنید")
    if body.lines is not None:
        db.execute(delete(QuotationLine).where(QuotationLine.quotation_id == obj.id))
        for position, line in enumerate(body.lines):
            db.add(QuotationLine(quotation_id=obj.id, position=position, **values(line)))
    finish(db, user, "update", "quotation", obj, json.dumps({"previous_draft": before}, ensure_ascii=False))
    return quote_view(db, obj)


@router.post(PREFIX + "/quotations/{identifier}/status", tags=["پیشنهاد قیمت"])
def change_quotation_status(identifier: UUID, body: QuotationStatusChange, db: Session = Depends(get_db), user=Depends(require_manager)):
    obj = record(db, Quotation, identifier)
    transitions = {"draft": {"sent"}, "sent": {"accepted", "rejected"}, "accepted": set(), "rejected": set()}
    if body.status not in transitions[obj.status]:
        raise HTTPException(409, "تغییر وضعیت پیشنهاد قیمت مجاز نیست")
    if body.status in {"sent", "accepted"} and obj.valid_until < business_today():
        raise HTTPException(409, "اعتبار پیشنهاد قیمت پایان یافته است")
    if body.status in {"sent", "accepted"}:
        customer_active(db, obj.customer_id)
    changed = db.execute(update(Quotation).where(Quotation.id == obj.id, Quotation.status == obj.status, Quotation.updated_at == obj.updated_at).values(status=body.status).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise HTTPException(409, "وضعیت پیشنهاد هم‌زمان تغییر کرده است؛ دوباره دریافت کنید")
    finish(db, user, "status", "quotation", obj)
    return quote_view(db, obj)


@router.get(PREFIX + "/contracts", tags=["قرارداد پروژه"])
def list_contracts(q: str = Query("", max_length=100), status: ContractStatus | None = None, customer_id: UUID | None = None, page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), user=Depends(current_user)):
    statement = select(ProjectContract).order_by(ProjectContract.created_at.desc())
    if q:
        statement = statement.join(Customer).where(or_(ProjectContract.title.contains(q, autoescape=True), ProjectContract.employee_name.contains(q, autoescape=True), ProjectContract.notes.contains(q, autoescape=True), Customer.name.contains(q, autoescape=True), Customer.company_name.contains(q, autoescape=True)))
    if status:
        statement = statement.where(ProjectContract.status == status)
    if customer_id:
        statement = statement.where(ProjectContract.customer_id == str(customer_id))
    return result_page(db, statement, page, page_size, lambda obj: contract_view(db, obj))


@router.get(PREFIX + "/contracts/{identifier}", tags=["قرارداد پروژه"])
def get_contract(identifier: UUID, db: Session = Depends(get_db), user=Depends(current_user)):
    return contract_view(db, record(db, ProjectContract, identifier))


@router.post(PREFIX + "/contracts", status_code=201, tags=["قرارداد پروژه"])
def create_contract(body: ContractCreate, db: Session = Depends(get_db), user=Depends(require_manager)):
    customer_active(db, body.customer_id)
    if body.quotation_id:
        quote = record(db, Quotation, body.quotation_id)
        if quote.customer_id != str(body.customer_id) or quote.status != "accepted" or quote.total != body.amount:
            raise HTTPException(409, "پیشنهاد باید تأییدشده و متعلق به همین مشتری و مبلغ باشد")
        if db.scalar(select(ProjectContract.id).where(ProjectContract.quotation_id == quote.id)):
            raise HTTPException(409, "این پیشنهاد قبلاً به قرارداد تبدیل شده است")
    obj = ProjectContract(**values(body), status="draft", invoiced_amount=0)
    db.add(obj)
    finish(db, user, "create", "contract", obj)
    return contract_view(db, obj)


@router.patch(PREFIX + "/contracts/{identifier}", tags=["قرارداد پروژه"])
def patch_contract(identifier: UUID, body: ContractPatch, db: Session = Depends(get_db), user=Depends(require_manager)):
    obj = record(db, ProjectContract, identifier)
    changes = values(body, exclude_unset=True)
    if obj.status in {"completed", "cancelled"}:
        raise HTTPException(409, "قرارداد نهایی‌شده قابل ویرایش نیست")
    financial_fields = {"customer_id", "amount", "start_date", "end_date"}
    financial_changes = {key for key in financial_fields.intersection(changes) if changes[key] != getattr(obj, key)}
    if obj.status != "draft" and financial_changes:
        raise HTTPException(409, "اطلاعات مالی و تاریخ‌های قرارداد فقط در پیش‌نویس قابل ویرایش است")
    customer_id = changes.get("customer_id", obj.customer_id)
    amount = changes.get("amount", obj.amount)
    if customer_id != obj.customer_id:
        customer_active(db, customer_id)
    if obj.quotation_id:
        quote = record(db, Quotation, obj.quotation_id)
        if customer_id != quote.customer_id or amount != quote.total:
            raise HTTPException(409, "مشتری و مبلغ باید با پیشنهاد تأییدشده یکسان بماند")
    start = changes.get("start_date", obj.start_date)
    end = changes.get("end_date", obj.end_date)
    if end and end < start:
        raise HTTPException(422, "تاریخ پایان قرارداد نباید پیش از شروع آن باشد")
    if bool(changes.get("employee_id", obj.employee_id)) != bool(changes.get("employee_name", obj.employee_name)):
        raise HTTPException(422, "شناسه و نام مسئول قرارداد باید با هم ثبت شوند")
    if changes:
        changed = db.execute(update(ProjectContract).where(ProjectContract.id == obj.id, ProjectContract.status == obj.status, ProjectContract.invoiced_amount <= amount).values(**changes).execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            raise HTTPException(409, "وضعیت قرارداد هم‌زمان تغییر کرده است")
    finish(db, user, "update", "contract", obj)
    return contract_view(db, obj)


@router.post(PREFIX + "/contracts/{identifier}/status", tags=["قرارداد پروژه"])
def change_contract_status(identifier: UUID, body: ContractStatusChange, db: Session = Depends(get_db), user=Depends(require_manager)):
    obj = record(db, ProjectContract, identifier)
    transitions = {"draft": {"active", "cancelled"}, "active": {"completed", "cancelled"}, "completed": set(), "cancelled": set()}
    if body.status not in transitions[obj.status]:
        raise HTTPException(409, "تغییر وضعیت قرارداد مجاز نیست")
    criteria = [ProjectContract.id == obj.id, ProjectContract.status == obj.status]
    if body.status == "cancelled":
        criteria.append(ProjectContract.invoiced_amount == 0)
    if body.status == "active":
        customer_active(db, obj.customer_id)
    changed = db.execute(update(ProjectContract).where(*criteria).values(status=body.status).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise HTTPException(409, "قرارداد هم‌زمان تغییر کرده یا صورتحساب ابطال‌نشده دارد")
    finish(db, user, "status", "contract", obj)
    return contract_view(db, obj)


@router.get(PREFIX + "/invoices", tags=["صورتحساب"])
def list_invoices(q: str = Query("", max_length=100), status: InvoiceStatus | None = None, contract_id: UUID | None = None, page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), user=Depends(current_user)):
    statement = select(Invoice).order_by(Invoice.created_at.desc())
    if q:
        statement = statement.join(ProjectContract).join(Customer).where(or_(Invoice.description.contains(q, autoescape=True), ProjectContract.title.contains(q, autoescape=True), Customer.name.contains(q, autoescape=True)))
    if status:
        statement = statement.where(Invoice.status == status)
    if contract_id:
        statement = statement.where(Invoice.contract_id == str(contract_id))
    return result_page(db, statement, page, page_size, lambda obj: invoice_view(db, obj))


@router.get(PREFIX + "/invoices/{identifier}", tags=["صورتحساب"])
def get_invoice(identifier: UUID, db: Session = Depends(get_db), user=Depends(current_user)):
    return invoice_view(db, record(db, Invoice, identifier))


@router.post(PREFIX + "/invoices", status_code=201, tags=["صورتحساب"])
def create_invoice(body: InvoiceCreate, db: Session = Depends(get_db), user=Depends(require_manager)):
    contract = record(db, ProjectContract, body.contract_id)
    if body.issue_date > business_today():
        raise HTTPException(422, "تاریخ صدور صورتحساب نباید در آینده باشد")
    if body.issue_date < contract.start_date:
        raise HTTPException(422, "صورتحساب نمی‌تواند پیش از شروع قرارداد صادر شود")
    # Atomic ceiling reservation prevents concurrent invoices exceeding amount.
    changed = db.execute(update(ProjectContract).where(ProjectContract.id == contract.id, ProjectContract.status.in_(["active", "completed"]), ProjectContract.invoiced_amount + body.amount <= ProjectContract.amount).values(invoiced_amount=ProjectContract.invoiced_amount + body.amount).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise HTTPException(409, "قرارداد فعال نیست یا مجموع صورتحساب‌ها از مبلغ قرارداد بیشتر می‌شود")
    obj = Invoice(**values(body), status="unpaid", paid_amount=0)
    db.add(obj)
    finish(db, user, "create", "invoice", obj)
    # The identity map may still contain the contract's previous cached total.
    db.expire(contract)
    return invoice_view(db, obj)


@router.post(PREFIX + "/invoices/{identifier}/void", tags=["صورتحساب"])
def void_invoice(identifier: UUID, body: EmptyRequest, db: Session = Depends(get_db), user=Depends(require_manager)):
    obj = record(db, Invoice, identifier)
    changed = db.execute(update(Invoice).where(Invoice.id == obj.id, Invoice.status == "unpaid", Invoice.paid_amount == 0).values(status="void").execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise HTTPException(409, "فقط صورتحساب پرداخت‌نشده و ابطال‌نشده قابل ابطال است")
    db.execute(update(ProjectContract).where(ProjectContract.id == obj.contract_id).values(invoiced_amount=ProjectContract.invoiced_amount - obj.amount).execution_options(synchronize_session=False))
    finish(db, user, "void", "invoice", obj)
    return invoice_view(db, obj)


@router.get(PREFIX + "/payments", tags=["دریافت وجه"])
def list_payments(q: str = Query("", max_length=100), invoice_id: UUID | None = None, page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), user=Depends(current_user)):
    statement = select(Payment).order_by(Payment.created_at.desc())
    if q:
        statement = statement.join(Invoice).join(ProjectContract).join(Customer).where(or_(Payment.reference.contains(q, autoescape=True), Payment.notes.contains(q, autoescape=True), Customer.name.contains(q, autoescape=True), ProjectContract.title.contains(q, autoescape=True)))
    if invoice_id:
        statement = statement.where(Payment.invoice_id == str(invoice_id))
    return result_page(db, statement, page, page_size, lambda obj: payment_view(db, obj))


@router.post(PREFIX + "/payments", status_code=201, tags=["دریافت وجه"])
def create_payment(body: PaymentCreate, db: Session = Depends(get_db), user=Depends(require_manager)):
    invoice = record(db, Invoice, body.invoice_id)
    if body.paid_date > business_today():
        raise HTTPException(422, "تاریخ دریافت وجه نباید در آینده باشد")
    if body.paid_date < invoice.issue_date:
        raise HTTPException(422, "تاریخ دریافت وجه نباید پیش از صدور صورتحساب باشد")
    reference = body.reference or None
    if reference and db.scalar(select(Payment.id).where(Payment.reference == reference)):
        raise HTTPException(409, "این شماره پیگیری قبلاً ثبت شده است")
    # Both the condition and increment execute in one statement: two requests
    # cannot independently read the old balance and both overpay the invoice.
    new_paid = Invoice.paid_amount + body.amount
    changed = db.execute(update(Invoice).where(Invoice.id == invoice.id, Invoice.status.in_(["unpaid", "partial"]), new_paid <= Invoice.amount).values(paid_amount=new_paid, status=case((new_paid == Invoice.amount, "paid"), else_="partial")).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise HTTPException(409, "مبلغ از مانده بیشتر است یا صورتحساب قابل پرداخت نیست")
    obj = Payment(**{**values(body), "reference": reference})
    db.add(obj)
    finish(db, user, "create", "payment", obj)
    db.refresh(invoice)
    return payment_view(db, obj)


@router.get(PREFIX + "/reports/receivables", tags=["گزارش"])
def receivables(q: str = Query("", max_length=100), overdue: bool = False, page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), user=Depends(current_user)):
    statement = select(Invoice).where(Invoice.status.in_(["unpaid", "partial"])).order_by(Invoice.due_date)
    if overdue:
        statement = statement.where(Invoice.due_date < business_today())
    if q:
        statement = statement.join(ProjectContract).join(Customer).where(or_(ProjectContract.title.contains(q, autoescape=True), Customer.name.contains(q, autoescape=True)))
    return result_page(db, statement, page, page_size, lambda obj: invoice_view(db, obj))


@router.get(PREFIX + "/dashboard", tags=["داشبورد"])
def dashboard(db: Session = Depends(get_db), user=Depends(current_user)):
    outstanding = db.scalar(select(func.coalesce(func.sum(Invoice.amount - Invoice.paid_amount), 0)).where(Invoice.status.in_(["unpaid", "partial"]))) or 0
    overdue_count = db.scalar(select(func.count()).select_from(Invoice).where(Invoice.status.in_(["unpaid", "partial"]), Invoice.due_date < business_today())) or 0
    active_count = db.scalar(select(func.count()).select_from(ProjectContract).where(ProjectContract.status == "active")) or 0
    customer_count = db.scalar(select(func.count()).select_from(Customer).where(Customer.status == "active")) or 0
    recent = db.scalars(select(ProjectContract).order_by(ProjectContract.created_at.desc()).limit(5)).all()
    notices = []
    if overdue_count:
        notices.append({"title": f"{overdue_count} صورتحساب سررسیدگذشته", "detail": "گزارش مطالبات را برای پیگیری دریافت وجه بررسی کنید."})
    return {"metrics": [{"label": "مشتریان فعال", "value": customer_count}, {"label": "قراردادهای فعال", "value": active_count}, {"label": "مانده مطالبات", "value": outstanding, "unit": "تومان"}, {"label": "صورتحساب معوق", "value": overdue_count}], "recent": [{"title": obj.title, "subtitle": record(db, Customer, obj.customer_id).name, "status": obj.status, "date": obj.start_date.isoformat()} for obj in recent], "notices": notices}


app.include_router(router)
