from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import AuditMixin


class Course(AuditMixin, Base):
    __tablename__ = "course"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    course_name: Mapped[str] = mapped_column(String(128), nullable=False)
    course_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    credit: Mapped[float | None] = mapped_column(Float, nullable=True)
    hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    course_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    college_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("college.id"), nullable=True, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
