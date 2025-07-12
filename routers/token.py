# token.py
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from utils.init import get_db

from utils.init import reset_daily_if_needed, reward_tokens_for_ad

router = APIRouter()

MAX_FREE_TOKENS_PER_DAY = 5000
TOKENS_ON_AD_WATCH = 500


# トークン状態取得API
@router.get("/token_status")
async def get_token_status(user_id: str = Query(...),db=Depends(get_db)):
    async with db.acquire() as db:
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



@router.get("/admob/reward")
async def handle_admob_reward(request: Request, db=Depends(get_db)):
    """
    AdMob リワード広告の SSV（Server-Side Verification）コールバック。
    - Google から `GET /admob/reward?...` が届く。
    - user_id と reward_amount を取り出し、トークンを加算。
    """
    params = dict(request.query_params)
    print("✅ SSV callback:", params)

    user_id = params.get("user_id")
    reward_amount = int(params.get("reward_amount", 0))

    # バリデーション
    if not user_id or reward_amount <= 0:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "msg": "Invalid reward request"},
        )

    # ここでトークンを加算（例：報酬量 × 50 トークン）
    await reward_tokens_for_ad(user_id, reward_amount * 50, db)

    return {"status": "ok"}



# 管理者専用の固定トークン（ハードコード）
_ADMIN_TOKEN = "super_secret_token"
_DEFAULT_TOKENS = 5000

@router.post("/admin/reset_all_tokens")
async def reset_all_tokens(request: Request, db=Depends(get_db)):
    # --- 超シンプルなヘッダートークン認証 ---
    if request.headers.get("X-ADMIN-TOKEN") != _ADMIN_TOKEN:
        return {"status": "unauthorized"}

    today = date.today()

    async with db.acquire() as conn:
        await conn.execute(
            """
            UPDATE user_tokens
            SET
              tokens_remaining = $1,
              daily_used       = 0,
              daily_rewarded   = 0,
              last_reset_date  = $2
            """,
            _DEFAULT_TOKENS,
            today,
        )

    return {"status": "ok", "date": today.isoformat()}