# main.py
import os
import asyncpg
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager 
from routers import chat, user, share, favorites, token, health
import asyncio                    
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import httpx                    

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

# --- 🔻 Nightly Reset 用 定数 ---
ADMIN_TOKEN = "super_secret_token"
# 同ホスト内なら http://127.0.0.1:8000 でOK
BASE_URL = "https://web-production-0080.up.railway.app"

# 🔻 追加：毎日0時にトークンをリセット
async def nightly_reset_task():
    while True:
        # 現在時刻（JST）
        now = datetime.now(ZoneInfo("Asia/Tokyo"))
        # 次の0時
        next_midnight = (now  timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        wait_sec = (next_midnight - now).total_seconds()
        await asyncio.sleep(wait_sec)

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{BASE_URL}/admin/reset_all_tokens",
                    headers={"X-ADMIN-TOKEN": ADMIN_TOKEN},
                    timeout=30,
                )
                print("🌓 Nightly reset status:", resp.status_code, await resp.text())
        except Exception as e:
            print("❌ Nightly reset failed:", e)





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

# スタートアップイベントでスケジューラ起動
@app.on_event("startup")
async def _start_nightly_scheduler():
    asyncio.create_task(nightly_reset_task())


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
