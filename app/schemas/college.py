from pydantic import BaseModel


class CollegeCreate(BaseModel):
    college_name: str
    college_code: str
    description: str | None = None


class CollegeUpdate(BaseModel):
    college_name: str | None = None
    college_code: str | None = None
    description: str | None = None
    is_deleted: bool | None = None


class CollegeOut(BaseModel):
    id: int
    college_name: str
    college_code: str
    description: str | None = None
    is_deleted: bool

    class Config:
        from_attributes = True
