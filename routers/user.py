import uuid
from fastapi import Depends, HTTPException
import supabase
from models import DeleteUserRequest
from fastapi import APIRouter
from utils.init import get_db 
router = APIRouter()


@router.get("/user_chats/{user_id}")
async def get_user_chats(user_id: str,db=Depends(get_db)):
    try:
        user_id = str(uuid.UUID(user_id))
        async with db.acquire() as db:
            chats = await db.fetch("""
                SELECT id, created_at, question
                FROM conversations
                WHERE user_id = $1 AND is_root = true
                ORDER BY created_at DESC
            """, user_id)
        return {"user_id": user_id, "chats": chats}
    except ValueError:
        raise HTTPException(status_code=400, detail="無効なUUID形式のuser_idです。")







@router.post("/api/delete_user")
async def delete_user(req: DeleteUserRequest):
    try:
        supabase.auth.admin.delete_user(req.user_id)
        return {"status": "success", "message": "User deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")

