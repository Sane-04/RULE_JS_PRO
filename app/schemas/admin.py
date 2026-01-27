from pydantic import BaseModel


class AdminProfile(BaseModel):
    id: int
    username: str
    real_name: str | None = None
    phone: str | None = None
    email: str | None = None
    status: str

    class Config:
        from_attributes = True


class AdminCreate(BaseModel):
    username: str
    password: str
    real_name: str | None = None
    phone: str | None = None
    email: str | None = None
    status: str | None = None


class AdminUpdate(BaseModel):
    password: str | None = None
    real_name: str | None = None
    phone: str | None = None
    email: str | None = None
    status: str | None = None
    is_deleted: bool | None = None


class AdminOut(BaseModel):
    id: int
    username: str
    real_name: str | None = None
    phone: str | None = None
    email: str | None = None
    status: str
    is_deleted: bool

    class Config:
        from_attributes = True
