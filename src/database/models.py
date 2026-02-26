# src/database/models.py

import enum
from datetime import datetime

from sqlalchemy import BigInteger, String, ForeignKey, Enum, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class UserRole(enum.Enum):
    admin = "admin"
    content_maker = "content_maker"
    mobilographer = "mobilographer"
    copywriter = "copywriter"
    marketer = "marketer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)

    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="userrole"), nullable=False)

    personal_sheet_id: Mapped[str] = mapped_column(String(100), nullable=True)
    worksheet_name: Mapped[str] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Mobilographer bo'lgan userga biriktirilgan tasklar
    tasks = relationship(
        "Task",
        back_populates="mobilographer",
        foreign_keys="[Task.mobilographer_id]",
        primaryjoin="User.telegram_id==Task.mobilographer_id",
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)

    task_name: Mapped[str] = mapped_column(Text, nullable=False)
    scenario: Mapped[str] = mapped_column(Text, nullable=False)

    deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    priority: Mapped[str] = mapped_column(String(50), nullable=False)

    # Umumiy status: Yangi / Jarayonda / Tekshirilmoqda / Bajarildi ...
    status: Mapped[str] = mapped_column(String(50), default="Yangi", nullable=False)

    # Ishtirokchilarning telegram IDlari
    content_maker_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    mobilographer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    copywriter_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    marketer_id: Mapped[int] = mapped_column(BigInteger, nullable=True)

    # Bajarilgan vaqtlar (kechikishni hisoblash uchun)
    mobi_done_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    copy_done_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    market_done_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Yakuniy post link (Sheets AH)
    final_link: Mapped[str] = mapped_column(Text, nullable=True)

    # Google Sheets'dagi qator raqami
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationship
    mobilographer = relationship(
        "User",
        back_populates="tasks",
        foreign_keys=[mobilographer_id],
        primaryjoin="Task.mobilographer_id==User.telegram_id",
    )