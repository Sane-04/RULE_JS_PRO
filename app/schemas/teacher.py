from datetime import date
from pydantic import BaseModel


class TeacherCreate(BaseModel):
    teacher_no: str
    real_name: str
    gender: str | None = None
    id_card: str | None = None
    birth_date: date | None = None
    phone: str | None = None
    email: str | None = None
    title: str | None = None
    college_id: int | None = None
    status: str | None = None


class TeacherUpdate(BaseModel):
    teacher_no: str | None = None
    real_name: str | None = None
    gender: str | None = None
    id_card: str | None = None
    birth_date: date | None = None
    phone: str | None = None
    email: str | None = None
    title: str | None = None
    college_id: int | None = None
    status: str | None = None
    is_deleted: bool | None = None


class TeacherOut(BaseModel):
    id: int
    teacher_no: str
    real_name: str
    gender: str | None = None
    id_card: str | None = None
    birth_date: date | None = None
    phone: str | None = None
    email: str | None = None
    title: str | None = None
    college_id: int | None = None
    status: str | None = None
    is_deleted: bool

    class Config:
        from_attributes = True
