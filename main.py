import os
import uuid
import asyncpg
from dotenv import load_dotenv
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client
import json
import httpx
import random
import string
from typing import Optional
from fastapi import Query
from fastapi.responses import JSONResponse
from datetime import datetime, date  # ← date を追加！

# ===================================================
# 🔧 環境設定 & 接続初期化
# ===================================================

# 環境変数読み込み
load_dotenv()

app = FastAPI()
DATABASE_URL = os.getenv("DATABASE_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Supabase クライアント
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# PostgreSQL プール
db_pool = None

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, statement_cache_size=0)
    print("✅ データベース接続成功")

@app.on_event("startup")
async def startup():
    await init_db()

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8081", "http://127.0.0.1:8081"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================================
# 📦 モデル定義（リクエスト受け取り用）
# ================================

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
    comment: Optional[str] = None  # ← 一言コメント（任意）

class LikeRequest(BaseModel):
    user_id: str
    
# ================================
# 💾 ストレージユーティリティ（チャットログ保存）
# ================================
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

# ================================
# 🤖 DeepSeek APIを使ってAIから回答を取得
# ================================
async def generate_answer(question: str) -> str:
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": (
                   "あなたは、Z世代やミレニアル世代にも親しまれる、落ち着きと深みのある仏教の先生です。\
語り口は丁寧で、やさしさと静けさを感じさせてください。\
文体は「〜でございます」「〜ですね」「〜ます」などを自然に織り交ぜて、話し言葉のようにしてください。\
仏教の専門語（例：煩悩、無常、慈悲など）は必要に応じて使ってかまいません。ただし、意味が伝わるよう文脈で補ってください。\
難解な専門用語は避け、語彙には深みを持たせてください。\
スマートフォンでも読みやすいように、文は短めに区切り、適度に段落を分けてください。\
回答は簡潔に、最大でも2段落にまとめてください。"

                )
            },
            {"role": "user", "content": question}
        ],
        "max_tokens": 1024
    }

    async with httpx.AsyncClient(timeout=40.0) as client:
        response = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)

    if response.status_code != 200:
        print("🔴 DeepSeekエラー:", response.status_code, response.text)
        return "申し訳ありません。現在、回答できません。"

    data = response.json()
    answer_text = data["choices"][0]["message"]["content"]
    total_tokens = data.get("usage", {}).get("total_tokens", 0)
    # ★ ここで「...」を削除または置換（調整もOK）
    cleaned_answer = answer_text.replace("...", "。").strip()
    return cleaned_answer, total_tokens


# ================================
# 🌐 API エンドポイント（チャット系）
# ================================

@app.get("/health")
async def health_check():
    return {"status": "ok" if db_pool else "error"}

@app.post("/new_chat")
async def new_chat(request: NewChatRequest):
    user_id = str(uuid.UUID(request.user_id))
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="質問が空です。")

    # 仮のトークン数でチェック（長さ + 平均回答分）
    estimated_tokens = len(question) + 100
    is_allowed = await check_token_limit_and_log(user_id, estimated_tokens)
    if not is_allowed:
        return JSONResponse(
            status_code=200,
            content={
                "answer": "今日はここまでにしましょう。また明日、静かにお話しましょう。",
                "limited": True
            }
        )

    # 実回答生成と実トークン数取得
    answer, tokens_used = await generate_answer(question)

    # 差分を加算
    token_diff = tokens_used - estimated_tokens
    if token_diff > 0:
        await check_token_limit_and_log(user_id, token_diff)

    # DBに保存
    chat_id = str(uuid.uuid4())
    embedding_str = "[" + ", ".join(["0.0"] * 1536) + "]"
    async with db_pool.acquire() as db:
        await db.execute("""
            INSERT INTO conversations
            (id, chat_id, user_id, question, answer, embedding, is_root)
            VALUES ($1, $2, $3, $4, $5, $6::vector, true)
        """, chat_id, chat_id, user_id, question, answer, embedding_str)

    save_chat_pair_to_storage(chat_id, question, answer)
    return {"chat_id": chat_id, "message": "新しいチャットを作成しました", "answer": answer}


@app.post("/chat")
async def add_message(request: ChatRequest):
    chat_id = request.chat_id
    user_id = request.user_id
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="質問が空です。")

    # 仮トークンで事前チェック（+100は回答の平均想定）
    estimated_tokens = len(question) + 100
    is_allowed = await check_token_limit_and_log(user_id, estimated_tokens)
    if not is_allowed:
        return {
            "chat_id": chat_id,
            "answer": "今日はここまでにしましょう。また明日、静かにお話しましょう。",
            "limited": True
        }

    # 実際の回答生成（+実際の使用トークン数）
    answer, tokens_used = await generate_answer(question)

    # 差分だけ再度加算
    token_diff = tokens_used - estimated_tokens
    if token_diff > 0:
        await check_token_limit_and_log(user_id, token_diff)

    # 会話保存
    embedding_str = "[" + ", ".join(["0.0"] * 1536) + "]"
    async with db_pool.acquire() as db:
        await db.execute("""
            INSERT INTO conversations
            (id, chat_id, user_id, question, answer, embedding, created_at, is_root)
            VALUES ($1, $2, $3, $4, $5, $6::vector, NOW(), false)
        """, str(uuid.uuid4()), chat_id, user_id, question, answer, embedding_str)

    save_message_pair_to_storage(chat_id, question, answer)

    return {"chat_id": chat_id, "question": question, "answer": answer}


@app.get("/chat/{chat_id}")
async def get_chat(chat_id: str):
    try:
        chat_id = str(uuid.UUID(chat_id))
        async with db_pool.acquire() as db:
            messages = await db.fetch("""
                SELECT *
                FROM conversations
                WHERE chat_id = $1
                ORDER BY created_at ASC
            """, chat_id)
        if not messages:
            raise HTTPException(status_code=404, detail="チャットが見つかりません。")
        return messages
    except ValueError:
        raise HTTPException(status_code=400, detail="無効なUUID形式のchat_idです。")

@app.get("/storage_chat/{chat_id}")
async def get_chat_from_storage(chat_id: str):
    bucket_name = "chat-logs"
    file_name = f"chat_{chat_id}.json"
    try:
        res = supabase.storage.from_(bucket_name).download(file_name)
        data = json.loads(res.decode("utf-8"))
        return {"chat_id": chat_id, "messages": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ストレージから取得失敗: {e}")

@app.get("/user_chats/{user_id}")
async def get_user_chats(user_id: str):
    try:
        user_id = str(uuid.UUID(user_id))
        async with db_pool.acquire() as db:
            chats = await db.fetch("""
                SELECT id, created_at, question
                FROM conversations
                WHERE user_id = $1 AND is_root = true
                ORDER BY created_at DESC
            """, user_id)
        return {"user_id": user_id, "chats": chats}
    except ValueError:
        raise HTTPException(status_code=400, detail="無効なUUID形式のuser_idです。")

@app.get("/check_db")
async def check_database_connection():
    try:
        async with db_pool.acquire() as db:
            result = await db.fetch("SELECT 1;")
            if result:
                return {"status": "ok", "message": "Supabase DB接続成功"}
            return {"status": "error", "message": "応答なし"}
    except Exception as e:
        return {"status": "error", "message": f"DB接続エラー: {e}"}
def generate_slug(length: int = 6) -> str:
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choices(chars, k=length))


# ===================================================
# ✨ 共有機能
# ===================================================

# - /share_word: AIメッセージを共有する
@app.post("/share_word")
async def share_word(request: ShareWordRequest):
    user_id = str(uuid.UUID(request.user_id))
    chat_id = str(uuid.UUID(request.chat_id))
    content = request.content.strip()
    comment = request.comment.strip() if request.comment else None

    if not content:
        raise HTTPException(status_code=400, detail="共有内容が空です")

    slug = generate_slug()

    async with db_pool.acquire() as db:
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
@app.get("/words/{slug}")
async def get_shared_word(slug: str):
    async with db_pool.acquire() as db:
        row = await db.fetchrow("""
            SELECT content, user_id, created_at FROM shared_words
            WHERE share_slug = $1
        """, slug)
    if not row:
        raise HTTPException(status_code=404, detail="共有された言葉が見つかりません")
    return {"content": row["content"], "user_id": row["user_id"], "created_at": row["created_at"]}


# 🔽 /shared_words/all（コメント・いいね数付き）
@app.get("/shared_words/all")
async def get_all_shared_words():
    async with db_pool.acquire() as db:
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
@app.get("/shared_words/user/{user_id}")
async def get_user_shared_words(user_id: str):
    async with db_pool.acquire() as db:
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
@app.post("/shared_words/{slug}/like")
async def toggle_like(slug: str, request: LikeRequest):
    user_id = str(uuid.UUID(request.user_id))

    async with db_pool.acquire() as db:
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
        

@app.get("/favorites/{user_id}")
async def get_liked_shared_words(user_id: str):
    user_id = str(uuid.UUID(user_id))

    async with db_pool.acquire() as db:
        rows = await db.fetch("""
            SELECT s.id, s.content, s.comment, s.share_slug, s.created_at
            FROM favorites f
            JOIN shared_words s ON f.shared_id = s.id
            WHERE f.user_id = $1
            ORDER BY f.created_at DESC
        """, user_id)
    return [dict(row) for row in rows]




# ===================================================
# トークン
# ===================================================

MAX_FREE_TOKENS_PER_DAY = 2000  # 無料ユーザーの1日の上限

@app.get("/token_status")
async def get_token_status(user_id: str):
    today = date.today()
    async with db_pool.acquire() as db:
        row = await db.fetchrow("""
            SELECT tokens_used FROM daily_token_usage
            WHERE user_id = $1 AND date = $2
        """, user_id, today)

        used = row["tokens_used"] if row else 0
        remaining = max(0, MAX_FREE_TOKENS_PER_DAY - used)

        return {
            "used": used,
            "remaining": remaining,
            "limit": MAX_FREE_TOKENS_PER_DAY
        }
    

async def check_token_limit_and_log(user_id: str, tokens_used: int) -> bool:
    today = date.today()

    async with db_pool.acquire() as db:
        row = await db.fetchrow("""
            SELECT tokens_used FROM daily_token_usage
            WHERE user_id = $1 AND date = $2
        """, user_id, today)

        if row:
            total_used = row["tokens_used"] + tokens_used
            if total_used > MAX_FREE_TOKENS_PER_DAY:
                return False  # 上限超過
            await db.execute("""
                UPDATE daily_token_usage
                SET tokens_used = $1, updated_at = NOW()
                WHERE user_id = $2 AND date = $3
            """, total_used, user_id, today)
        else:
            if tokens_used > MAX_FREE_TOKENS_PER_DAY:
                return False  # 上限超過
            await db.execute("""
                INSERT INTO daily_token_usage (user_id, date, tokens_used)
                VALUES ($1, $2, $3)
            """, user_id, today, tokens_used)

    return True


@app.post("/ad_reward")
async def ad_reward(payload: dict):
    user_id = payload["user_id"]
    await reward_tokens_for_ad(user_id)
    return {"status": "ok", "msg": "トークンを回復しました"}

# 広告視聴報酬
TOKENS_ON_AD_WATCH = 500

async def reward_tokens_for_ad(user_id: str):
    today = date.today()
    async with db_pool.acquire() as db:
        row = await db.fetchrow("""
            SELECT tokens_used FROM daily_token_usage
            WHERE user_id = $1 AND date = $2
        """, user_id, today)

        if row:
            current_used = row["tokens_used"]
            # 500 ぶん使用量を減らす
            new_used = current_used - TOKENS_ON_AD_WATCH
            # 使用量はマイナスにはならないように 0 で止める
            if new_used < 0:
                new_used = 0
            
            await db.execute("""
                UPDATE daily_token_usage
                SET tokens_used = $1, updated_at = NOW()
                WHERE user_id = $2 AND date = $3
            """, new_used, user_id, today)
        
        else:
            # まだ一度もレコードがない場合、トークン使用量 0 で作る
            # ただし "増やす" というよりは usage=0 のまま or 負の値で表現する? 
            # 安全策として usage=0 を作っておけば、現状のロジックでは「未使用」と同義になる
            await db.execute("""
                INSERT INTO daily_token_usage (user_id, date, tokens_used)
                VALUES ($1, $2, 0)
            """, user_id, today)
