# token.py
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
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
async def handle_admob_reward(request: Request):
    params = dict(request.query_params)
    print("✅ SSV callback:", params)

    user_id = params.get("user_id")
    reward_amount = int(params.get("reward_amount", 0))

    if not user_id or reward_amount <= 0:
        return {"status": "error", "msg": "Invalid reward request"}

    # reward_amount が 10なら、10トークンでも、500換算でもOK
    # 例：1つの報酬 = 50トークン
    await reward_tokens_for_ad(user_id, reward_amount * 50)

    return {"status": "ok"}
