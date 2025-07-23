# token.py
# -----------------------------------------------
from datetime import date
import os

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from utils.init import get_db, reset_daily_if_needed, reward_tokens_for_ad

router = APIRouter()

# ─────── 設定値（必要なら .env に移動） ───────
MAX_FREE_TOKENS_PER_DAY     = 6000      # 無料ユーザー 1 日上限
MAX_PREMIUM_TOKENS_PER_DAY  = None      # None = 無制限
TOKENS_ON_AD_WATCH          = 1000       # 広告報酬
_ADMIN_TOKEN                = os.getenv("ADMIN_TOKEN", "super_secret_token")
# -----------------------------------------------


# ────────────────────────────────
# 0. 共通ユーティリティ（全ユーザー一括リセット）
# ────────────────────────────────
async def _reset_all_tokens(conn, today: date):
    """
    全ユーザーの残トークンを “日次上限” まで回復。
    - 無料: MAX_FREE_TOKENS_PER_DAY
    - プレミアム: MAX_PREMIUM_TOKENS_PER_DAY (Noneならスキップ)
    """
    # 無料プラン
    await conn.execute("""
        UPDATE user_tokens
        SET tokens_remaining = $1,
            daily_used       = 0,
            daily_rewarded   = 0,
            last_reset_date  = $2
        WHERE plan = 'free'
    """, MAX_FREE_TOKENS_PER_DAY, today)

    # プレミアムプラン
    if MAX_PREMIUM_TOKENS_PER_DAY is not None:
        await conn.execute("""
            UPDATE user_tokens
            SET tokens_remaining = $1,
                daily_used       = 0,
                daily_rewarded   = 0,
                last_reset_date  = $2
            WHERE plan = 'premium'
        """, MAX_PREMIUM_TOKENS_PER_DAY, today)
# ────────────────────────────────


# ────────────────────────────────
# 1. ユーザー用: トークン残高取得 & 自動回復
# ────────────────────────────────
@router.get("/token_status")
async def get_token_status(user_id: str = Query(...), db=Depends(get_db)):
    """
    - アクセスするたび reset_daily_if_needed(...) が
      “そのユーザーだけ” 日次リセットしてくれる。
    """
    async with db.acquire() as conn:
        await reset_daily_if_needed(conn, user_id)

        row = await conn.fetchrow(
            """SELECT tokens_remaining, daily_used, daily_rewarded,
                      plan, last_reset_date
               FROM user_tokens WHERE user_id = $1""",
            user_id,
        )

        return {
            "remaining":       row["tokens_remaining"],
            "used":            row["daily_used"],
            "ad_reward_count": row["daily_rewarded"],
            "plan":            row["plan"],
            "limit":           MAX_FREE_TOKENS_PER_DAY,
            "last_reset_date": row["last_reset_date"].isoformat()
                               if row["last_reset_date"] else None,
        }


# ────────────────────────────────
# 2. 広告報酬コールバック（AdMob SSV）
# ────────────────────────────────
@router.get("/admob/reward")
async def handle_admob_reward(request: Request, db=Depends(get_db)):
    params = dict(request.query_params)
    print("✅ SSV callback:", params)

    user_id       = params.get("user_id")
    reward_amount = int(params.get("reward_amount", 0))

    if not user_id or reward_amount <= 0:
     return JSONResponse(
        status_code=400,
        content={"status": "error", "msg": "Invalid reward"}
     )
    # 例: 1 reward → 50 トークン * 倍率
    await reward_tokens_for_ad(user_id, reward_amount * 50, db)
    return {"status": "ok"}


# ────────────────────────────────
# 3. 管理者: 全ユーザー手動リセット
# ────────────────────────────────
@router.post("/admin/reset_all_tokens")
async def admin_reset_all(request: Request, db=Depends(get_db)):
    """
    管理者が全ユーザー残高を強制リセットするエンドポイント。
    """
    if request.headers.get("X-ADMIN-TOKEN") != _ADMIN_TOKEN:
        return {"status": "unauthorized"}

    today = date.today()
    async with db.acquire() as conn:
        await _reset_all_tokens(conn, today)

    return {"status": "ok", "date": today.isoformat()}
