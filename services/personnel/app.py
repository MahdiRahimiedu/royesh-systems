from calendar import monthrange
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select, update
from shared.app import create_app
from shared.auth import User, current_user, require_manager
from shared.audit import log_action
from shared.database import get_db, make_database
from shared.utils import paginate, serialize
from .models import Department, Employee, EmploymentContract, Leave, Mission, Adjustment, Payroll
from .schemas import (DepartmentCreate, DepartmentUpdate, EmployeeCreate, EmployeeUpdate,
                      ContractCreate, ContractUpdate, LeaveCreate, MissionCreate, Decision,
                      AdjustmentCreate, PayrollCreate, PayrollUpdate)

engine, SessionLocal, Base = make_database('personnel')
router = APIRouter(prefix='/api/v1', tags=['پرسنلی'])


def get_record(db, model, record_id):
    row = db.get(model, record_id)
    if row is None:
        raise HTTPException(404, 'رکورد مورد نظر یافت نشد.')
    return row


def employee_name(db, employee_id):
    row = db.get(Employee, employee_id)
    return f'{row.first_name} {row.last_name}' if row else 'نامشخص'


def employee_out(db, row):
    department = db.get(Department, row.department_id) if row.department_id else None
    return serialize(row, full_name=f'{row.first_name} {row.last_name}', department_name=department.name if department else '')


def own_scope(statement, model, user):
    if user.role == 'staff':
        statement = statement.where(model.employee_id == (user.employee_id or 'no-employee'))
    return statement


def allowed_employee(db, employee_id, user, active=True):
    if user.role == 'staff' and employee_id != user.employee_id:
        raise HTTPException(403, 'فقط امکان ثبت درخواست برای خودتان وجود دارد.')
    employee = get_record(db, Employee, employee_id)
    if active and employee.status != 'active':
        raise HTTPException(409, 'کارمند باید در وضعیت فعال باشد.')
    return employee


def lock_employee(db, employee_id):
    db.execute(update(Employee).where(Employee.id == employee_id).values(status=Employee.status))
    employee = get_record(db, Employee, employee_id)
    db.refresh(employee)
    return employee


def employee_matches(q):
    return or_((Employee.first_name + ' ' + Employee.last_name).contains(q, autoescape=True),
               Employee.personnel_code.contains(q, autoescape=True))


def validate_status(status, allowed):
    if status and status not in allowed:
        raise HTTPException(422, 'فیلتر وضعیت معتبر نیست.')


def contract_overlap(db, employee_id, start, end, exclude=None):
    statement = select(EmploymentContract.id).where(
        EmploymentContract.employee_id == employee_id, EmploymentContract.status == 'active',
        EmploymentContract.start_date <= (end or date.max),
        or_(EmploymentContract.end_date.is_(None), EmploymentContract.end_date >= start))
    if exclude:
        statement = statement.where(EmploymentContract.id != exclude)
    if db.scalar(statement.limit(1)):
        raise HTTPException(409, 'در این بازه قرارداد استخدامی فعال دیگری برای کارمند وجود دارد.')


def save(db, row, user, entity, action='create'):
    db.add(row)
    db.flush()
    log_action(db, user, action, entity, row.id)
    db.commit()
    return row


def patch_values(body, nullable=()):
    values = body.model_dump(exclude_unset=True)
    if any(value is None and key not in nullable for key, value in values.items()):
        raise HTTPException(422, 'فیلد الزامی نمی‌تواند خالی باشد.')
    return values


def dated_list(db, model, user, q, page, page_size, status=None):
    statement = own_scope(select(model), model, user)
    if status and hasattr(model, 'status'):
        statement = statement.where(model.status == status)
    if q:
        ids = select(Employee.id).where(employee_matches(q))
        searchable = [getattr(model, name).contains(q, autoescape=True) for name in ('title', 'reason', 'destination', 'period', 'notes') if hasattr(model, name)]
        statement = statement.where(or_(model.employee_id.in_(ids), *searchable))
    result = paginate(db, statement.order_by(model.created_at.desc(), model.id), page, page_size)
    for row in result['items']:
        row['employee_name'] = employee_name(db, row['employee_id'])
    return result


@router.get('/departments')
def departments(q: str = Query('', max_length=100), page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100), user=Depends(current_user), db=Depends(get_db)):
    return paginate(db, select(Department).where(or_(Department.name.contains(q, autoescape=True), Department.description.contains(q, autoescape=True))).order_by(Department.name, Department.id), page, page_size)


@router.post('/departments', status_code=201)
def create_department(body: DepartmentCreate, user=Depends(require_manager), db=Depends(get_db)):
    return serialize(save(db, Department(**body.model_dump()), user, 'department'))


@router.patch('/departments/{record_id}')
def update_department(record_id: str, body: DepartmentUpdate, user=Depends(require_manager), db=Depends(get_db)):
    row = get_record(db, Department, record_id)
    for key, value in patch_values(body).items():
        setattr(row, key, value)
    return serialize(save(db, row, user, 'department', 'update'))


@router.get('/employees/lookup')
def lookup(q: str = Query('', max_length=100), page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100), user=Depends(current_user), db=Depends(get_db)):
    statement = select(Employee).where(employee_matches(q))
    if user.role == 'staff':
        statement = statement.where(Employee.id == (user.employee_id or 'none'))
    result = paginate(db, statement.order_by(Employee.personnel_code), page, page_size)
    result['items'] = [{key: item[key] for key in ('id', 'personnel_code', 'first_name', 'last_name', 'job_title', 'status')} | {'full_name': item['first_name'] + ' ' + item['last_name']} for item in result['items']]
    return result


@router.get('/employees')
def employees(q: str = Query('', max_length=100), status: str | None = None, page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100), user=Depends(current_user), db=Depends(get_db)):
    validate_status(status, ('active', 'inactive', 'terminated'))
    statement = select(Employee).where(or_(employee_matches(q), Employee.job_title.contains(q, autoescape=True), Employee.email.contains(q, autoescape=True), Employee.phone.contains(q, autoescape=True)))
    if status:
        statement = statement.where(Employee.status == status)
    if user.role == 'staff':
        statement = statement.where(Employee.id == (user.employee_id or 'none'))
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    items = db.scalars(statement.order_by(Employee.created_at.desc(), Employee.id).offset((page - 1) * page_size).limit(page_size))
    return {'items': [employee_out(db, item) for item in items], 'total': total, 'page': page, 'page_size': page_size}


@router.get('/employees/{record_id}')
def employee_detail(record_id: str, user=Depends(current_user), db=Depends(get_db)):
    if user.role == 'staff' and record_id != user.employee_id:
        raise HTTPException(403, 'دسترسی به پرونده دیگران مجاز نیست.')
    return employee_out(db, get_record(db, Employee, record_id))


@router.post('/employees', status_code=201)
def create_employee(body: EmployeeCreate, user=Depends(require_manager), db=Depends(get_db)):
    if body.department_id:
        get_record(db, Department, body.department_id)
    return employee_out(db, save(db, Employee(**body.model_dump()), user, 'employee'))


@router.patch('/employees/{record_id}')
def update_employee(record_id: str, body: EmployeeUpdate, user=Depends(require_manager), db=Depends(get_db)):
    row = lock_employee(db, record_id)
    values = patch_values(body, ('department_id',))
    if values.get('department_id'):
        get_record(db, Department, values['department_id'])
    if values.get('hire_date') and values['hire_date'] != row.hire_date:
        hire = values['hire_date']
        for model, column in ((EmploymentContract, EmploymentContract.start_date), (Leave, Leave.start_date), (Mission, Mission.start_date), (Adjustment, Adjustment.date)):
            if db.scalar(select(model.id).where(model.employee_id == row.id, column < hire).limit(1)):
                raise HTTPException(409, 'تاریخ استخدام نمی‌تواند بعد از سوابق ثبت‌شده کارمند قرار گیرد.')
        for period in db.scalars(select(Payroll.period).where(Payroll.employee_id == row.id)):
            year, month = map(int, period.split('-'))
            if date(year, month, monthrange(year, month)[1]) < hire:
                raise HTTPException(409, 'تاریخ استخدام با فیش حقوق ثبت‌شده سازگار نیست.')
    for key, value in values.items():
        setattr(row, key, value)
    return employee_out(db, save(db, row, user, 'employee', 'update'))


@router.get('/employment-contracts')
def contracts(q: str = Query('', max_length=100), status: str | None = None, page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100), user=Depends(current_user), db=Depends(get_db)):
    validate_status(status, ('active', 'ended'))
    return dated_list(db, EmploymentContract, user, q, page, page_size, status)


@router.post('/employment-contracts', status_code=201)
def create_contract(body: ContractCreate, user=Depends(require_manager), db=Depends(get_db)):
    employee = lock_employee(db, body.employee_id)
    allowed_employee(db, body.employee_id, user)
    if body.start_date < employee.hire_date:
        raise HTTPException(422, 'شروع قرارداد نباید قبل از تاریخ استخدام باشد.')
    if body.status == 'active':
        contract_overlap(db, employee.id, body.start_date, body.end_date)
    row = EmploymentContract(**body.model_dump())
    save(db, row, user, 'employment_contract')
    return serialize(row, employee_name=employee_name(db, employee.id))


@router.patch('/employment-contracts/{record_id}')
def update_contract(record_id: str, body: ContractUpdate, user=Depends(require_manager), db=Depends(get_db)):
    row = get_record(db, EmploymentContract, record_id)
    lock_employee(db, row.employee_id)
    db.refresh(row)
    values = patch_values(body, ('end_date',))
    if row.status == 'ended':
        raise HTTPException(409, 'قرارداد خاتمه‌یافته قابل تغییر نیست.')
    if values.get('end_date') and values['end_date'] < row.start_date:
        raise HTTPException(422, 'تاریخ پایان نباید قبل از شروع باشد.')
    if values.get('status', row.status) == 'active':
        contract_overlap(db, row.employee_id, row.start_date, values.get('end_date', row.end_date), row.id)
    for key, value in values.items():
        setattr(row, key, value)
    return serialize(save(db, row, user, 'employment_contract', 'update'), employee_name=employee_name(db, row.employee_id))


def check_overlap(db, employee_id, start, end, exclude_id=None):
    for model in (Leave, Mission):
        statement = select(model.id).where(model.employee_id == employee_id, model.status == 'approved', model.start_date <= end, model.end_date >= start)
        if exclude_id:
            statement = statement.where(model.id != exclude_id)
        if db.scalar(statement.limit(1)):
            raise HTTPException(409, 'در این بازه مرخصی یا مأموریت تأییدشده وجود دارد.')


@router.get('/leaves')
def leaves(q: str = Query('', max_length=100), status: str | None = None, page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100), user=Depends(current_user), db=Depends(get_db)):
    validate_status(status, ('pending', 'approved', 'rejected'))
    return dated_list(db, Leave, user, q, page, page_size, status)


@router.post('/leaves', status_code=201)
def create_leave(body: LeaveCreate, user=Depends(current_user), db=Depends(get_db)):
    employee = allowed_employee(db, body.employee_id, user)
    if body.start_date < employee.hire_date:
        raise HTTPException(422, 'درخواست نمی‌تواند قبل از تاریخ استخدام باشد.')
    check_overlap(db, employee.id, body.start_date, body.end_date)
    row = save(db, Leave(**body.model_dump()), user, 'leave')
    return serialize(row, employee_name=employee_name(db, row.employee_id))


@router.get('/missions')
def missions(q: str = Query('', max_length=100), status: str | None = None, page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100), user=Depends(current_user), db=Depends(get_db)):
    validate_status(status, ('pending', 'approved', 'rejected'))
    return dated_list(db, Mission, user, q, page, page_size, status)


@router.post('/missions', status_code=201)
def create_mission(body: MissionCreate, user=Depends(current_user), db=Depends(get_db)):
    employee = allowed_employee(db, body.employee_id, user)
    if body.start_date < employee.hire_date:
        raise HTTPException(422, 'درخواست نمی‌تواند قبل از تاریخ استخدام باشد.')
    if user.role == 'staff' and body.allowance:
        raise HTTPException(403, 'مبلغ فوق‌العاده مأموریت را کارشناس تعیین می‌کند.')
    check_overlap(db, employee.id, body.start_date, body.end_date)
    row = save(db, Mission(**body.model_dump()), user, 'mission')
    return serialize(row, employee_name=employee_name(db, row.employee_id))


def decide(db, model, record_id, body, user):
    if body.allowance is not None and (model is not Mission or body.status != 'approved'):
        raise HTTPException(422, 'مبلغ فقط هنگام تأیید مأموریت قابل تعیین است.')
    row = get_record(db, model, record_id)
    if row.status != 'pending':
        raise HTTPException(409, 'این درخواست قبلاً تعیین تکلیف شده است.')
    # Lock the employee row to serialize overlapping approvals on PostgreSQL/SQLite.
    lock_employee(db, row.employee_id)
    db.refresh(row)
    if row.status != 'pending':
        raise HTTPException(409, 'این درخواست قبلاً تعیین تکلیف شده است.')
    if body.status == 'approved':
        allowed_employee(db, row.employee_id, user)
        employee = get_record(db, Employee, row.employee_id)
        if row.start_date < employee.hire_date:
            raise HTTPException(409, 'درخواست با تاریخ استخدام فعلی سازگار نیست.')
        check_overlap(db, row.employee_id, row.start_date, row.end_date, row.id)
        allowance = body.allowance if body.allowance is not None else (row.allowance if model is Mission else 0)
        if model is Mission and allowance and db.scalar(select(Payroll.id).where(Payroll.employee_id == row.employee_id, Payroll.period == row.start_date.strftime('%Y-%m'))):
            raise HTTPException(409, 'حقوق این دوره صادر شده است؛ ابتدا دوره بعد را برای مأموریت انتخاب کنید.')
    changes = {'status': body.status, 'decision_comment': body.comment}
    if model is Mission and body.allowance is not None:
        changes['allowance'] = body.allowance
    changed = db.execute(update(model).where(model.id == record_id, model.status == 'pending').values(**changes))
    if changed.rowcount != 1:
        raise HTTPException(409, 'درخواست قبلاً تعیین تکلیف شده است.')
    log_action(db, user, body.status, 'mission' if model is Mission else 'leave', record_id, body.comment)
    db.commit()
    db.refresh(row)
    return serialize(row, employee_name=employee_name(db, row.employee_id))


@router.post('/leaves/{record_id}/decision')
def decide_leave(record_id: str, body: Decision, user=Depends(require_manager), db=Depends(get_db)):
    return decide(db, Leave, record_id, body, user)


@router.post('/missions/{record_id}/decision')
def decide_mission(record_id: str, body: Decision, user=Depends(require_manager), db=Depends(get_db)):
    return decide(db, Mission, record_id, body, user)


@router.get('/adjustments')
def adjustments(q: str = Query('', max_length=100), page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100), user=Depends(current_user), db=Depends(get_db)):
    return dated_list(db, Adjustment, user, q, page, page_size)


@router.post('/adjustments', status_code=201)
def create_adjustment(body: AdjustmentCreate, user=Depends(require_manager), db=Depends(get_db)):
    allowed_employee(db, body.employee_id, user)
    db.execute(update(Employee).where(Employee.id == body.employee_id).values(status=Employee.status))
    db.expire_all()
    employee = allowed_employee(db, body.employee_id, user)
    if body.date < employee.hire_date:
        raise HTTPException(422, 'تاریخ تعدیل حقوق نمی‌تواند قبل از استخدام باشد.')
    if db.scalar(select(Payroll.id).where(Payroll.employee_id == body.employee_id, Payroll.period == body.date.strftime('%Y-%m'))):
        raise HTTPException(409, 'حقوق این دوره صادر شده است. اصلاحیه را در دوره بعد ثبت کنید.')
    row = save(db, Adjustment(**body.model_dump()), user, 'adjustment')
    return serialize(row, employee_name=employee_name(db, row.employee_id))


@router.get('/payrolls')
def payrolls(q: str = Query('', max_length=100), status: str | None = None, page: int = Query(1, ge=1, le=1_000_000), page_size: int = Query(20, ge=1, le=100), user=Depends(current_user), db=Depends(get_db)):
    validate_status(status, ('draft', 'paid'))
    return dated_list(db, Payroll, user, q, page, page_size, status)


@router.post('/payrolls', status_code=201)
def create_payroll(body: PayrollCreate, user=Depends(require_manager), db=Depends(get_db)):
    employee = allowed_employee(db, body.employee_id, user)
    db.execute(update(Employee).where(Employee.id == employee.id).values(status=Employee.status))
    db.refresh(employee)
    if employee.status != 'active':
        raise HTTPException(409, 'کارمند باید در وضعیت فعال باشد.')
    year, month = map(int, body.period.split('-'))
    if not 1900 <= year <= 2200:
        raise HTTPException(422, 'سال دوره باید بین ۱۹۰۰ و ۲۲۰۰ میلادی باشد.')
    start, end = date(year, month, 1), date(year, month, monthrange(year, month)[1])
    if end < employee.hire_date:
        raise HTTPException(422, 'دوره حقوق قبل از استخدام است.')
    adjustments = db.scalars(select(Adjustment).where(Adjustment.employee_id == employee.id, Adjustment.date >= start, Adjustment.date <= end)).all()
    rewards = sum(row.amount for row in adjustments if row.kind == 'reward')
    penalties = sum(row.amount for row in adjustments if row.kind == 'penalty')
    allowance = db.scalar(select(func.coalesce(func.sum(Mission.allowance), 0)).where(Mission.employee_id == employee.id, Mission.status == 'approved', Mission.start_date >= start, Mission.start_date <= end))
    total = employee.base_salary + body.bonus + rewards + allowance - body.deduction - penalties
    if total < 0:
        raise HTTPException(422, 'مجموع کسورات بیشتر از حقوق و مزایا است.')
    if total > 1_000_000_000_000_000:
        raise HTTPException(422, 'مبلغ فیش از سقف مجاز سامانه بیشتر است.')
    row = Payroll(**body.model_dump(), base_salary=employee.base_salary, rewards=rewards, penalties=penalties, mission_allowance=allowance, total=total)
    save(db, row, user, 'payroll')
    return serialize(row, employee_name=employee_name(db, row.employee_id))


@router.patch('/payrolls/{record_id}')
def update_payroll(record_id: str, body: PayrollUpdate, user=Depends(require_manager), db=Depends(get_db)):
    row = get_record(db, Payroll, record_id)
    changes = patch_values(body)
    bonus, deduction = changes.get('bonus', row.bonus), changes.get('deduction', row.deduction)
    total = row.base_salary + bonus + row.rewards + row.mission_allowance - deduction - row.penalties
    if total < 0 or total > 1_000_000_000_000_000:
        raise HTTPException(422, 'جمع خالص حقوق خارج از بازه مجاز است.')
    # Atomically use the latest unchanged components; a concurrent payment/patch must not be overwritten.
    changed = db.execute(update(Payroll).where(Payroll.id == row.id, Payroll.status == 'draft', Payroll.bonus == row.bonus, Payroll.deduction == row.deduction).values(bonus=bonus, deduction=deduction, total=total))
    if changed.rowcount != 1:
        raise HTTPException(409, 'فیش پرداخت شده یا هم‌زمان تغییر کرده است. اطلاعات را تازه‌سازی کنید.')
    log_action(db, user, 'update', 'payroll', row.id)
    db.commit()
    db.refresh(row)
    return serialize(row, employee_name=employee_name(db, row.employee_id))


@router.post('/payrolls/{record_id}/pay')
def pay_payroll(record_id: str, user=Depends(require_manager), db=Depends(get_db)):
    row = get_record(db, Payroll, record_id)
    changed = db.execute(update(Payroll).where(Payroll.id == row.id, Payroll.status == 'draft').values(status='paid'))
    if changed.rowcount != 1:
        raise HTTPException(409, 'این فیش قبلاً پرداخت شده است.')
    log_action(db, user, 'pay', 'payroll', row.id)
    db.commit()
    db.refresh(row)
    return serialize(row, employee_name=employee_name(db, row.employee_id))


@router.get('/dashboard')
def dashboard(user=Depends(current_user), db=Depends(get_db)):
    if user.role == 'staff':
        employee = db.get(Employee, user.employee_id) if user.employee_id else None
        pending = sum(db.scalar(select(func.count()).select_from(model).where(model.employee_id == (user.employee_id or 'none'), model.status == 'pending')) for model in (Leave, Mission))
        return {'metrics': [{'label': 'درخواست در انتظار', 'value': pending}, {'label': 'حقوق پایه شما', 'value': employee.base_salary if employee else 0, 'unit': 'تومان'}], 'recent': [], 'notices': [{'title': 'پنل شخصی', 'detail': 'فقط پرونده و درخواست‌های خودتان نمایش داده می‌شود.'}]}
    employees_count = db.scalar(select(func.count()).select_from(Employee).where(Employee.status == 'active'))
    pending = db.scalar(select(func.count()).select_from(Leave).where(Leave.status == 'pending')) + db.scalar(select(func.count()).select_from(Mission).where(Mission.status == 'pending'))
    drafts = db.scalar(select(func.coalesce(func.sum(Payroll.total), 0)).where(Payroll.status == 'draft'))
    recent = db.scalars(select(Employee).order_by(Employee.created_at.desc()).limit(5))
    return {'metrics': [{'label': 'همکاران فعال', 'value': employees_count, 'unit': 'نفر'}, {'label': 'واحد سازمانی', 'value': db.scalar(select(func.count()).select_from(Department)), 'unit': 'واحد'}, {'label': 'درخواست در انتظار', 'value': pending}, {'label': 'حقوق آماده پرداخت', 'value': drafts, 'unit': 'تومان'}], 'recent': [{'title': f'{e.first_name} {e.last_name}', 'subtitle': e.job_title, 'status': e.status, 'date': e.hire_date.isoformat()} for e in recent], 'notices': [{'title': 'محاسبات آموزشی حقوق', 'detail': 'حقوق پایه + مزایا + تشویقی + مأموریت − کسورات − جریمه؛ دوره‌ها میلادی هستند و اتصال بانکی وجود ندارد.'}]}


def seed(db):
    if db.scalar(select(Department.id).limit(1)):
        return
    departments = [Department(name='توسعه نرم‌افزار', description='توسعه محصولات و سامانه‌های سفارشی'), Department(name='طراحی محصول', description='تجربه کاربری و طراحی رابط'), Department(name='عملیات و پشتیبانی', description='زیرساخت، منابع انسانی و پشتیبانی')]
    db.add_all(departments)
    db.flush()
    names = [('نگار', 'احمدی', 'توسعه‌دهنده ارشد', 0, 48_000_000), ('امیرعلی', 'رضایی', 'توسعه‌دهنده فرانت‌اند', 0, 36_000_000), ('سارا', 'کریمی', 'طراح محصول', 1, 39_000_000), ('محمد', 'موسوی', 'کارشناس پشتیبانی', 2, 28_000_000), ('هستی', 'نوری', 'مهندس تضمین کیفیت', 0, 32_000_000), ('رضا', 'صالحی', 'مدیر پروژه', 2, 52_000_000)]
    employees = []
    for index, (first, last, title, dept, salary) in enumerate(names):
        row = Employee(id=f'10000000-0000-4000-8000-{index+1:012}', personnel_code=f'EMP-{index+1:03}', first_name=first, last_name=last, job_title=title, department_id=departments[dept].id, base_salary=salary, hire_date=date(2025, 1 + index, 10), email=f'employee{index+1}@example.com', phone=f'0912000000{index}')
        employees.append(row)
        db.add(row)
    db.flush()
    staff = db.scalar(select(User).where(User.username == 'staff'))
    if staff:
        staff.employee_id = employees[0].id
    today = date.today()
    db.add(Leave(employee_id=employees[1].id, type='annual', start_date=today, end_date=today, reason='امور شخصی'))
    db.add(Mission(employee_id=employees[5].id, title='جلسه تحلیل نیازمندی', destination='دفتر مشتری', start_date=today, end_date=today, allowance=800_000, reason='شروع پروژه سامانه پشتیبانی'))
    for employee in employees:
        db.add(EmploymentContract(employee_id=employee.id, title='قرارداد همکاری سالانه', start_date=employee.hire_date, end_date=date(2027, 12, 31), base_salary=employee.base_salary))
    db.flush()


app = create_app('personnel', 'رویش | سامانه پرسنلی', Base, engine, SessionLocal, seed)
app.include_router(router)
