from pydantic import BaseModel


class MajorCreate(BaseModel):
    major_name: str
    major_code: str
    college_id: int
    degree_type: str | None = None
    description: str | None = None


class MajorUpdate(BaseModel):
    major_name: str | None = None
    major_code: str | None = None
    college_id: int | None = None
    degree_type: str | None = None
    description: str | None = None
    is_deleted: bool | None = None


class MajorOut(BaseModel):
    id: int
    major_name: str
    major_code: str
    college_id: int
    degree_type: str | None = None
    description: str | None = None
    is_deleted: bool

    class Config:
        from_attributes = True
