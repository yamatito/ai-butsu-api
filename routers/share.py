import uuid
from fastapi import Depends, HTTPException
import supabase
from fastapi import APIRouter

from utils.init import generate_slug, get_db
from models import ChatRequest, LikeRequest, ShareWordRequest
router = APIRouter()



# ===================================================
# ✨ 共有機能
# ===================================================

# - /share_word: AIメッセージを共有する
@router.post("/share_word")
async def share_word(request: ShareWordRequest,db=Depends(get_db)):
    user_id = str(uuid.UUID(request.user_id))
    chat_id = str(uuid.UUID(request.chat_id))
    content = request.content.strip()
    comment = request.comment.strip() if request.comment else None

    if not content:
        raise HTTPException(status_code=400, detail="共有内容が空です")

    slug = generate_slug()

    async with db.acquire() as db:
        # すでに同じ内容が共有済みか確認（ユーザー＋チャット＋内容で重複チェック）
        existing = await db.fetchval("""
            SELECT 1 FROM shared_words
            WHERE user_id = $1 AND chat_id = $2 AND content = $3
        """, user_id, chat_id, content)

        if existing:
            raise HTTPException(status_code=409, detail="すでに共有されています")

        # 共有データを保存（comment カラム含むように変更）
        await db.execute("""
            INSERT INTO shared_words (user_id, chat_id, content, comment, share_slug, created_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
        """, user_id, chat_id, content, comment, slug)

    return {"slug": slug, "url": f"/words/{slug}"}

# - /words/{slug}: スラッグで1つ取得
@router.get("/words/{slug}")
async def get_shared_word(slug: str,db=Depends(get_db)):
    async with db.acquire() as db:
        row = await db.fetchrow("""
            SELECT content, user_id, created_at FROM shared_words
            WHERE share_slug = $1
        """, slug)
    if not row:
        raise HTTPException(status_code=404, detail="共有された言葉が見つかりません")
    return {"content": row["content"], "user_id": row["user_id"], "created_at": row["created_at"]}


# 🔽 /shared_words/all（コメント・いいね数付き）
@router.get("/shared_words/all")
async def get_all_shared_words(db=Depends(get_db)):
    async with db.acquire() as db:
        rows = await db.fetch("""
            SELECT s.id, s.content, s.share_slug, s.created_at, s.comment,
                COUNT(f.id) AS like_count
            FROM shared_words s
            LEFT JOIN favorites f ON s.id = f.shared_id
            GROUP BY s.id
            ORDER BY s.created_at DESC
            LIMIT 100
        """)
    return [dict(row) for row in rows]

# 🔽 /shared_words/user/{user_id}（コメント・いいね数付き）
@router.get("/shared_words/user/{user_id}")
async def get_user_shared_words(user_id: str,db=Depends(get_db)):
    async with db.acquire() as db:
        rows = await db.fetch("""
            SELECT s.id, s.content, s.share_slug, s.created_at, s.comment,
                COUNT(f.id) AS like_count
            FROM shared_words s
            LEFT JOIN favorites f ON s.id = f.shared_id
            WHERE s.user_id = $1
            GROUP BY s.id
            ORDER BY s.created_at DESC
        """, user_id)
    return [dict(row) for row in rows]







# 🔽 いいねのトグル（登録 or 削除）
@router.post("/shared_words/{slug}/like")
async def toggle_like(slug: str, request: LikeRequest,db=Depends(get_db)):
    user_id = str(uuid.UUID(request.user_id))

    async with db.acquire() as db:
        shared_word = await db.fetchrow("""
            SELECT id FROM shared_words WHERE share_slug = $1
        """, slug)
        if not shared_word:
            raise HTTPException(status_code=404, detail="共有された言葉が見つかりません")

        shared_id = shared_word["id"]

        exists = await db.fetchval("""
            SELECT 1 FROM favorites WHERE user_id = $1 AND shared_id = $2
        """, user_id, shared_id)

        if exists:
            await db.execute("""
                DELETE FROM favorites WHERE user_id = $1 AND shared_id = $2
            """, user_id, shared_id)
            return {"liked": False}
        else:
            await db.execute("""
                INSERT INTO favorites (user_id, shared_id, created_at)
                VALUES ($1, $2, NOW())
            """, user_id, shared_id)
            return {"liked": True}