
import uuid
from fastapi import APIRouter, Depends
from utils.init import get_db
router = APIRouter()




@router.get("/favorites/{user_id}")
async def get_liked_shared_words(user_id: str,db=Depends(get_db)):
    user_id = str(uuid.UUID(user_id))

    async with db.acquire() as db:
        rows = await db.fetch("""
            SELECT s.id, s.content, s.comment, s.share_slug, s.created_at
            FROM favorites f
            JOIN shared_words s ON f.shared_id = s.id
            WHERE f.user_id = $1
            ORDER BY f.created_at DESC
        """, user_id)
    return [dict(row) for row in rows]

