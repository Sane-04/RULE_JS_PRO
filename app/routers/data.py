from datetime import date, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.deps import get_current_admin, get_db
from app.models import Admin, ClassModel, College, Course, Major, Score, Student, Teacher
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

FK_FILTER_RESOLVERS = {
    "major_id": {"model": Major, "code_fields": ["major_code"], "name_fields": ["major_name"]},
    "college_id": {"model": College, "code_fields": ["college_code"], "name_fields": ["college_name"]},
    "class_id": {"model": ClassModel, "code_fields": ["class_code"], "name_fields": ["class_name"]},
    "head_teacher_id": {"model": Teacher, "code_fields": ["teacher_no"], "name_fields": ["real_name"]},
    "teacher_id": {"model": Teacher, "code_fields": ["teacher_no"], "name_fields": ["real_name"]},
    "course_id": {"model": Course, "code_fields": ["course_code"], "name_fields": ["course_name"]},
    "student_id": {"model": Student, "code_fields": ["student_no"], "name_fields": ["real_name"]},
}


def get_table(name: str) -> dict:
    """
    作用：根据表名获取对应的模型与校验配置。
    输入参数：
    - name: 前端传入的表名字符串。
    输出参数：
    - dict: TABLE_MAP 中对应表的配置字典。
    """
    if name not in TABLE_MAP:
        raise HTTPException(status_code=404, detail="Unknown table")
    return TABLE_MAP[name]


@router.get("/{table}/list", response_model=ListResponse)
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
    """
    作用：通用分页列表查询接口，支持过滤、关键词搜索与排序。
    输入参数：
    - table: 业务表名。
    - request: FastAPI 请求对象，用于读取 query 参数。
    - offset: 分页起始偏移。
    - limit: 分页条数。
    - sort_by: 排序字段，支持逗号分隔。
    - sort_dir: 排序方向，支持逗号分隔，值为 asc/desc。
    - only_deleted: 是否只查询已删除数据。
    - q: 关键词搜索文本。
    - db: 数据库会话。
    - current_admin: 当前登录管理员（鉴权依赖）。
    输出参数：
    - ListResponse: 列表数据与分页元信息。
    """

    def _helper_resolve_foreign_key_value(key: str, value: str) -> tuple[bool, int | None]:
        """
        作用：将外键过滤值从业务编码/名称解析为真实数值 ID。
        输入参数：
        - key: 外键字段名，如 major_id。
        - value: 前端传入的过滤值。
        输出参数：
        - tuple[bool, int | None]:
          第一个值表示当前字段是否由该解析器负责；
          第二个值为解析后的 ID，解析失败时为 None。
        """
        resolver = FK_FILTER_RESOLVERS.get(key)
        if not resolver:
            return False, None

        if not isinstance(value, str):
            return True, None
        lookup_text = value.strip()
        if not lookup_text:
            return True, None

        ref_model = resolver["model"]
        code_fields = resolver.get("code_fields", [])
        name_fields = resolver.get("name_fields", [])

        for field_name in code_fields:
            if not hasattr(ref_model, field_name):
                continue
            row = (
                db.query(ref_model.id)
                .filter(getattr(ref_model, field_name) == lookup_text, ref_model.is_deleted == False)
                .order_by(ref_model.id.asc())
                .first()
            )
            if row:
                return True, int(row[0])

        for field_name in name_fields:
            if not hasattr(ref_model, field_name):
                continue
            row = (
                db.query(ref_model.id)
                .filter(getattr(ref_model, field_name) == lookup_text, ref_model.is_deleted == False)
                .order_by(ref_model.id.asc())
                .first()
            )
            if row:
                return True, int(row[0])

        return True, None

    def _helper_cast_value(model, key: str, value: str):
        """
        作用：按模型字段类型把字符串过滤值转换为对应 Python 类型。
        输入参数：
        - model: SQLAlchemy 模型类。
        - key: 字段名。
        - value: 原始过滤值。
        输出参数：
        - 转换后的值；若为空字符串则返回 None。
        """
        column = getattr(model, key).property.columns[0]
        try:
            python_type = column.type.python_type
        except (NotImplementedError, AttributeError):
            # 只有当该类型确实没有定义 python_type 时才返回原值
            return value
        except Exception as e:
            # 其他预料之外的错误（如模型配置错误）依然可以记录或抛出
            raise e

        normalized_value = value.strip() if isinstance(value, str) else value
        if normalized_value == "":
            return None

        if python_type is bool:
            value_text = str(normalized_value).strip().lower()
            if value_text in {"1", "true", "yes", "on"}:
                return True
            if value_text in {"0", "false", "no", "off"}:
                return False
            raise HTTPException(status_code=400, detail=f"Invalid filter value for {key}")

        if python_type is int:
            value_text = str(normalized_value).strip()
            try:
                return int(value_text)
            except Exception:
                try:
                    float_value = float(value_text)
                    if float_value.is_integer():
                        return int(float_value)
                except Exception:
                    pass
            raise HTTPException(status_code=400, detail=f"Invalid filter value for {key}")

        if python_type is float:
            try:
                return float(str(normalized_value).strip())
            except Exception:
                raise HTTPException(status_code=400, detail=f"Invalid filter value for {key}")

        if python_type is date:
            try:
                return date.fromisoformat(str(normalized_value).strip())
            except Exception:
                raise HTTPException(status_code=400, detail=f"Invalid filter value for {key}")

        if python_type is datetime:
            try:
                return datetime.fromisoformat(str(normalized_value).strip())
            except Exception:
                raise HTTPException(status_code=400, detail=f"Invalid filter value for {key}")

        try:
            return python_type(normalized_value)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid filter value for {key}")

    def _helper_apply_filters(query, model, params: dict, only_deleted: bool):
        """
        作用：将删除标记过滤与字段过滤条件应用到查询对象。
        输入参数：
        - query: SQLAlchemy Query 对象。
        - model: SQLAlchemy 模型类。
        - params: 动态过滤参数字典。
        - only_deleted: 是否仅查询已删除数据。
        输出参数：
        - Query: 追加过滤条件后的查询对象。
        """
        if only_deleted:
            query = query.filter(model.is_deleted == True)
        else:
            query = query.filter(model.is_deleted == False)

        for key, value in params.items():
            if hasattr(model, key) and value is not None:
                try:
                    casted_value = _helper_cast_value(model, key, value)
                except HTTPException:
                    resolved, resolved_value = _helper_resolve_foreign_key_value(key, value)
                    if not resolved:
                        raise
                    # 解析失败时使用不可能命中的 ID，返回空结果而非 400。
                    casted_value = -1 if resolved_value is None else resolved_value
                if casted_value is None:
                    continue
                query = query.filter(getattr(model, key) == casted_value)
        return query

    def _helper_apply_search(query, model, keyword: str | None):
        """
        作用：对模型字符串字段与外键关联表名称/编码执行关键词模糊匹配（OR 组合）。
        输入参数：
        - query: SQLAlchemy Query 对象。
        - model: SQLAlchemy 模型类。
        - keyword: 关键词，空值时不追加条件。
        输出参数：
        - Query: 追加搜索条件后的查询对象。
        """
        if not keyword:
            return query

        conditions = []
        for column in model.__table__.columns:
            try:
                if column.type.python_type is str:
                    conditions.append(column.like(f"%{keyword}%"))
            except (NotImplementedError, AttributeError):
                continue

        for fk_key, resolver in FK_FILTER_RESOLVERS.items():
            if not hasattr(model, fk_key):
                continue

            ref_model = resolver["model"]
            ref_conditions = []
            for field_name in resolver.get("code_fields", []):
                if hasattr(ref_model, field_name):
                    ref_conditions.append(getattr(ref_model, field_name).like(f"%{keyword}%"))
            for field_name in resolver.get("name_fields", []):
                if hasattr(ref_model, field_name):
                    ref_conditions.append(getattr(ref_model, field_name).like(f"%{keyword}%"))
            if not ref_conditions:
                continue

            matched_fk_ids = (
                db.query(ref_model.id)
                .filter(ref_model.is_deleted == False)
                .filter(or_(*ref_conditions))
            )
            conditions.append(getattr(model, fk_key).in_(matched_fk_ids))

        if conditions:
            query = query.filter(or_(*conditions))
        return query

    def _helper_apply_sort(query, model, sort_by: str | None, sort_dir: str | None):
        """
        作用：按前端传入字段与方向对查询结果排序。
        输入参数：
        - query: SQLAlchemy Query 对象。
        - model: SQLAlchemy 模型类。
        - sort_by: 排序字段，支持逗号分隔。
        - sort_dir: 排序方向，支持逗号分隔。
        输出参数：
        - Query: 追加排序后的查询对象。
        """
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

    meta = get_table(table)
    model = meta["model"]

    params = {k: v for k, v in request.query_params.items() if k not in RESERVED_PARAMS}
    query = db.query(model)
    query = _helper_apply_filters(query, model, params, only_deleted)
    query = _helper_apply_search(query, model, q)
    total = query.count()
    query = _helper_apply_sort(query, model, sort_by, sort_dir)
    items = query.offset(offset).limit(limit).all()

    return ListResponse(
        data=jsonable_encoder(items),
        meta=Meta(offset=offset, limit=limit, total=total),
    )


@router.get("/{table}/{item_id}", response_model=OkResponse)
def get_item(
    table: str,
    item_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    """
    作用：按主键查询单条未删除数据。
    输入参数：
    - table: 业务表名。
    - item_id: 数据主键 ID。
    - db: 数据库会话。
    - current_admin: 当前登录管理员（鉴权依赖）。
    输出参数：
    - OkResponse: 单条数据对象。
    """
    meta = get_table(table)
    model = meta["model"]
    item = db.query(model).filter(model.id == item_id, model.is_deleted == False).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return OkResponse(data=jsonable_encoder(item))


@router.post("/{table}/create", response_model=OkResponse)
def create_item(
    table: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    """
    作用：通用创建接口，按表配置进行入参校验并写入数据库。
    输入参数：
    - table: 业务表名。
    - payload: 前端提交的数据字典。
    - db: 数据库会话。
    - current_admin: 当前登录管理员（用于审计字段）。
    输出参数：
    - OkResponse: 新建后的数据对象。
    """
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


@router.put("/{table}/{item_id}", response_model=OkResponse)
def update_item(
    table: str,
    item_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    """
    作用：通用更新接口，支持普通更新与软删除恢复。
    输入参数：
    - table: 业务表名。
    - item_id: 数据主键 ID。
    - payload: 前端提交的更新字段字典。
    - db: 数据库会话。
    - current_admin: 当前登录管理员（用于审计字段）。
    输出参数：
    - OkResponse: 更新后的数据对象。
    """
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


@router.delete("/{table}/{item_id}", response_model=OkResponse)
def delete_item(
    table: str,
    item_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    """
    作用：通用软删除接口，将记录标记为 is_deleted=True。
    输入参数：
    - table: 业务表名。
    - item_id: 数据主键 ID。
    - db: 数据库会话。
    - current_admin: 当前登录管理员（用于审计字段）。
    输出参数：
    - OkResponse: 删除结果对象（返回被删除记录内容）。
    """
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


@router.get("/student/{student_id}/scores", response_model=ListResponse)
def get_student_scores(
    student_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    """
    作用：查询指定学生的成绩列表，关联返回课程名称与课程编码。
    输入参数：
    - student_id: 学生 ID。
    - offset: 分页起始偏移。
    - limit: 分页条数。
    - db: 数据库会话。
    - current_admin: 当前登录管理员（鉴权依赖）。
    输出参数：
    - ListResponse: 学生成绩列表与分页元信息。
    """
    query = (
        db.query(Score, Course)
        .join(Course, Score.course_id == Course.id)
        .filter(Score.student_id == student_id, Score.is_deleted == False)
    )
    total = query.count()
    items = query.offset(offset).limit(limit).all()
    data = [
        {
            "id": score.id,
            "student_id": score.student_id,
            "course_id": score.course_id,
            "course_name": course.course_name,
            "course_code": course.course_code,
            "course_class_id": score.course_class_id,
            "term": score.term,
            "score_value": score.score_value,
            "score_level": score.score_level,
        }
        for score, course in items
    ]
    return ListResponse(
        data=jsonable_encoder(data),
        meta=Meta(offset=offset, limit=limit, total=total),
    )
