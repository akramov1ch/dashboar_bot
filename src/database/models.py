# src/database/models.py

import enum
from sqlalchemy import BigInteger, String, ForeignKey, Enum, DateTime, Integer, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
from datetime import datetime

class UserRole(enum.Enum):
    admin = "admin"
    content_maker = "content_maker"
    mobilographer = "mobilographer"
    copywriter = "copywriter"
    designer = "designer"
    marketer = "marketer"

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole))
    personal_sheet_id: Mapped[str] = mapped_column(String(100), nullable=True)
    worksheet_name: Mapped[str] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tasks = relationship("Task", back_populates="mobilographer", foreign_keys="[Task.mobilographer_id]")

class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_name: Mapped[str] = mapped_column(Text)
    scenario: Mapped[str] = mapped_column(Text)
    deadline: Mapped[datetime] = mapped_column(DateTime)
    priority: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="Yangi")

    content_maker_id: Mapped[int] = mapped_column(BigInteger)
    mobilographer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"))
    copywriter_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    designer_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    marketer_id: Mapped[int] = mapped_column(BigInteger, nullable=True)

    mobi_done_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    copy_done_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    design_done_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    market_done_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    final_link: Mapped[str] = mapped_column(Text, nullable=True)
    row_index: Mapped[int] = mapped_column(Integer)

    # ✅ NEW: 1-day reminder flags (spam bo'lmasin)
    mobi_reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    copy_reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    design_reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    market_reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    mobilographer = relationship("User", back_populates="tasks", foreign_keys=[mobilographer_id])