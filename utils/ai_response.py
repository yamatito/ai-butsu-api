# ai-butsu-api/utils/ai_response.py
# ─────────────────────────────
import os, asyncpg, random
from typing import List, Dict, Tuple
from dotenv import load_dotenv
from openai import AsyncOpenAI
import re
from utils.init import trim_if_needed
from utils.prompt_assets import SYSTEM_PROMPT, FEW_SHOTS

load_dotenv()
OPENAI_MODEL          = os.getenv("OPENAI_MODEL",          "gpt-4o")
OPENAI_SUMMARY_MODEL  = os.getenv("OPENAI_SUMMARY_MODEL",  "gpt-3.5-turbo")
OPENAI_API_KEY        = os.getenv("OPENAI_API_KEY")
openai_client         = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ------------ tiktoken で概算 token 数 -------------
try:
    from tiktoken import encoding_for_model
    _enc35 = encoding_for_model("gpt-3.5-turbo")
    def _tok_len(text: str) -> int: return len(_enc35.encode(text))
except Exception:
    def _tok_len(text: str) -> int: return len(text) // 2

FULL_PAIR_LIMIT       = 2
SUMMARY_PAIR_MAX      = 6
TOKEN_BUDGET_HISTORY  = 900

# ──────────────────────────────
# BLESS トリガー語
# ──────────────────────────────
BLESS_TRIGGERS = {
    "お守り", "ご加護", "厄除け", "加持", "護摩", "御祈祷",
    "怖い夢", "不吉", "呪い", "不安が消えない", "心がざわつく"
}

# ──────────────────────────────
def _limit_questions(text: str, max_q: int = 1) -> str:
    q_cnt, out = 0, []
    for ch in text:
        if ch in ("?", "？"):
            q_cnt += 1
            out.append(ch if q_cnt <= max_q else "。")
        else:
            out.append(ch)
    return "".join(out)

# ──────────────────────────────
async def _summarize_pair(q: str, a: str) -> str:
    prompt = f"次の相談と回答を50字以内で要約してください。\n◆相談: {q}\n◆回答: {a}\n要約:"
    try:
        r = await openai_client.chat.completions.create(
            model=OPENAI_SUMMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0.2,
        )
        return r.choices[0].message.content.strip()
    except Exception:
        return (q[:25] + " / " + a[:25])[:50]

# ──────────────────────────────
async def _prepare_history(db: asyncpg.pool.Pool,
                           chat_id: str,
                           user_input: str) -> Tuple[List[Dict], List[str]]:
    rows = await db.fetch(
        """SELECT question, answer FROM conversations
           WHERE chat_id = $1 ORDER BY created_at ASC""",
        chat_id,
    )

    full_pairs, summaries = [], []
    if rows:
        # 直近 FULL_PAIR_LIMIT
        for r in rows[-FULL_PAIR_LIMIT:]:
            full_pairs.extend([
                {"role": "user", "content": r["question"]},
                {"role": "assistant", "content": r["answer"]},
            ])

        # それ以前は要約
        earlier_rows = rows[:-FULL_PAIR_LIMIT]
        total_tok = _tok_len(user_input) + sum(_tok_len(m["content"]) for m in full_pairs)
        for r in reversed(earlier_rows):
            summary = await _summarize_pair(r["question"], r["answer"])
            if len(summaries) < SUMMARY_PAIR_MAX and (total_tok + _tok_len(summary)) <= TOKEN_BUDGET_HISTORY:
                summaries.insert(0, summary)
                total_tok += _tok_len(summary)
            else:
                break
    return full_pairs, summaries

# ──────────────────────────────
def _detect_bless(text: str) -> bool:
    return any(t in text for t in BLESS_TRIGGERS)

# ──────────────────────────────
def _build_messages(full_pairs: List[Dict],
                    summaries: List[str],
                    user_input: str,
                    is_bless: bool) -> List[Dict]:

    msgs: List[Dict] = [{"role": "system", "content": SYSTEM_PROMPT}] + FEW_SHOTS

    if is_bless:
        msgs.append({"role": "assistant", "content": "[BLESS]"})

    for s in summaries:
        msgs.append({"role": "assistant", "content": f"(要約ログ) {s}"})

    msgs.extend(full_pairs)
    msgs.append({"role": "user", "content": user_input})

    if len(msgs) > 25:
        msgs = msgs[:1] + FEW_SHOTS + msgs[-(25 - 1 - len(FEW_SHOTS)):]
    return msgs

# ──────────────────────────────
def _postprocess(text: str, is_bless: bool) -> str:
   # --- <区分タグ> を除去 ------------------------------------
    # 行頭または改行直後に現れる [A] / [B] / [C] / [BLESS] を削る
    text = re.sub(r'(^|\n)\s*\[(?:A|B|C|BLESS)\]\s*', r'\1', text)

    text = text.replace("...", "。")
    text = _limit_questions(text)
    if is_bless and random.random() < 0.3 and not text.endswith(("合掌", "南無阿弥陀仏—")):
        text += "　合掌"
    return trim_if_needed(text)

# ──────────────────────────────
async def _call_openai(messages: List[Dict], is_bless: bool) -> Tuple[str, int]:
    r = await openai_client.chat.completions.create(
        model       = OPENAI_MODEL,
        messages    = messages,
        max_tokens  = 120,
        temperature = 0.75 if not is_bless else 0.8,
        top_p       = 0.95,
    )
    text = r.choices[0].message.content.strip()
    return _postprocess(text, is_bless), r.usage.total_tokens

# ──────────────────────────────
async def generate_answer(question: str) -> Tuple[str, int]:
    is_bless = _detect_bless(question)
    msgs = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + FEW_SHOTS
        + ( [{"role": "assistant", "content": "[BLESS]"}] if is_bless else [] )
        + [{"role": "user", "content": question}]
    )
    return await _call_openai(msgs, is_bless)

# ──────────────────────────────
async def generate_answer_with_context(chat_id: str,
                                       user_input: str,
                                       db: asyncpg.pool.Pool) -> Tuple[str, int]:

    is_bless                 = _detect_bless(user_input)
    full_pairs, summaries    = await _prepare_history(db, chat_id, user_input)
    messages                 = _build_messages(full_pairs, summaries, user_input, is_bless)
    return await _call_openai(messages, is_bless)
