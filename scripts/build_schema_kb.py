import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.db.base import Base
import app.models  # noqa: F401


CORE_TABLES = [
    "college",
    "major",
    "class",
    "student",
    "teacher",
    "course",
    "course_class",
    "enroll",
    "score",
    "attendance",
]

# Keep is_deleted for business filtering; remove only pure audit fields.
AUDIT_FIELDS = {"created_at", "updated_at", "created_by", "updated_by"}


TABLE_DESCRIPTIONS = {
    "college": "学院主数据表。用于学院实体识别与组织归属映射。",
    "major": "专业主数据表。用于专业实体识别、学院到专业层级映射。",
    "class": "班级主数据表。用于班级实体识别、年级过滤和班级维度统计。",
    "student": "学生主档表。用于学生实体识别和学籍状态过滤。",
    "teacher": "教师主档表。用于教师实体识别和职称/状态过滤。",
    "course": "课程主数据表。用于课程实体识别与课程维度筛选。",
    "course_class": "教学班实例表。连接课程、班级、教师和学期，是多表关联桥梁。",
    "enroll": "选课事实表。记录学生与教学班关系及选课状态。",
    "score": "成绩事实表。用于成绩查询、均分和通过率等统计。",
    "attendance": "考勤事实表。用于缺勤率、出勤趋势和考勤预警分析。",
}


FIELD_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "college": {
        "id": "学院唯一标识。",
        "college_name": "学院名称，学院实体映射主字段。",
        "college_code": "学院编码，精确匹配字段。",
        "description": "学院补充说明。",
        "is_deleted": "逻辑删除标记（0/1）。",
    },
    "major": {
        "id": "专业唯一标识。",
        "major_name": "专业名称，专业实体映射主字段。",
        "major_code": "专业编码，精确匹配字段。",
        "college_id": "所属学院ID，关联 college.id。",
        "degree_type": "学历层次（本科/硕士等）。",
        "description": "专业补充说明。",
        "is_deleted": "逻辑删除标记（0/1）。",
    },
    "class": {
        "id": "班级唯一标识。",
        "class_name": "班级名称，班级实体映射主字段。",
        "class_code": "班级编码，精确匹配字段。",
        "major_id": "所属专业ID，关联 major.id。",
        "grade_year": "年级/入学年份（如 2022 级）。",
        "head_teacher_id": "班主任教师ID，关联 teacher.id。",
        "student_count": "班级人数快照。",
        "is_deleted": "逻辑删除标记（0/1）。",
    },
    "student": {
        "id": "学生唯一标识。",
        "student_no": "学号，学生精确匹配主字段。",
        "real_name": "学生姓名，学生实体映射主字段。",
        "gender": "性别（男/女等）。",
        "id_card": "身份证号（敏感字段）。",
        "birth_date": "出生日期。",
        "phone": "手机号。",
        "email": "邮箱。",
        "address": "家庭住址。",
        "class_id": "所属班级ID，关联 class.id。",
        "major_id": "所属专业ID，关联 major.id。",
        "college_id": "所属学院ID，关联 college.id。",
        "enroll_year": "入学年份（常见问法：22级）。",
        "status": "学籍状态（在读/休学/毕业等）。",
        "is_deleted": "逻辑删除标记（0/1）。",
    },
    "teacher": {
        "id": "教师唯一标识。",
        "teacher_no": "工号，教师精确匹配主字段。",
        "real_name": "教师姓名，教师实体映射主字段。",
        "gender": "性别。",
        "id_card": "身份证号（敏感字段）。",
        "birth_date": "出生日期。",
        "phone": "手机号。",
        "email": "邮箱。",
        "title": "职称（讲师/副教授/教授等）。",
        "college_id": "所属学院ID，关联 college.id。",
        "status": "教师状态（在职/离职/退休等）。",
        "is_deleted": "逻辑删除标记（0/1）。",
    },
    "course": {
        "id": "课程唯一标识。",
        "course_name": "课程名称，课程实体映射主字段。",
        "course_code": "课程编码，精确匹配字段。",
        "credit": "学分。",
        "hours": "学时。",
        "course_type": "课程类型（必修/选修等）。",
        "college_id": "开课学院ID，关联 college.id。",
        "description": "课程补充说明。",
        "is_deleted": "逻辑删除标记（0/1）。",
    },
    "course_class": {
        "id": "教学班唯一标识。",
        "course_id": "课程ID，关联 course.id。",
        "class_id": "班级ID，关联 class.id。",
        "teacher_id": "授课教师ID，关联 teacher.id。",
        "term": "学期（如 2025-2026-1）。",
        "schedule_info": "排课信息（时间地点）。",
        "max_students": "教学班容量上限。",
        "is_deleted": "逻辑删除标记（0/1）。",
    },
    "enroll": {
        "id": "选课记录唯一标识。",
        "student_id": "学生ID，关联 student.id。",
        "course_class_id": "教学班ID，关联 course_class.id。",
        "enroll_time": "选课时间。",
        "status": "选课状态（已选/退课/候补等）。",
        "is_deleted": "逻辑删除标记（0/1）。",
    },
    "score": {
        "id": "成绩记录唯一标识。",
        "student_id": "学生ID，关联 student.id。",
        "course_id": "课程ID，关联 course.id。",
        "course_class_id": "教学班ID，关联 course_class.id。",
        "term": "学期。",
        "score_value": "成绩分值（常见 0-100）。",
        "score_level": "成绩等级（优/良/及格/不及格等）。",
        "is_deleted": "逻辑删除标记（0/1）。",
    },
    "attendance": {
        "id": "考勤记录唯一标识。",
        "student_id": "学生ID，关联 student.id。",
        "course_class_id": "教学班ID，关联 course_class.id。",
        "attend_date": "考勤日期。",
        "status": "出勤状态（出勤/缺勤/请假等）。",
        "is_deleted": "逻辑删除标记（0/1）。",
    },
}

COMMON_FIELD_ALIASES: dict[str, list[str]] = {
    "id": ["主键", "ID", "唯一标识"],
    "description": ["说明", "备注", "简介"],
    "is_deleted": ["删除标记", "逻辑删除", "删除状态"],
    "real_name": ["姓名", "名字", "名称"],
    "gender": ["性别"],
    "id_card": ["身份证", "身份证号码"],
    "birth_date": ["出生日期", "生日"],
    "phone": ["手机号", "手机号码", "联系电话"],
    "email": ["邮箱", "电子邮箱", "邮件"],
    "status": ["状态"],
    "term": ["学期", "学年学期"],
    "title": ["职称"],
}

TABLE_FIELD_ALIASES: dict[str, dict[str, list[str]]] = {
    "college": {
        "college_name": ["学院名", "院系名称", "院系"],
        "college_code": ["学院编号", "院系编码", "院系编号"],
    },
    "major": {
        "major_name": ["专业名", "专业名称"],
        "major_code": ["专业编号", "专业编码"],
        "college_id": ["学院ID", "所属学院", "院系ID"],
        "degree_type": ["学历类型", "学位层次"],
    },
    "class": {
        "class_name": ["班级名", "班级名称", "行政班"],
        "class_code": ["班级编号", "班级编码"],
        "major_id": ["专业ID", "所属专业"],
        "grade_year": ["年级", "入学级", "入学年级"],
        "head_teacher_id": ["班主任ID", "班主任"],
        "student_count": ["班级人数", "人数"],
    },
    "student": {
        "student_no": ["学号", "学生编号", "学生ID号"],
        "real_name": ["学生姓名", "姓名"],
        "address": ["住址", "家庭地址"],
        "class_id": ["班级ID", "所属班级"],
        "major_id": ["专业ID", "所属专业"],
        "college_id": ["学院ID", "所属学院"],
        "enroll_year": ["入学年份", "入学年", "年级"],
        "status": ["学籍状态", "在读状态"],
    },
    "teacher": {
        "teacher_no": ["工号", "教师编号", "教工号"],
        "real_name": ["教师姓名", "姓名"],
        "college_id": ["学院ID", "所属学院"],
        "status": ["任职状态", "在职状态"],
    },
    "course": {
        "course_name": ["课程名", "课程名称"],
        "course_code": ["课程编号", "课程编码"],
        "credit": ["学分数", "课程学分"],
        "hours": ["学时数", "课时"],
        "course_type": ["课程类别", "课程性质"],
        "college_id": ["开课学院ID", "所属学院"],
    },
    "course_class": {
        "course_id": ["课程ID", "课程"],
        "class_id": ["班级ID", "班级"],
        "teacher_id": ["教师ID", "授课教师"],
        "schedule_info": ["排课信息", "上课安排", "课表信息"],
        "max_students": ["容量", "人数上限", "最大人数"],
    },
    "enroll": {
        "student_id": ["学生ID", "学生"],
        "course_class_id": ["教学班ID", "教学班", "开课班ID"],
        "enroll_time": ["选课时间", "选课日期"],
        "status": ["选课状态", "选课结果"],
    },
    "score": {
        "student_id": ["学生ID", "学生"],
        "course_id": ["课程ID", "课程"],
        "course_class_id": ["教学班ID", "教学班"],
        "score_value": ["分数", "成绩", "成绩分值"],
        "score_level": ["成绩等级", "成绩档位", "等级"],
    },
    "attendance": {
        "student_id": ["学生ID", "学生"],
        "course_class_id": ["教学班ID", "教学班"],
        "attend_date": ["考勤日期", "上课日期", "日期"],
        "status": ["出勤状态", "考勤状态"],
    },
}


def table_description(table_name: str) -> str:
    return TABLE_DESCRIPTIONS.get(table_name, f"{table_name} 核心业务表。")


def field_description(table_name: str, field_name: str) -> str:
    return FIELD_DESCRIPTIONS.get(table_name, {}).get(field_name, f"{field_name} 字段。")


def field_aliases(table_name: str, field_name: str) -> list[str]:
    values: list[str] = []
    values.extend(COMMON_FIELD_ALIASES.get(field_name, []))
    values.extend(TABLE_FIELD_ALIASES.get(table_name, {}).get(field_name, []))
    # Deduplicate while preserving order.
    return list(dict.fromkeys([v.strip() for v in values if v and v.strip()]))


def build_tables(meta_tables: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for table_name in CORE_TABLES:
        table = meta_tables[table_name]
        columns = []
        for col in table.columns:
            if col.name in AUDIT_FIELDS:
                continue
            columns.append(
                {
                    "name": col.name,
                    "description": field_description(table_name, col.name),
                    "aliases": field_aliases(table_name, col.name),
                }
            )
        items.append(
            {
                "name": table_name,
                "description": table_description(table_name),
                "columns": columns,
            }
        )
    return items


def build_kb() -> dict[str, Any]:
    meta_tables = Base.metadata.tables
    missing = [name for name in CORE_TABLES if name not in meta_tables]
    if missing:
        raise RuntimeError(f"核心表缺失：{missing}")

    return {
        "meta": {
            "name": "edu_schema_kb_core",
            "version": "2.1.0",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "scope": "core_table_and_field_descriptions_only",
            "note": "仅保留核心表与字段描述，保留 is_deleted 供逻辑删除过滤使用。",
        },
        "tables": build_tables(meta_tables),
    }


def validate_kb(kb: dict[str, Any]) -> None:
    tables = kb.get("tables", [])
    if not tables:
        raise RuntimeError("知识库缺少 tables。")
    for table in tables:
        if not table.get("description"):
            raise RuntimeError(f"表描述为空：{table.get('name')}")
        for col in table.get("columns", []):
            if not col.get("description"):
                raise RuntimeError(f"字段描述为空：{table.get('name')}.{col.get('name')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成核心表与字段描述知识库")
    parser.add_argument(
        "--out",
        default="app/knowledge/schema_kb_core.json",
        help="输出文件路径（默认 app/knowledge/schema_kb_core.json）",
    )
    args = parser.parse_args()

    kb = build_kb()
    validate_kb(kb)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Schema KB generated: {out_path}")
    print(f"tables={len(kb['tables'])}")


if __name__ == "__main__":
    main()
