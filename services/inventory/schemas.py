"""Explicit request schemas keep the public API understandable and predictable."""
from typing import Annotated, Literal
from uuid import UUID
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Name = Annotated[str, Field(min_length=1, max_length=200)]
Text = Annotated[str, Field(max_length=4000)]
PositiveInt = Annotated[int, Field(strict=True, gt=0, le=1_000_000)]
Money = Annotated[int, Field(strict=True, ge=0, le=1_000_000_000_000)]
Tracking = Literal["quantity", "serialized"]


class ItemCreate(Input):
    sku: Annotated[str, Field(min_length=1, max_length=64)]
    name: Name
    category: Annotated[str, Field(min_length=1, max_length=100)]
    unit: Annotated[str, Field(min_length=1, max_length=40)] = "عدد"
    tracking_type: Tracking = "quantity"
    min_stock: Annotated[int, Field(strict=True, ge=0, le=1_000_000)] = 0
    description: Text = ""


class ItemPatch(Input):
    sku: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    name: Name | None = None
    category: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    unit: Annotated[str, Field(min_length=1, max_length=40)] | None = None
    tracking_type: Tracking | None = None
    min_stock: Annotated[int, Field(strict=True, ge=0, le=1_000_000)] | None = None
    description: Text | None = None

    @model_validator(mode="after")
    def no_null(self):
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("فیلدهای کالا نمی‌توانند خالی باشند")
        return self


class SupplierCreate(Input):
    name: Name
    contact_name: Annotated[str, Field(max_length=150)] = ""
    phone: Annotated[str, Field(max_length=30)] = ""
    email: Annotated[str, Field(max_length=254)] = ""
    address: Text = ""

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        if value and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("نشانی ایمیل معتبر وارد کنید")
        return value


class SupplierPatch(Input):
    name: Name | None = None
    contact_name: Annotated[str, Field(max_length=150)] | None = None
    phone: Annotated[str, Field(max_length=30)] | None = None
    email: Annotated[str, Field(max_length=254)] | None = None
    address: Text | None = None

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        return SupplierCreate.valid_email(value) if value is not None else value

    @model_validator(mode="after")
    def no_null(self):
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("فیلدهای تأمین‌کننده نمی‌توانند خالی باشند")
        return self


class PurchaseCreate(Input):
    supplier_id: UUID
    item_id: UUID
    quantity: PositiveInt
    unit_price: Money
    notes: Text = ""

    @model_validator(mode="after")
    def valid_total(self):
        # Exact integer arithmetic must survive both SQL and JavaScript clients.
        if self.quantity * self.unit_price > 1_000_000_000_000_000:
            raise ValueError("جمع مبلغ سفارش بیش از سقف مجاز است")
        return self


class SerialNumbers(Input):
    serial_numbers: list[Annotated[str, Field(min_length=1, max_length=150)]] = Field(default_factory=list, max_length=10_000)

    @field_validator("serial_numbers")
    @classmethod
    def clean_serials(cls, values):
        values = [value.strip() for value in values]
        if any(not value for value in values):
            raise ValueError("شماره سریال خالی مجاز نیست")
        if len(values) != len(set(values)):
            raise ValueError("شماره سریال تکراری در درخواست وجود دارد")
        return values


class MovementCreate(SerialNumbers):
    item_id: UUID
    type: Literal["in", "out"]
    quantity: PositiveInt
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    reference: Annotated[str, Field(max_length=200)] = ""


class AssetCreate(Input):
    item_id: UUID
    serial_number: Annotated[str, Field(min_length=1, max_length=150)]
    status: Literal["available"] = "available"
    notes: Text = ""


class AssetPatch(Input):
    notes: Text | None = None
    status: Literal["available", "assigned", "retired"] | None = None

    @model_validator(mode="after")
    def no_null(self):
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("فیلدهای تجهیز نمی‌توانند خالی باشند")
        return self


class AssignmentCreate(Input):
    asset_id: UUID | None = None
    item_id: UUID | None = None
    employee_id: UUID
    employee_name: Name
    quantity: PositiveInt = 1
    notes: Text = ""

    @model_validator(mode="after")
    def one_target(self):
        if (self.asset_id is None) == (self.item_id is None):
            raise ValueError("دقیقاً یکی از asset_id یا item_id را وارد کنید")
        if self.asset_id is not None and self.quantity != 1:
            raise ValueError("تعداد تجهیز سریال‌دار باید یک باشد")
        return self


class Empty(Input):
    pass
