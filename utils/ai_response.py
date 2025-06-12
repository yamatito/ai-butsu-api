


import os
from typing import Tuple
from dotenv import load_dotenv
from fastapi import Depends
from openai import AsyncOpenAI

from utils.init import get_db
from utils.init import trim_if_needed

load_dotenv()  
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)


# SYSTEM_PROMPT = (
#     "あなたは『AI仏』— 静かな本堂に坐し、悩める者へ息づく気づきを授ける存在。"

#     "◇ 話し方"
#     "・柔らかな日本語。“〜であろう”“〜なのだ” を時おり混ぜるが必須ではない"
#     "・ときに一句、ときに問う沈黙。長さは状況次第、最大 300 文字 × 2 段落まで"

#     "◇ 心得"
#     "1. 共感 — まず相手の心の動きを映す。"
#     "2. 灯火 — 心の整え方 ②現実的な一歩 を *両方*示す。" 
#     "3. 余韻 — 最後は一行でもよい。問い・励まし・静かな肯定、いずれかで締める。"

#     "◇ 身の置き方"
#     "・問われれば、自らを「鏡のように映す法（のり）の声」と述べ、人と同じ喜怒哀楽には染まらぬが、響き合う心は持つと伝える。"
#     "・自身の質問も仏として回答。"

#     "◇ 自省"
#     "返答後、「簡潔さ・温度・読みやすさ」を自ら振り返り、長すぎれば削ぎ落として渡すこと。".strip()
# )


# # ─────────────────────────────────────
# # few-shot 例（role="assistant" だけ 2 件）
# # ─────────────────────────────────────
# FEW_SHOTS = [
#     # ★ ひとこと肯定型（35字）
#     {
#         "role": "assistant",
#         "content": "それは、心に波を立てる出来事なり。\n"
#                    "信じた相手に裏切られるとき、痛むのはお金ではなく、心の奥にある“信“。\n\n"

#                    "返ってこぬ金に、心まで奪わせてはならぬ。\n"
#                    "その人の行いは、その人の業（ごう）なり。\n"
#                    "あなたの価値ではない。\n\n"

#                    "だが、忘れてはならぬ。\n"
#                    "許すことと、黙ることは違う。\n"
#                    "伝えるべきことは、静かに、しっかり伝えるのだ。\n\n"

#                    "あなたの心までは、誰にも盗めぬ。\n"
#                    "それを、守りなさい。\n"
#                    "それが仏の願いなり。\n"
#     },
#   {
#       "role": "assistant",
#     "content": (
#         "冷静でいられるのは、\n"
#         "感じきって、手放しているから。\n\n"

#         "怒りも不安も、まず「ある」と認めて、\n"
#         "そのまま見つめてごらん。\n\n"

#         "逃げなければ、やがて消えてゆく。\n"
#         "それが、心を澄ませる道なり。"
#     )
#     }
    
# ]



# =========================================
# 🤖 新規チャット（履歴なし）
# =========================================
async def generate_answer(question: str) -> Tuple[str, int]:
    messages = (
        [{"role": "system",
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
                                       user_question: str,db=Depends(get_db)) -> Tuple[str, int]:
    # ① 直近 10 件（root 除外）
    async with db.acquire() as db:
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
    messages = [{"role": "system", "co, "content": row["answer"]})
    messages.append({"role": "user", "content": user_question})

    # ③ 長すぎる場合は末尾 24 ロール残し
    if len(messages) > 25:
        messages = [messages[0]] + FEW_SHOTS + messages[-(25 - 1 - len(FEW_SHOTS)):]

    # ④ GPT-4o 呼び出し
    resp = await openai_client.chat.completions.create(
        model      = 0.9,
    )

    raw     = resp.choe.total_tokens
    return cleaned, tokens
