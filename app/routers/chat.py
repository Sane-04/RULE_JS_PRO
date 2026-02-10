from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_current_admin, get_db
from app.schemas.chat import ChatIntentRequest, ChatParseData, ChatParseResponse
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
