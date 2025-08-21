# ai-butsu-api/routers/omikuji.py
from datetime import date, timedelta, datetime, timezone
import hashlib, random, uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from utils.init import get_db  # ← あなたのDB依存をそのまま利用

router = APIRouter()

JST = timezone(timedelta(hours=9))

# ─────────────────────────────────────────────────────
# 共通：引いた ref_id を正規化して返す
# ─────────────────────────────────────────────────────
async def _render_draw(db, draw_type: Literal["word","omikuji"], ref_id: uuid.UUID):
    if draw_type == "word":
        row = await db.fetchrow("""
            select title, body, action_hint
            from daily_words where id = $1
        """, ref_id)
        if not row:
            return None
        return {
            "type": "word",
            "title": row["title"],
            "body": row["body"],
            "action_hint": row["action_hint"],
        }
    else:
        row = await db.fetchrow("""
            select grade, headline, guidance, action_hint
            from omikuji where id = $1
        """, ref_id)
        if not row:
            return None
        # title は headline に寄せて、grade は別で返す
        return {
            "type": "omikuji",
            "grade": row["grade"],
            "title": row["headline"],
            "guidance": row["guidance"],
            "action_hint": row["action_hint"],
        }

# ─────────────────────────────────────────────────────
# GET /daily/today?type=word|omikuji&user_id=...
# 決定論抽選（user_id+date+type）＋ 30日再出防止
# ─────────────────────────────────────────────────────
@router.get("/daily/today")
async def get_today(
    type: Literal["word","omikuji"] = Query(...),
    user_id: uuid.UUID = Query(...),
    db=Depends(get_db),
):
    today = datetime.now(JST).date()

    accepted = await db.fetchval(
        "select last_active = $2 from user_streaks where user_id=$1",
        user_id, today
    ) or False

    # 1) その日の確定結果があればそれを返す
    drawn = await db.fetchrow("""
        select ref_id from daily_draws
        where user_id=$1 and date=$2 and type=$3::draw_type
        limit 1
    """, user_id, today, type)
    if drawn:
        ref_id = drawn["ref_id"]                 # ← 修正
        payload = await _render_draw(db, type, ref_id)
        return { **(payload or {"type": type}), "accepted": accepted }

    # 2) 30日内の自分の重複を除外
    exclude = await db.fetch("""
        select ref_id from daily_draws
        where user_id=$1 and date > $2 and type=$3::draw_type
    """, user_id, today - timedelta(days=30), type)
    exclude_ids = [r["ref_id"] for r in exclude]

    table = "daily_words" if type == "word" else "omikuji"
    candidates = await db.fetch(
        f"""
        select id, coalesce(rarity,1) as rarity
        from {table}
        where is_active = true
          and (array_length($1::uuid[],1) is null or id <> ALL($1::uuid[]))
        """,
        exclude_ids
    )
    if not candidates:
        candidates = await db.fetch(
            f"select id, coalesce(rarity,1) as rarity from {table} where is_active=true"
        )
    if not candidates:
        return {"type": type, "empty": True, "accepted": accepted}

    seed_str = f"{user_id}:{today.isoformat()}:{type}"
    seed = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16)
    rnd = random.Random(seed)

    def weight(r: int) -> int:
        return {1:80, 2:20, 3:6, 4:2, 5:1}.get(int(r or 1), 1)

    pool = []
    for c in candidates:
        pool.extend([c["id"]] * weight(c["rarity"]))

    ref_id: uuid.UUID = rnd.choice(pool)

    # 5) 確定ログ（1日1回）
    draw_id = uuid.uuid4()
    await db.execute("""
        insert into daily_draws (id, user_id, date, type, ref_id, seed, drawn_at)
        values ($1,$2,$3,$4::draw_type,$5,$6, now())
        on conflict (user_id, date, type) do nothing
    """, draw_id, user_id, today, type, ref_id, seed_str)

    payload = await _render_draw(db, type, ref_id)
    return { **(payload or {"type": type}), "accepted": accepted }


# ─────────────────────────────────────────────────────
# /streak/bump 連続日数更新（GET/POST両方OK・冪等）
# ─────────────────────────────────────────────────────
@router.post("/streak/bump")
@router.get("/streak/bump")
async def bump(user_id: uuid.UUID = Query(...), db=Depends(get_db)):
    today = datetime.now(JST).date()
    row = await db.fetchrow("""
        select last_active, streak, best_streak
        from user_streaks where user_id=$1
    """, user_id)

    if not row:
        await db.execute("""
            insert into user_streaks (user_id, last_active, streak, best_streak)
            values ($1,$2,1,1)
        """, user_id, today)
        return {"streak": 1, "best_streak": 1, "date": str(today)}

    last, streak, best = row["last_active"], row["streak"], row["best_streak"]

    if last == today:
        return {"streak": streak, "best_streak": best, "date": str(today), "status": "already_bumped"}

    is_yesterday = (last is not None) and (last + timedelta(days=1) == today)
    new_streak = (streak or 0) + 1 if is_yesterday else 1
    new_best = max(best or 0, new_streak)

    await db.execute("""
        update user_streaks
        set last_active=$2, streak=$3, best_streak=$4
        where user_id=$1
    """, user_id, today, new_streak, new_best)

    return {"streak": new_streak, "best_streak": new_best, "date": str(today)}
