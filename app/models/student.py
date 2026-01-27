from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import AuditMixin


class Student(AuditMixin, Base):
    __tablename__ = "student"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    student_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    real_name: Mapped[str] = mapped_column(String(64), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    id_card: Mapped[str | None] = mapped_column(String(32), nullable=True)
    birth_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    class_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("class.id"), nullable=True, index=True
    )
    major_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("major.id"), nullable=True, index=True
    )
    college_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("college.id"), nullable=True, index=True
    )
    enroll_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
