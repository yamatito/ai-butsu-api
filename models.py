# ================================
# 📦 モデル定義（リクエスト受け取り用）
# ================================

from typing import Optional
from pydantic import BaseModel


class NewChatRequest(BaseModel):
    user_id: str
    question: str

class ChatRequest(BaseModel):
    chat_id: str
    user_id: str
    question: str

class ShareWordRequest(BaseModel):
    user_id: str
    chat_id: str
    content: str
    comment: Optional[str] = None  

class LikeRequest(BaseModel):
    user_id: str
    
    
class DeleteUserRequest(BaseModel):
    user_id: str   # ← JSON で受け取るキー名