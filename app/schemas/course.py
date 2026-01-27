from pydantic import BaseModel


class CourseCreate(BaseModel):
    course_name: str
    course_code: str
    credit: float | None = None
    hours: int | None = None
    course_type: str | None = None
    college_id: int | None = None
    description: str | None = None


class CourseUpdate(BaseModel):
    course_name: str | None = None
    course_code: str | None = None
    credit: float | None = None
    hours: int | None = None
    course_type: str | None = None
    college_id: int | None = None
    description: str | None = None
    is_deleted: bool | None = None


class CourseOut(BaseModel):
    id: int
    course_name: str
    course_code: str
    credit: float | None = None
    hours: int | None = None
    course_type: str | None = None
    college_id: int | None = None
    description: str | None = None
    is_deleted: bool

    class Config:
        from_attributes = True
