from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import AuditMixin


class College(AuditMixin, Base):
    __tablename__ = "college"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    college_name: Mapped[str] = mapped_column(String(128), nullable=False)
    college_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
