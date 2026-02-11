from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.deps import get_current_admin, get_db
from app.models.chat_history import ChatHistory
from app.schemas.chat import ChatIntentRequest, ChatParseData, ChatParseResponse
from app.schemas.response import ListResponse, Meta
from app.services.chat_graph import execute_chat_workflow

router = APIRouter()


@router.post("", response_model=ChatParseResponse)
def chat_entry(
    payload: ChatIntentRequest,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    data = execute_chat_workflow(db=db, admin_id=current_admin.id, payload=payload)
    return ChatParseResponse(data=ChatParseData(**data))


@router.get("/sessions", response_model=ListResponse)
def list_chat_sessions(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    base_filters = (
        ChatHistory.admin_id == current_admin.id,
        ChatHistory.is_deleted.is_(False),
        ChatHistory.message_role.in_(("user", "assistant")),
    )
    total = db.query(func.count(func.distinct(ChatHistory.session_id))).filter(*base_filters).scalar() or 0
    session_rows = (
        db.query(
            ChatHistory.session_id.label("session_id"),
            func.max(ChatHistory.created_at).label("last_active_at"),
        )
        .filter(*base_filters)
        .group_by(ChatHistory.session_id)
        .order_by(func.max(ChatHistory.created_at).desc(), ChatHistory.session_id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    session_ids = [row.session_id for row in session_rows]
    preview_map: dict[str, str] = {}
    if session_ids:
        first_user_subquery = (
            db.query(
                ChatHistory.session_id.label("session_id"),
                func.min(ChatHistory.id).label("first_user_id"),
            )
            .filter(
                ChatHistory.admin_id == current_admin.id,
                ChatHistory.is_deleted.is_(False),
                ChatHistory.message_role == "user",
                ChatHistory.session_id.in_(session_ids),
            )
            .group_by(ChatHistory.session_id)
            .subquery()
        )
        preview_rows = (
            db.query(ChatHistory.session_id, ChatHistory.message_content)
            .join(first_user_subquery, ChatHistory.id == first_user_subquery.c.first_user_id)
            .all()
        )
        for row in preview_rows:
            raw_text = str(row.message_content or "").strip()
            preview_map[row.session_id] = f"{raw_text[:7]}..." if len(raw_text) > 7 else raw_text

    data = [
        {
            "session_id": row.session_id,
            "preview": preview_map.get(row.session_id, ""),
            "last_active_at": row.last_active_at,
        }
        for row in session_rows
    ]
    return ListResponse(
        data=jsonable_encoder(data),
        meta=Meta(offset=offset, limit=limit, total=total),
    )


@router.get("/sessions/{session_id}/messages", response_model=ListResponse)
def list_chat_session_messages(
    session_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin),
):
    message_query = db.query(ChatHistory).filter(
        ChatHistory.admin_id == current_admin.id,
        ChatHistory.session_id == session_id,
        ChatHistory.is_deleted.is_(False),
        ChatHistory.message_role.in_(("user", "assistant")),
    )
    total = message_query.count()
    rows = (
        message_query.order_by(ChatHistory.created_at.asc(), ChatHistory.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    data = [
        {
            "id": row.id,
            "role": row.message_role,
            "content": row.message_content,
            "created_at": row.created_at,
        }
        for row in rows
    ]
    return ListResponse(
        data=jsonable_encoder(data),
        meta=Meta(offset=offset, limit=limit, total=total),
    )
