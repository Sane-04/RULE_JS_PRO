from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import AuditMixin


class ClassModel(AuditMixin, Base):
    __tablename__ = "class"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    class_name: Mapped[str] = mapped_column(String(128), nullable=False)
    class_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    major_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("major.id"), nullable=False, index=True
    )
    grade_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    head_teacher_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("teacher.id"), nullable=True, index=True
    )
    student_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
