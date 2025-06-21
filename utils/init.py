
# init.py
from datetime import date, datetime
import json
import random
import string

import os
from asyncpg import Pool
from fastapi import Depends, Request
from supabase import create_client    # ← クライアントを生成
from dotenv import load_dotenv

load_dotenv()
SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)  # ← これが本物の client

async def get_db(request: Request):
    return request.app.state.db_pool

def trim_if_needed(text: str, limit: int = 300) -> str:
    return text if len(text) <= limit else text[:limit].rstrip("、。") + "。"


def empty_embedding_vector(dim: int = 1536) -> str:
    return "[" + ", ".join(["0.0"] * dim) + "]"


def generate_slug(length: int = 6) -> str:
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choices(chars, k=length))




def save_chat_pair_to_storage(chat_id: str, user_message: str, assistant_message: str):
    bucket_name = "chat-logs"
    file_name = f"chat_{chat_id}.json"
    now = datetime.utcnow().isoformat()

    try:
        res = supabase.storage.from_(bucket_name).download(file_name)
        existing_data = json.loads(res.decode("utf-8"))
    except Exception:
        existing_data = []

    existing_data.extend([
        {"role": "user", "message": user_message, "timestamp": now},
        {"role": "assistant", "message": assistant_message, "timestamp": now},
    ])

    try:
        supabase.storage.from_(bucket_name).remove([file_name])
    except:
        pass

    supabase.storage.from_(bucket_name).upload(
        path=file_name,
        file=bytes(json.dumps(existing_data, ensure_ascii=False), encoding="utf-8"),
        file_options={"content-type": "application/json"},
    )

def save_message_pair_to_storage(chat_id: str, user_message: str, assistant_message: str):
    return save_chat_pair_to_storage(chat_id, user_message, assistant_message)




# 毎日初めてアクセスされた時にリセットする
async def reset_daily_if_needed(db, user_id: str):
    today = date.today()
    row = await db.fetchrow("""
        SELECT last_reset_date FROM user_tokens WHERE user_id = $1
    """, user_id)

    if not row:
        # 新規ユーザー（初期値で作成）
        await db.execute("""
            INSERT INTO user_tokens (user_id) VALUES ($1)
        """, user_id)
    elif row["last_reset_date"] != today:
        # 日付が変わってたらリセット
        await db.execute("""
            UPDATE user_tokens
            SET daily_used = 0, daily_rewarded = 0, last_reset_date = $2
            WHERE user_id = $1
        """, user_id, today)

# トークン使用チェック & 消費処理
async def check_token_limit_and_log(user_id: str, tokens_used: int, db_pool: Pool) -> bool:
    async with db_pool.acquire() as db:
        await reset_daily_if_needed(db, user_id)

        row = await db.fetchrow("""
            SELECT tokens_remaining, daily_used FROM user_tokens WHERE user_id = $1
        """, user_id)

        if not row:
            # ✅ ユーザー初回：レコードを自動作成
            await db.execute("""
                INSERT INTO user_tokens (user_id) VALUES ($1)
            """, user_id)
            row = await db.fetchrow("""
                SELECT tokens_remaining, daily_used FROM user_tokens WHERE user_id = $1
            """, user_id)

        remaining = row["tokens_remaining"]
        today_used = row["daily_used"]

        if remaining < tokens_used:
            return False  # 上限超え

        await db.execute("""
            UPDATE user_tokens
            SET
              tokens_remaining = tokens_remaining - $2,
              total_used = total_used + $2,
              daily_used = daily_used + $2
            WHERE user_id = $1
        """, user_id, tokens_used)

        return True


# 報酬付与（広告視聴）
async def reward_tokens_for_ad(user_id: str, reward_amount: int,db=Depends(get_db)):
    async with db.acquire() as db:
        await reset_daily_if_needed(db, user_id)

        await db.execute("""
            UPDATE user_tokens
            SET
              tokens_remaining = tokens_remaining + $2,
              total_rewarded = total_rewarded + $2,
              daily_rewarded = daily_rewarded + $2
            WHERE user_id = $1
        """, user_id, reward_amount)
