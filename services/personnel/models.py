from datetime import date as DateValue
from sqlalchemy import BigInteger, Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from shared.database import Base
from shared.models import Record


class Department(Record, Base):
    __tablename__ = 'hr_departments'
    name: Mapped[str] = mapped_column(String(150), unique=True)
    description: Mapped[str] = mapped_column(Text, default='')


class Employee(Record, Base):
    __tablename__ = 'hr_employees'
    personnel_code: Mapped[str] = mapped_column(String(40), unique=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(200), default='')
    phone: Mapped[str] = mapped_column(String(30), default='')
    department_id: Mapped[str | None] = mapped_column(ForeignKey('hr_departments.id'), nullable=True)
    job_title: Mapped[str] = mapped_column(String(150))
    employment_type: Mapped[str] = mapped_column(String(30), default='full_time')
    hire_date: Mapped[DateValue] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default='active')
    base_salary: Mapped[int] = mapped_column(BigInteger, default=0)


class EmploymentContract(Record, Base):
    __tablename__ = 'hr_contracts'
    employee_id: Mapped[str] = mapped_column(ForeignKey('hr_employees.id'))
    title: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[DateValue] = mapped_column(Date)
    end_date: Mapped[DateValue | None] = mapped_column(Date, nullable=True)
    base_salary: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default='active')
    notes: Mapped[str] = mapped_column(Text, default='')


class Leave(Record, Base):
    __tablename__ = 'hr_leaves'
    employee_id: Mapped[str] = mapped_column(ForeignKey('hr_employees.id'))
    type: Mapped[str] = mapped_column(String(20), default='annual')
    start_date: Mapped[DateValue] = mapped_column(Date)
    end_date: Mapped[DateValue] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    decision_comment: Mapped[str] = mapped_column(Text, default='')


class Mission(Record, Base):
    __tablename__ = 'hr_missions'
    employee_id: Mapped[str] = mapped_column(ForeignKey('hr_employees.id'))
    title: Mapped[str] = mapped_column(String(200))
    destination: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[DateValue] = mapped_column(Date)
    end_date: Mapped[DateValue] = mapped_column(Date)
    allowance: Mapped[int] = mapped_column(BigInteger, default=0)
    reason: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(20), default='pending')
    decision_comment: Mapped[str] = mapped_column(Text, default='')


class Adjustment(Record, Base):
    __tablename__ = 'hr_adjustments'
    employee_id: Mapped[str] = mapped_column(ForeignKey('hr_employees.id'))
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(Text)
    date: Mapped[DateValue] = mapped_column(Date)


class Payroll(Record, Base):
    __tablename__ = 'hr_payrolls'
    __table_args__ = (UniqueConstraint('employee_id', 'period'),)
    employee_id: Mapped[str] = mapped_column(ForeignKey('hr_employees.id'))
    period: Mapped[str] = mapped_column(String(7))
    base_salary: Mapped[int] = mapped_column(BigInteger)
    bonus: Mapped[int] = mapped_column(BigInteger, default=0)
    deduction: Mapped[int] = mapped_column(BigInteger, default=0)
    rewards: Mapped[int] = mapped_column(BigInteger, default=0)
    penalties: Mapped[int] = mapped_column(BigInteger, default=0)
    mission_allowance: Mapped[int] = mapped_column(BigInteger, default=0)
    total: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default='draft')
