from app.models.admin import Admin
from app.models.class_model import ClassModel
from app.models.college import College
from app.models.course import Course
from app.models.major import Major
from app.models.mixins import AuditMixin
from app.models.student import Student
from app.models.teacher import Teacher

__all__ = [
    "Admin",
    "AuditMixin",
    "ClassModel",
    "College",
    "Course",
    "Major",
    "Student",
    "Teacher",
]
