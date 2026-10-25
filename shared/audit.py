from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from shared.database import Base
from shared.models import Record


class AuditLog(Record, Base):
    __tablename__ = 'audit_logs'
    user_id: Mapped[str] = mapped_column(String(36))
    username: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(80))
    entity: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(100))
    details: Mapped[str] = mapped_column(Text, default='')


def log_action(db, user, action, entity, entity_id, details=''):
    db.add(AuditLog(user_id=user.id, username=user.username, action=action, entity=entity, entity_id=str(entity_id), details=details))
