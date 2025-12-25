import enum
from sqlalchemy import BigInteger, String, ForeignKey, Enum, DateTime, Boolean, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB # Feedbacklar uchun


class UserRole(enum.Enum):
    admin = "admin"
    director = "director"
    employee = "employee"
    super_employee = "super_employee"

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100))
    username: Mapped[str] = mapped_column(String(50), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.employee) # ✅
    personal_sheet_id: Mapped[str] = mapped_column(String(100), nullable=True)
    worksheet_name: Mapped[str] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    tasks = relationship("Task", back_populates="user")


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    assigner_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    task_name: Mapped[str] = mapped_column(Text)
    deadline: Mapped[str] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="Yangi")
    row_index: Mapped[int] = mapped_column(Integer)
    # Feedbacklarni saqlash: {"admin_id": {"name": "Shaxboz", "text": "Yaxshi", "status": "done"}}
    feedbacks: Mapped[dict] = mapped_column(JSONB, default={}, server_default='{}') 

    user = relationship("User", back_populates="tasks")