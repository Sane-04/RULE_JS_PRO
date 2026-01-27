from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import AuditMixin


class Major(AuditMixin, Base):
    __tablename__ = "major"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    major_name: Mapped[str] = mapped_column(String(128), nullable=False)
    major_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    college_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("college.id"), nullable=False, index=True
    )
    degree_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
