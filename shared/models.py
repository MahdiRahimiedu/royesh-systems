from datetime import datetime, timezone
import os
from zoneinfo import ZoneInfo
from uuid import uuid4
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


def utcnow():
    return datetime.now(timezone.utc)


def business_today():
    """Calendar decisions use the company's timezone, independent of the server's clock zone."""
    return utcnow().astimezone(ZoneInfo(os.getenv('BUSINESS_TIMEZONE', 'Asia/Tehran'))).date()


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
