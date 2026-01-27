from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.deps import get_current_admin, get_db
from app.models import Admin, ClassModel, College, Course, Major, Student, Teacher
from app.schemas.admin import AdminCreate, AdminOut, AdminUpdate
from app.schemas.class_schema import ClassCreate, ClassOut, ClassUpdate
from app.schemas.college import CollegeCreate, CollegeOut, CollegeUpdate
from app.schemas.course import CourseCreate, CourseOut, CourseUpdate
from app.schemas.major import MajorCreate, MajorOut, MajorUpdate
from app.schemas.response import ListResponse, Meta, OkResponse
from app.schemas.student import StudentCreate, StudentOut, StudentUpdate
from app.schemas.teacher import TeacherCreate, TeacherOut, TeacherUpdate

router = APIRouter()

TABLE_MAP = {
    "admin": {
        "model": Admin,
        "create": AdminCreate,
        "update": AdminUpdate,
        "out": AdminOut,
        "password_field": "password",
    },
    "college": {"model": College, "create": CollegeCreate, "update": CollegeUpdate, "out": CollegeOut},
    "major": {"model": Major, "create": MajorCreate, "update": MajorUpdate, "out": MajorOut},
    "class": {"model": ClassModel, "create": ClassCreate, "update": ClassUpdate, "out": ClassOut},
    "student": {"model": Student, "create": StudentCreate, "update": StudentUpdate, "out": StudentOut},
    "teacher": {"model": Teacher, "create": TeacherCreate, "update": TeacherUpdate, "out": TeacherOut},
    "course": {"model": Course, "create": CourseCreate, "update": CourseUpdate, "out": CourseOut},
}

RESERVED_PARAMS = {"offset", "limit", "sort_by", "sort_dir", "only_deleted", "q"}


def get_table(name: str) -> dict:
    if name not in TABLE_MAP:
        raise HTTPException(status_code=404, detail="Unknown table")
    return TABLE_MAP[name]


def cast_value(model, key: str, value: str):
    column = getattr(model, key).property.columns[0]
    try:
        python_type = column.type.python_type
    except (NotImplementedError, AttributeError):
        # 只有当该类型确实没有定义 python_type 时才返回原值
        return value
    except Exception as e:
        # 其他预料之外的错误（如模型配置错误）依然可以记录或抛出
        raise e

    if python_type is bool:
        return value.lower() in {"1", "true", "yes"}
    try:
        return python_type(value)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid filter value for {key}")


def apply_filters(query, model, params: dict, only_deleted: bool):
    if only_deleted:
        query = query.filter(model.is_deleted == True)
    else:
        query = query.filter(model.is_deleted == False)

    for key, value in params.items():
        if hasattr(model, key) and value is not None:
            query = query.filter(getattr(model, key) == cast_value(model, key, value))
    return query


def apply_search(query, model, keyword: str | None):
    if not keyword:
        return query

    conditions = []
    for column in model.__table__.columns:
        try:
            if column.type.python_type is str:
                conditions.append(column.like(f"%{keyword}%"))
        except (NotImplementedError, AttributeError):
            continue
    if conditions:
        query = query.filter(or_(*conditions))
    return query


def apply_sort(query, model, sort_by: str | None, sort_dir: str | None):
    if not sort_by:
        return query
    fields = [item.strip() for item in sort_by.split(",") if item.strip()]
    dirs = []
    if sort_dir:
        dirs = [item.strip().lower() for item in sort_dir.split(",") if item.strip()]
    order_by = []
    for idx, field in enumerate(fields):
        if not hasattr(model, field):
            continue
        direction = dirs[idx] if idx < len(dirs) else "asc"
        column = getattr(model, field)
        order_by.append(desc(column) if direction == "desc" else asc(column))
    if order_by:
        query = query.order_by(*order_by)
    return query


@router.get("/api/{table}/list", response_model=ListResponse)
def list_items(
    table: str,
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    sort_by: str | None = None,
    sort_dir: str | None = None,
    only_deleted: bool = False,
    q: str | None = None,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    meta = get_table(table)
    model = meta["model"]

    params = {k: v for k, v in request.query_params.items() if k not in RESERVED_PARAMS}
    query = db.query(model)
    query = apply_filters(query, model, params, only_deleted)
    query = apply_search(query, model, q)
    total = query.count()
    query = apply_sort(query, model, sort_by, sort_dir)
    items = query.offset(offset).limit(limit).all()

    return ListResponse(
        data=jsonable_encoder(items),
        meta=Meta(offset=offset, limit=limit, total=total),
    )


@router.get("/api/{table}/{item_id}", response_model=OkResponse)
def get_item(
    table: str,
    item_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    meta = get_table(table)
    model = meta["model"]
    item = db.query(model).filter(model.id == item_id, model.is_deleted == False).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return OkResponse(data=jsonable_encoder(item))


@router.post("/api/{table}/create", response_model=OkResponse)
def create_item(
    table: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    meta = get_table(table)
    model = meta["model"]
    schema = meta["create"]
    data = schema(**payload).model_dump()

    if table == "admin":
        password = data.pop("password")
        data["password_hash"] = hash_password(password)

    data["created_by"] = current_admin.id
    data["updated_by"] = current_admin.id

    item = model(**data)
    db.add(item)
    db.commit()
    db.refresh(item)
    return OkResponse(data=jsonable_encoder(item))


@router.put("/api/{table}/{item_id}", response_model=OkResponse)
def update_item(
    table: str,
    item_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    meta = get_table(table)
    model = meta["model"]
    schema = meta["update"]
    data = schema(**payload).dict(exclude_unset=True)

    item = db.query(model).filter(model.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")

    if item.is_deleted:
        if data.keys() != {"is_deleted"} or data.get("is_deleted") is not False:
            raise HTTPException(status_code=400, detail="Only restore is allowed")
        item.is_deleted = False
    else:
        if "is_deleted" in data:
            raise HTTPException(status_code=400, detail="Use DELETE to remove records")
        if table == "admin" and "password" in data:
            item.password_hash = hash_password(data.pop("password"))
        for key, value in data.items():
            setattr(item, key, value)

    item.updated_by = current_admin.id
    db.add(item)
    db.commit()
    db.refresh(item)
    return OkResponse(data=jsonable_encoder(item))


@router.delete("/api/{table}/{item_id}", response_model=OkResponse)
def delete_item(
    table: str,
    item_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    meta = get_table(table)
    model = meta["model"]
    item = db.query(model).filter(model.id == item_id, model.is_deleted == False).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")

    item.is_deleted = True
    item.updated_by = current_admin.id
    db.add(item)
    db.commit()
    db.refresh(item)
    return OkResponse(data=jsonable_encoder(item))
