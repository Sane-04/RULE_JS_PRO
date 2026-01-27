from datetime import date
from pydantic import BaseModel


class StudentCreate(BaseModel):
    student_no: str
    real_name: str
    gender: str | None = None
    id_card: str | None = None
    birth_date: date | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    class_id: int | None = None
    major_id: int | None = None
    college_id: int | None = None
    enroll_year: int | None = None
    status: str | None = None


class StudentUpdate(BaseModel):
    student_no: str | None = None
    real_name: str | None = None
    gender: str | None = None
    id_card: str | None = None
    birth_date: date | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    class_id: int | None = None
    major_id: int | None = None
    college_id: int | None = None
    enroll_year: int | None = None
    status: str | None = None
    is_deleted: bool | None = None


class StudentOut(BaseModel):
    id: int
    student_no: str
    real_name: str
    gender: str | None = None
    id_card: str | None = None
    birth_date: date | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    class_id: int | None = None
    major_id: int | None = None
    college_id: int | None = None
    enroll_year: int | None = None
    status: str | None = None
    is_deleted: bool

    class Config:
        from_attributes = True
