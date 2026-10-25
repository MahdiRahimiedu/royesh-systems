from datetime import date
import re
from typing import Annotated, Literal
from pydantic import Field, field_validator, model_validator
from shared.auth import Input

Money = Annotated[int, Field(ge=0, le=1_000_000_000_000, strict=True)]
Name = Annotated[str, Field(min_length=1, max_length=200)]
Identifier = Annotated[str, Field(min_length=1, max_length=36)]


class DepartmentCreate(Input):
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default='', max_length=2000)


class DepartmentUpdate(Input):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)


class EmployeeCreate(Input):
    personnel_code: str = Field(min_length=1, max_length=40)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(default='', max_length=200)
    phone: str = Field(default='', max_length=30)
    department_id: Identifier | None = None
    job_title: str = Field(min_length=1, max_length=150)
    employment_type: Literal['full_time', 'part_time', 'contract'] = 'full_time'
    hire_date: date
    status: Literal['active', 'inactive', 'terminated'] = 'active'
    base_salary: Money = 0

    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        if value and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', value):
            raise ValueError('ایمیل معتبر وارد کنید.')
        return value


class EmployeeUpdate(Input):
    personnel_code: str | None = Field(default=None, min_length=1, max_length=40)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=30)
    department_id: Identifier | None = None
    job_title: str | None = Field(default=None, min_length=1, max_length=150)
    employment_type: Literal['full_time', 'part_time', 'contract'] | None = None
    hire_date: date | None = None
    status: Literal['active', 'inactive', 'terminated'] | None = None
    base_salary: Money | None = None

    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        return EmployeeCreate.valid_email(value) if value is not None else value


class Dated(Input):
    start_date: date
    end_date: date

    @model_validator(mode='after')
    def ordered(self):
        if self.end_date < self.start_date:
            raise ValueError('تاریخ پایان نباید قبل از شروع باشد.')
        return self


class ContractCreate(Input):
    employee_id: Identifier
    title: Name
    start_date: date
    end_date: date | None = None
    base_salary: Money
    status: Literal['active', 'ended'] = 'active'
    notes: str = Field(default='', max_length=4000)

    @model_validator(mode='after')
    def ordered(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError('تاریخ پایان نباید قبل از شروع باشد.')
        return self


class ContractUpdate(Input):
    title: Name | None = None
    end_date: date | None = None
    status: Literal['ended'] | None = None
    notes: str | None = Field(default=None, max_length=4000)


class LeaveCreate(Dated):
    employee_id: Identifier
    type: Literal['annual', 'sick', 'unpaid'] = 'annual'
    reason: str = Field(min_length=2, max_length=2000)


class MissionCreate(Dated):
    employee_id: Identifier
    title: Name
    destination: Name
    allowance: Money = 0
    reason: str = Field(default='', max_length=2000)


class Decision(Input):
    status: Literal['approved', 'rejected']
    comment: str = Field(default='', max_length=2000)
    allowance: Money | None = None


class AdjustmentCreate(Input):
    employee_id: Identifier
    kind: Literal['reward', 'penalty']
    amount: Annotated[int, Field(gt=0, le=1_000_000_000_000, strict=True)]
    reason: str = Field(min_length=2, max_length=2000)
    date: date


class PayrollCreate(Input):
    employee_id: Identifier
    period: str = Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    bonus: Money = 0
    deduction: Money = 0


class PayrollUpdate(Input):
    bonus: Money | None = None
    deduction: Money | None = None
