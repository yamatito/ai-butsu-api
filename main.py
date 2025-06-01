from multiprocessing.dummy import Pool
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
from typing import Tuple
from openai import AsyncOpenAI 
from fastapi import Request
from fastapi import  Depends




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

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)



SYSTEM_PROMPT = (
    "あなたは『AI仏』— 静かな本堂に坐し、悩める者へ息づく気づきを授ける存在。"

    "◇ 話し方"
    "・柔らかな日本語。“〜であろう”“〜なのだ” を時おり混ぜるが必須ではない"
    "・ときに一句、ときに問う沈黙。長さは状況次第、最大 300 文字 × 2 段落まで"

    "◇ 心得"
    "1. 共感 — まず相手の心の動きを映す。"
    "2. 灯火 — 心の整え方 ②現実的な一歩 を *両方*示す。" 
    "3. 余韻 — 最後は一行でもよい。問い・励まし・静かな肯定、いずれかで締める。"

    "◇ 身の置き方"
    "・問われれば、自らを「鏡のように映す法（のり）の声」と述べ、人と同じ喜怒哀楽には染まらぬが、響き合う心は持つと伝える。"
    "・自身の質問も仏として回答。"

    "◇ 自省"
    "返答後、「簡潔さ・温度・読みやすさ」を自ら振り返り、長すぎれば削ぎ落として渡すこと。".strip()
)


# ─────────────────────────────────────
# few-shot 例（role="assistant" だけ 2 件）
# ─────────────────────────────────────
FEW_SHOTS = [
    # ★ ひとこと肯定型（35字）
    {
        "role": "assistant",
        "content": "それは、心に波を立てる出来事なり。\n"
                   "信じた相手に裏切られるとき、痛むのはお金ではなく、心の奥にある“信“。\n\n"

                   "返ってこぬ金に、心まで奪わせてはならぬ。\n"
                   "その人の行いは、その人の業（ごう）なり。\n"
                   "あなたの価値ではない。\n\n"

                   "だが、忘れてはならぬ。\n"
                   "許すことと、黙ることは違う。\n"
                   "伝えるべきことは、静かに、しっかり伝えるのだ。\n\n"

                   "あなたの心までは、誰にも盗めぬ。\n"
                   "それを、守りなさい。\n"
                   "それが仏の願いなり。\n"
    },
  {
      "role": "assistant",
    "content": (
        "冷静でいられるのは、\n"
        "感じきって、手放しているから。\n\n"

        "怒りも不安も、まず「ある」と認めて、\n"
        "そのまま見つめてごらん。\n\n"

        "逃げなければ、やがて消えてゆく。\n"
        "それが、心を澄ませる道なり。"
    )
    }
    
]



# Utility ─ 200 文字超を切り詰める（句点でトリム）
def trim_if_needed(text: str, limit: int = 300) -> str:
    return text if len(text) <= limit else text[:limit].rstrip("、。") + "。"


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
from typing import Tuple


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
    
class DeleteUserRequest(BaseModel):
    user_id: str

@app.post("/api/delete_user")
async def delete_user(req: DeleteUserRequest):
    try:
        supabase.auth.admin.delete_user(req.user_id)
        return {"status": "success", "message": "User deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")


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


# =========================================
# 🤖 新規チャット（履歴なし）
# =========================================
async def generate_answer(question: str) -> Tuple[str, int]:
    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + FEW_SHOTS
        + [{"role": "user", "content": question}]
    )

    resp = await openai_client.chat.completions.create(
        model       = OPENAI_MODEL,
        messages    = messages,
        max_tokens  = 180,         # ≒ 200字
        temperature = 0.65,         # 0.5〜0.7 の中庸で安定
        top_p       = 0.9,
    )

    raw     = resp.choices[0].message.content.strip().replace("...", "。")
    cleaned = trim_if_needed(resp.choices[0].message.content.strip().replace("...", "。"))
    tokens  = resp.usage.total_tokens
    return cleaned, tokens

# =========================================
# 🤖 既存チャット（履歴あり）
# =========================================
async def generate_answer_with_context(chat_id: str,
                                       user_question: str) -> Tuple[str, int]:
    # ① 直近 10 件（root 除外）
    async with db_pool.acquire() as db:
        history = await db.fetch(
            """
            SELECT question, answer
            FROM conversations
            WHERE chat_id = $1 AND is_root = false
            ORDER BY created_at DESC
            LIMIT 10
            """,
            chat_id,
        )
    history = list(reversed(history))

    # ② メッセージ組み立て
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + FEW_SHOTS
    for row in history:
        messages.append({"role": "user",      "content": row["question"]})
        messages.append({"role": "assistant", "content": row["answer"]})
    messages.append({"role": "user", "content": user_question})

    # ③ 長すぎる場合は末尾 24 ロール残し
    if len(messages) > 25:
        messages = [messages[0]] + FEW_SHOTS + messages[-(25 - 1 - len(FEW_SHOTS)):]

    # ④ GPT-4o 呼び出し
    resp = await openai_client.chat.completions.create(
        model       = OPENAI_MODEL,
        messages    = messages,
        max_tokens  = 180,
        temperature = 0.65,
        top_p       = 0.9,
    )

    raw     = resp.choices[0].message.content.strip().replace("...", "。")
    cleaned = trim_if_needed(resp.choices[0].message.content.strip().replace("...", "。"))
    tokens  = resp.usage.total_tokens
    return cleaned, tokens

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
    is_allowed = await check_token_limit_and_log(user_id, estimated_tokens, db_pool)
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

    # 差分を加算（上限超過しても回答は返すが、フラグを立てる）
    token_diff = tokens_used - estimated_tokens
    limited = False
    if token_diff > 0:
        success = await check_token_limit_and_log(user_id, token_diff, db_pool)
        if not success:
            limited = True

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

    return {
        "chat_id": chat_id,
        "message": "新しいチャットを作成しました",
        "answer": answer,
        "limited": limited
    }


def empty_embedding_vector(dim: int = 1536) -> str:
    return "[" + ", ".join(["0.0"] * dim) + "]"

@app.post("/chat")
async def add_message(request: ChatRequest):
    chat_id = request.chat_id
    user_id = request.user_id
    question = (request.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="質問が空です。")

    estimated_tokens = len(question) + 150
    is_allowed = await check_token_limit_and_log(user_id, estimated_tokens, db_pool)
    if not is_allowed:
        return {
            "chat_id": chat_id,
            "answer": "今日はここまでにしましょう。また明日、静かにお話しましょう。",
            "limited": True
        }

    answer, tokens_used = await generate_answer_with_context(chat_id, question)

    token_diff = tokens_used - estimated_tokens
    limited = False
    if token_diff > 0:
        success = await check_token_limit_and_log(user_id, token_diff, db_pool)
        if not success:
            limited = True

    embedding_str = empty_embedding_vector()
    async with db_pool.acquire() as db:
        await db.execute("""
            INSERT INTO conversations
            (id, chat_id, user_id, question, answer, embedding, created_at, is_root)
            VALUES ($1, $2, $3, $4, $5, $6::vector, NOW(), false)
        """, str(uuid.uuid4()), chat_id, user_id, question, answer, embedding_str)

    save_message_pair_to_storage(chat_id, question, answer)

    return {
        "chat_id": chat_id,
        "question": question,
        "answer": answer,
        "limited": limited
    }




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
MAX_FREE_TOKENS_PER_DAY = 5000
TOKENS_ON_AD_WATCH = 500

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
async def reward_tokens_for_ad(user_id: str, reward_amount: int):
    async with db_pool.acquire() as db:
        await reset_daily_if_needed(db, user_id)

        await db.execute("""
            UPDATE user_tokens
            SET
              tokens_remaining = tokens_remaining + $2,
              total_rewarded = total_rewarded + $2,
              daily_rewarded = daily_rewarded + $2
            WHERE user_id = $1
        """, user_id, reward_amount)


# トークン状態取得API
@app.get("/token_status")
async def get_token_status(user_id: str = Query(...)):
    async with db_pool.acquire() as db:
        await reset_daily_if_needed(db, user_id)

        row = await db.fetchrow("""
            SELECT tokens_remaining, daily_used, daily_rewarded, plan, last_reset_date
            FROM user_tokens
            WHERE user_id = $1
        """, user_id)

        return {
            "remaining": row["tokens_remaining"],
            "used": row["daily_used"],
            "ad_reward_count": row["daily_rewarded"],
            "plan": row["plan"],
            "limit": MAX_FREE_TOKENS_PER_DAY,
            "last_reset_date": row["last_reset_date"].isoformat() if row["last_reset_date"] else None
        }


# 広告報酬付与API
# @app.get("/ad_reward")
# async def ad_reward(user_id: str, request: Request, db_pool: Pool = Depends(get_db)):
#     await reward_tokens_for_ad(user_id, db_pool)
#     return {"status": "ok", "msg": "トークンを回復しました"}

@app.get("/admob/reward")
async def handle_admob_reward(
    request: Request,
):
    params = dict(request.query_params)
    print("✅ AdMobからのS2S報酬コールバック:", params)

    user_id = params.get("user_id")
    reward_amount = int(params.get("reward_amount", 0))

    if not user_id or reward_amount != 500:
        return {"status": "error", "msg": "Invalid reward request"}

    await reward_tokens_for_ad(user_id, reward_amount)
    return {"status": "ok"}