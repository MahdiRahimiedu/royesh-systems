from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.inspection import inspect


def serialize(record, **extra):
    result = {}
    for column in inspect(record).mapper.column_attrs:
        value = getattr(record, column.key)
        if isinstance(value, datetime):
            value = value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.isoformat()
        elif isinstance(value, date):
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = int(value) if value == value.to_integral() else str(value)
        result[column.key] = value
    result.update(extra)
    return result


def paginate(db, statement, page=1, page_size=20):
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    rows = db.scalars(statement.offset((page - 1) * page_size).limit(page_size)).all()
    return {'items': [serialize(row) for row in rows], 'total': total, 'page': page, 'page_size': page_size}
