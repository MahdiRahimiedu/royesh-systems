"""Explicit request schemas keep the API readable and reject unknown fields."""

from datetime import date
import re
from typing import Annotated, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_MONEY = 1_000_000_000_000_000
Money = Annotated[int, Field(strict=True, gt=0, le=MAX_MONEY)]
Quantity = Annotated[int, Field(strict=True, gt=0, le=1_000_000)]
Name = Annotated[str, Field(min_length=1, max_length=160)]
Title = Annotated[str, Field(min_length=1, max_length=200)]
Notes = Annotated[str, Field(max_length=5000)]
CustomerStatus = Literal["active", "inactive"]
QuoteStatus = Literal["draft", "sent", "accepted", "rejected"]
ContractStatus = Literal["draft", "active", "completed", "cancelled"]
InvoiceStatus = Literal["unpaid", "partial", "paid", "void"]


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PatchRequest(Request):
    nullable_fields: ClassVar[set[str]] = set()

    @model_validator(mode="after")
    def required_when_provided(self):
        for field in self.model_fields_set - {"nullable_fields"}:
            if getattr(self, field) is None and field not in self.nullable_fields:
                raise ValueError(f"فیلد {field} نمی‌تواند خالی باشد")
        return self


class ContactEmail(Request):
    @field_validator("email", check_fields=False)
    @classmethod
    def validate_email(cls, value):
        if value and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("نشانی ایمیل معتبر نیست")
        return value


class CustomerCreate(ContactEmail):
    name: Name
    company_name: Annotated[str, Field(max_length=160)] = ""
    contact_name: Annotated[str, Field(max_length=160)] = ""
    email: Annotated[str, Field(max_length=254)] = ""
    phone: Annotated[str, Field(max_length=30)] = ""
    address: Notes = ""
    status: CustomerStatus = "active"


class CustomerPatch(PatchRequest, ContactEmail):
    name: Name | None = None
    company_name: Annotated[str, Field(max_length=160)] | None = None
    contact_name: Annotated[str, Field(max_length=160)] | None = None
    email: Annotated[str, Field(max_length=254)] | None = None
    phone: Annotated[str, Field(max_length=30)] | None = None
    address: Notes | None = None
    status: CustomerStatus | None = None


class OfferingCreate(Request):
    name: Name
    description: Notes = ""
    unit_price: Money
    unit: Literal["project", "month", "hour"] = "project"
    is_active: bool = True


class OfferingPatch(PatchRequest):
    name: Name | None = None
    description: Notes | None = None
    unit_price: Money | None = None
    unit: Literal["project", "month", "hour"] | None = None
    is_active: bool | None = None


class QuotationLineCreate(Request):
    offering_id: UUID | None = None
    description: Annotated[str, Field(min_length=1, max_length=1000)]
    quantity: Quantity
    unit_price: Money


class QuotationCreate(Request):
    customer_id: UUID
    title: Title
    valid_until: date
    notes: Notes = ""
    lines: Annotated[list[QuotationLineCreate], Field(min_length=1, max_length=100)]


class QuotationPatch(PatchRequest):
    customer_id: UUID | None = None
    title: Title | None = None
    valid_until: date | None = None
    notes: Notes | None = None
    lines: Annotated[list[QuotationLineCreate], Field(min_length=1, max_length=100)] | None = None


class QuotationStatusChange(Request):
    status: QuoteStatus


class ContractCreate(Request):
    customer_id: UUID
    quotation_id: UUID | None = None
    title: Title
    employee_id: UUID | None = None
    employee_name: Name | None = None
    start_date: date
    end_date: date | None = None
    amount: Money
    notes: Notes = ""

    @field_validator("employee_name", mode="before")
    @classmethod
    def empty_employee_name(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def date_order(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("تاریخ پایان قرارداد نباید پیش از شروع آن باشد")
        if bool(self.employee_id) != bool(self.employee_name):
            raise ValueError("شناسه و نام مسئول قرارداد باید با هم ثبت شوند")
        return self


class ContractPatch(PatchRequest):
    nullable_fields: ClassVar[set[str]] = {"employee_id", "employee_name", "end_date"}
    customer_id: UUID | None = None
    title: Title | None = None
    employee_id: UUID | None = None
    employee_name: Name | None = None
    start_date: date | None = None
    end_date: date | None = None
    amount: Money | None = None
    notes: Notes | None = None

    @field_validator("employee_name", mode="before")
    @classmethod
    def empty_employee_name(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


class ContractStatusChange(Request):
    status: ContractStatus


class InvoiceCreate(Request):
    contract_id: UUID
    issue_date: date
    due_date: date
    amount: Money
    description: Notes = ""

    @model_validator(mode="after")
    def date_order(self):
        if self.due_date < self.issue_date:
            raise ValueError("سررسید نباید پیش از تاریخ صدور باشد")
        return self


class PaymentCreate(Request):
    invoice_id: UUID
    amount: Money
    paid_date: date
    method: Literal["bank", "cash", "cheque"]
    reference: Annotated[str, Field(max_length=120)] | None = None
    notes: Notes = ""


class EmptyRequest(Request):
    pass
