from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import verify_password, create_access_token
from app.models.admin import Admin


def authenticate_admin(db: Session, username: str, password: str) -> str | None:
    admin = db.query(Admin).filter(Admin.username == username, Admin.is_deleted == False).first()
    if not admin:
        return None
    if not verify_password(password, admin.password_hash):
        return None

    admin.last_login_at = func.now()
    db.add(admin)
    db.commit()

    return create_access_token(subject=str(admin.id))
