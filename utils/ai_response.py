# ai-butsu-api/utils/ai_response.py
# ==================================
#  ✔ 直近 2 ペアは “そのまま” 投入
#  ✔ それ以前は要約して圧縮
#  ✔ 「短文保険」を撤廃（短文でも文脈があればそのまま送る）
# ==================================
import os, asyncpg
from typing import List, Dict, Tuple
from dotenv import load_dotenv
from openai import AsyncOpenAI
from utils.init import trim_if_needed

load_dotenv()
OPENAI_MODEL          = os.getenv("OPENAI_MODEL",          "gpt-4o")
OPENAI_SUMMARY_MODEL  = os.getenv("OPENAI_SUMMARY_MODEL",  "gpt-3.5-turbo")
OPENAI_API_KEY        = os.getenv("OPENAI_API_KEY")
openai_client         = AsyncOpenAI(api_key=OPENAI_API_KEY)

from utils.prompt_assets import SYSTEM_PROMPT, FEW_SHOTS

# ------------ tiktoken で概算 token 数 -------------
try:
    from tiktoken import encoding_for_model
    _enc35 = encoding_for_model("gpt-3.5-turbo")
    def _tok_len(text: str) -> int: return len(_enc35.encode(text))
except Exception:
    def _tok_len(text: str) -> int: return len(text) // 2

FULL_PAIR_LIMIT       = 2     # 直近 n ペアをそのまま挿入
SUMMARY_PAIR_MAX      = 6     # 要約を最大 n ペア
TOKEN_BUDGET_HISTORY  = 900   # user_input を含め 900 token に抑える

# ──────────────────────────────
# 1. ペア要約
# ──────────────────────────────
async def _summarize_pair(q: str, a: str) -> str:
    prompt = (
        "次の相談と回答を 50 字以内で要約してください。\n"
        "◆相談: " + q + "\n◆回答: " + a + "\n要約:"
    )
    try:
        r = await openai_client.chat.completions.create(
            model       = OPENAI_SUMMARY_MODEL,
            messages    = [{"role": "user", "content": prompt}],
            max_tokens  = 60,
            temperature = 0.2,
        )
        return r.choices[0].message.content.strip()
    except Exception:
        return (q[:25] + " / " + a[:25])[:50]

# ──────────────────────────────
# 2. 履歴を「フル + 要約」に分割
# ──────────────────────────────
async def _prepare_history(db: asyncpg.pool.Pool,
                           chat_id: str,
                           user_input: str) -> Tuple[List[Dict], List[str]]:
    """
    return -> (full_pairs_msgs, summaries)
    full_pairs_msgs : 直近 FULL_PAIR_LIMIT ペアをそのまま user/assistant ロールで
    summaries       : それ以前を古い順に 50 文字要約
    """
    rows = await db.fetch(
        """
        SELECT question, answer
        FROM conversations
        WHERE chat_id = $1
        ORDER BY created_at ASC
        """,
        chat_id,
    )
    full_pairs_msgs: List[Dict] = []
    summaries: List[str]        = []

    if rows:
        # 直近 FULL_PAIR_LIMIT ペア
        last_rows = rows[-FULL_PAIR_LIMIT:]
        for r in last_rows:
            full_pairs_msgs.extend([
                {"role": "user",      "content": r["question"]},
                {"role": "assistant", "content": r["answer"]},
            ])

        # それ以前は要約
        earlier_rows = rows[:-FULL_PAIR_LIMIT]
        total_tok = _tok_len(user_input) + sum(_tok_len(m["content"]) for m in full_pairs_msgs)
        for r in reversed(earlier_rows):           # 新しい方から
            summary = await _summarize_pair(r["question"], r["answer"])
            s_tok   = _tok_len(summary)
            if len(summaries) < SUMMARY_PAIR_MAX and (total_tok + s_tok) <= TOKEN_BUDGET_HISTORY:
                summaries.insert(0, summary)       # 古い順に
                total_tok += s_tok
            else:
                break
    return full_pairs_msgs, summaries

# ──────────────────────────────
# 3. メッセージ組み立て
# ──────────────────────────────
def _build_messages(full_pairs: List[Dict],
                    summaries: List[str],
                    user_input: str) -> List[Dict]:

    msgs: List[Dict] = [{"role": "system", "content": SYSTEM_PROMPT}] + FEW_SHOTS

    for s in summaries:
        msgs.append({"role": "assistant", "content": f"(要約ログ) {s}"})

    msgs.extend(full_pairs)               # 直近のやり取りはそのまま

    msgs.append({"role": "user", "content": user_input})

    # 念のため 25 ロールに収める
    if len(msgs) > 25:
        msgs = msgs[:1] + FEW_SHOTS + msgs[-(25 - 1 - len(FEW_SHOTS)):]
    return msgs

# ──────────────────────────────
# 4. OpenAI 呼び出し
# ──────────────────────────────
async def _call_openai(messages: List[Dict]) -> Tuple[str, int]:
    r = await openai_client.chat.completions.create(
        model       = OPENAI_MODEL,
        messages    = messages,
        max_tokens  = 120,
        temperature = 0.75,
        top_p       = 0.95,
    )
    text = r.choices[0].message.content.strip().replace("...", "。")
    return trim_if_needed(text), r.usage.total_tokens

# ──────────────────────────────
# 5. 外部公開関数
# ──────────────────────────────
async def generate_answer(question: str) -> Tuple[str, int]:
    msgs = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + FEW_SHOTS
        + [{"role": "user", "content": question}]
    )
    return await _call_openai(msgs)


async def generate_answer_with_context(chat_id: str,
                                       user_input: str,
                                       db: asyncpg.pool.Pool) -> Tuple[str, int]:

    full_pairs, summaries = await _prepare_history(db, chat_id, user_input)
    messages              = _build_messages(full_pairs, summaries, user_input)
    return await _call_openai(messages)


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


# async def generate_answer(question: str) -> Tuple[str, int]:
#     messages = (
#         [{"role": "system",
#     )

#     resp = await openai_client.chat.completions.create(
#         model       = OPENAI_MODEL,
#         messages    = messages,
#         max_tokens  = 180,         # ≒ 200字
#         temperature = 0.65,         # 0.5〜0.7 の中庸で安定
#         top_p       = 0.9,
#     )

#     raw     = resp.choices[0].message.content.strip().replace("...", "。")
#     cleaned = trim_if_needed(resp.choices[0].message.content.strip().replace("...", "。"))
#     tokens  = resp.usage.total_tokens
#     return cleaned, tokens



# async def generate_answer_with_context(chat_id: str,
#                                        user_question: str,db=Depends(get_db)) -> Tuple[str, int]:
#     # ① 直近 10 件（root 除外）
#     async with db.acquire() as db:
#         history = await db.fetch(
#             """
#             SELECT question, answer
#             FROM conversations
#             WHERE chat_id = $1 AND is_root = false
#             ORDER BY created_at DESC
#             LIMIT 10
#             """,
#             chat_id,
#         )
#     history = list(reversed(history))

#     # ② メッセージ組み立て
#     messages = [{"role": "system", "co, "content": row["answer"]})
#     messages.append({"role": "user", "content": user_question})

#     # ③ 長すぎる場合は末尾 24 ロール残し
#     if len(messages) > 25:
#         messages = [messages[0]] + FEW_SHOTS + messages[-(25 - 1 - len(FEW_SHOTS)):]

#     # ④ GPT-4o 呼び出し
#     resp = await openai_client.chat.completions.create(
#         model      = 0.9,
#     )

#     raw     = resp.choe.total_tokens
#     return cleaned, tokens
