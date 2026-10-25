"""Passwords: salted scrypt. Sessions: random opaque tokens stored as SHA256 hashes."""
import hashlib
import hmac
import os
import secrets
from datetime import timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy import Boolean, DateTime, ForeignKey, String, or_, select
from sqlalchemy.orm import Mapped, mapped_column
from shared.database import Base, get_db
from shared.models import Record, utcnow
from shared.utils import paginate, serialize


class User(Record, Base):
    __tablename__ = 'users'
    username: Mapped[str] = mapped_column(String(100), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(20), default='staff')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    employee_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class AuthSession(Record, Base):
    __tablename__ = 'auth_sessions'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True))


def hash_password(password):
    salt = secrets.token_hex(16)
    hashed = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return f'{salt}${hashed}'


def verify_password(password, encoded):
    salt, expected = encoded.split('$', 1)
    actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(actual, expected)


def user_data(user):
    return {key: getattr(user, key) for key in ('id', 'username', 'full_name', 'role', 'is_active', 'employee_id')}


bearer = HTTPBearer(auto_error=False)


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db=Depends(get_db)):
    if not credentials:
        raise HTTPException(401, 'ابتدا وارد حساب کاربری شوید.')
    token_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))
    expiry = None if session is None else session.expires_at
    if expiry is not None:
        expiry = expiry.replace(tzinfo=timezone.utc) if expiry.tzinfo is None else expiry.astimezone(timezone.utc)
    if session is None or expiry <= utcnow():
        raise HTTPException(401, 'نشست شما منقضی شده است. دوباره وارد شوید.')
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, 'این حساب غیرفعال است.')
    return user


def require_manager(user=Depends(current_user)):
    if user.role not in ('admin', 'manager'):
        raise HTTPException(403, 'این عملیات به دسترسی مدیر یا کارشناس نیاز دارد.')
    return user


def require_admin(user=Depends(current_user)):
    if user.role != 'admin':
        raise HTTPException(403, 'این عملیات فقط برای مدیر سامانه مجاز است.')
    return user


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


Password = Annotated[str, StringConstraints(strip_whitespace=False)]


def normalize_employee_id(value):
    if value is None or value == '':
        return None
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('شناسه کارمند باید UUID معتبر باشد.')


class Login(Input):
    username: str = Field(min_length=1, max_length=100)
    password: Password = Field(min_length=1, max_length=256)


class CreateUser(Input):
    username: str = Field(pattern=r'^[a-zA-Z0-9_.-]{3,100}$')
    full_name: str = Field(min_length=2, max_length=200)
    password: Password = Field(min_length=10, max_length=128)
    role: Literal['admin', 'manager', 'staff'] = 'staff'
    employee_id: str | None = Field(default=None, max_length=36)
    is_active: bool = True

    _employee_id = field_validator('employee_id')(normalize_employee_id)


class UpdateUser(Input):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    role: Literal['admin', 'manager', 'staff'] | None = None
    is_active: bool | None = None
    employee_id: str | None = Field(default=None, max_length=36)

    _employee_id = field_validator('employee_id')(normalize_employee_id)


class PasswordChange(Input):
    current_password: Password = Field(max_length=256)
    new_password: Password = Field(min_length=10, max_length=128)


router = APIRouter(prefix='/api/v1', tags=['حساب کاربری'])


@router.post('/auth/login')
def login(body: Login, request: Request, db=Depends(get_db)):
    # Process-local limit is sufficient for laptop use; reverse-proxy limits needed for multi-worker online use.
    now = utcnow().timestamp()
    key = request.client.host if request.client else 'unknown'
    attempts = request.app.state.login_attempts
    attempts[key] = [t for t in attempts.get(key, []) if now - t < 60]
    if len(attempts[key]) >= 10:
        raise HTTPException(429, 'تعداد تلاش زیاد است. یک دقیقه دیگر دوباره امتحان کنید.')
    attempts[key].append(now)
    user = db.scalar(select(User).where(User.username == body.username))
    if not user or not verify_password(body.password, user.password_hash) or not user.is_active:
        raise HTTPException(401, 'نام کاربری یا رمز عبور درست نیست.')
    token = secrets.token_urlsafe(48)
    db.add(AuthSession(user_id=user.id, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=utcnow() + timedelta(hours=8)))
    db.commit()
    return {'access_token': token, 'token_type': 'bearer', 'user': user_data(user)}


@router.get('/auth/me')
def me(user=Depends(current_user)):
    return user_data(user)


@router.post('/auth/logout')
def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer), user=Depends(current_user), db=Depends(get_db)):
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hashlib.sha256(credentials.credentials.encode()).hexdigest()))
    db.delete(session)
    db.commit()
    return {'message': 'از حساب خارج شدید.'}


@router.post('/auth/change-password')
def change_password(body: PasswordChange, user=Depends(current_user), db=Depends(get_db)):
    from shared.audit import log_action
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, 'رمز عبور فعلی درست نیست.')
    user.password_hash = hash_password(body.new_password)
    for session in db.scalars(select(AuthSession).where(AuthSession.user_id == user.id)):
        db.delete(session)
    log_action(db, user, 'change_password', 'user', user.id, 'گذرواژه تغییر کرد؛ همه نشست‌ها باطل شدند.')
    db.commit()
    return {'message': 'رمز عبور تغییر کرد. دوباره وارد شوید.'}


@router.get('/users')
def users(q: str = Query('', max_length=100), page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100), user=Depends(require_admin), db=Depends(get_db)):
    statement = select(User).where(or_(User.username.contains(q, autoescape=True), User.full_name.contains(q, autoescape=True))).order_by(User.created_at.desc(), User.id)
    total_result = paginate(db, statement, page, page_size)
    for item in total_result['items']:
        item.pop('password_hash', None)
    return total_result


@router.post('/users', status_code=201)
def create_user(body: CreateUser, request: Request, user=Depends(require_admin), db=Depends(get_db)):
    from shared.audit import log_action
    values = body.model_dump(exclude={'password'})
    validate_employee_link(request, db, body.employee_id)
    row = User(**values, password_hash=hash_password(body.password))
    db.add(row)
    db.flush()
    log_action(db, user, 'create', 'user', row.id)
    db.commit()
    return user_data(row)


@router.patch('/users/{record_id}')
def update_user(record_id: str, body: UpdateUser, request: Request, user=Depends(require_admin), db=Depends(get_db)):
    from shared.audit import log_action
    row = db.get(User, record_id)
    if not row:
        raise HTTPException(404, 'کاربر یافت نشد.')
    changes = body.model_dump(exclude_unset=True)
    if any(value is None for key, value in changes.items() if key != 'employee_id'):
        raise HTTPException(422, 'مقدار خالی برای این فیلد مجاز نیست.')
    if row.id == user.id and (changes.get('role', 'admin') != 'admin' or changes.get('is_active') is False):
        raise HTTPException(409, 'امکان حذف دسترسی مدیریت حساب فعلی وجود ندارد.')
    if 'employee_id' in changes:
        validate_employee_link(request, db, changes['employee_id'])
    for key, value in changes.items():
        setattr(row, key, value)
    log_action(db, user, 'update', 'user', row.id)
    db.commit()
    return user_data(row)


@router.get('/audit-logs')
def audit_logs(page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100), q: str = Query('', max_length=100), user=Depends(require_manager), db=Depends(get_db)):
    from shared.audit import AuditLog
    return paginate(db, select(AuditLog).where(or_(*[column.contains(q, autoescape=True) for column in (AuditLog.entity, AuditLog.username, AuditLog.action, AuditLog.details, AuditLog.entity_id)])).order_by(AuditLog.created_at.desc(), AuditLog.id), page, page_size)


def validate_employee_link(request, db, employee_id):
    # Only personnel owns employee records. Other systems hold a validated UUID reference.
    if employee_id and request.app.state.service == 'personnel':
        from services.personnel.models import Employee
        if db.get(Employee, employee_id) is None:
            raise HTTPException(422, 'پرونده‌ای با این شناسه کارمند در سامانه پرسنلی وجود ندارد.')


def seed_users(db, demo=True):
    if db.scalar(select(User.id).limit(1)):
        return
    if demo:
        for role, name in [('admin', 'مدیر نمونه'), ('manager', 'کارشناس نمونه'), ('staff', 'کارمند نمونه')]:
            db.add(User(username=role, full_name=name, role=role, password_hash=hash_password(role + '12345')))
    else:
        password = os.getenv('ADMIN_PASSWORD', '')
        if len(password) < 12:
            raise RuntimeError('Set ADMIN_PASSWORD to at least 12 characters when SEED_DEMO=false.')
        db.add(User(username=os.getenv('ADMIN_USERNAME', 'admin'), full_name='مدیر سامانه', role='admin', password_hash=hash_password(password)))
    db.commit()
