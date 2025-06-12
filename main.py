import os
import asyncpg
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager  # ← これを追加！
from routers import chat, user, share, favorites, token, health


# ===================================================
# 🔧 環境設定 & 接続初期化
# ===================================================
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Supabase クライアント
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 👇 ここにデコレーターを追加
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await asyncpg.create_pool(DATABASE_URL, statement_cache_size=0)
    print("✅ データベース接続成功")

    yield

    await app.state.db_pool.close()
    print("👋 DB接続終了")

# lifespan を渡して FastAPI インスタンス作成
app = FastAPI(lifespan=lifespan)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8081", "http://127.0.0.1:8081"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# ルーター登録
app.include_router(chat.router)
app.include_router(user.router)
app.include_router(share.router)
app.include_router(favorites.router)
app.include_router(token.router)
app.include_router(health.router)
