from pydantic import BaseModel


class ClassCreate(BaseModel):
    class_name: str
    class_code: str
    major_id: int
    grade_year: int | None = None
    head_teacher_id: int | None = None
    student_count: int | None = None


class ClassUpdate(BaseModel):
    class_name: str | None = None
    class_code: str | None = None
    major_id: int | None = None
    grade_year: int | None = None
    head_teacher_id: int | None = None
    student_count: int | None = None
    is_deleted: bool | None = None


class ClassOut(BaseModel):
    id: int
    class_name: str
    class_code: str
    major_id: int
    grade_year: int | None = None
    head_teacher_id: int | None = None
    student_count: int | None = None
    is_deleted: bool

    class Config:
        from_attributes = True
