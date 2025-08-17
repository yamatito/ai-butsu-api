import json
import uuid
from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
import supabase
from fastapi import APIRouter
from models import ChatRequest, NewChatRequest
from utils.ai_response import generate_answer, generate_answer_with_context
from utils.init import check_token_limit_and_log, empty_embedding_vector, save_chat_pair_to_storage, save_message_pair_to_storage
from utils.init import get_db 
router = APIRouter()


@router.post("/new_chat")
async def new_chat(request: NewChatRequest, db=Depends(get_db)):
    user_id = str(uuid.UUID(request.user_id))
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="質問が空です。")

    # 仮のトークン数でチェック（長さ + 平均回答分）
    estimated_tokens = _rough_token_estimate(question)
    is_allowed = await check_token_limit_and_log(user_id, estimated_tokens, db)
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
        success = await check_token_limit_and_log(user_id, token_diff, db)
        if not success:
            limited = True

    # DBに保存
    chat_id = str(uuid.uuid4())
    embedding_str = "[" + ", ".join(["0.0"] * 1536) + "]"
    async with db.acquire() as db:
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




@router.post("/chat")
async def add_message(request: ChatRequest, db=Depends(get_db)):
    chat_id = request.chat_id
    user_id = request.user_id
    question = (request.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="質問が空です。")

    estimated_tokens = _rough_token_estimate(question)
    is_allowed = await check_token_limit_and_log(user_id, estimated_tokens, db)
    if not is_allowed:
        return {
            "chat_id": chat_id,
            "answer": "今日はここまでにしましょう。また明日、静かにお話しましょう。",
            "limited": True
        }

    answer, tokens_used = await generate_answer_with_context(chat_id, question, db)

    token_diff = tokens_used - estimated_tokens
    limited = False
    if token_diff > 0:
        success = await check_token_limit_and_log(user_id, token_diff, db)
        if not success:
            limited = True

    embedding_str = empty_embedding_vector()
    async with db.acquire() as db:
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


def _rough_token_estimate(text: str) -> int:
    # 日本語ざっくり想定：2.2文字 ≒ 1token。回答分バッファを足す
    base = max(1, int(len(text) / 2.2))
    return base + 300   # 応答バッファ（自動つづき込みでも余裕め）

@router.get("/chat/{chat_id}")
async def get_chat(chat_id: str,db=Depends(get_db)):
    try:
        chat_id = str(uuid.UUID(chat_id))
        async with db.acquire() as db:
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

@router.get("/storage_chat/{chat_id}")
async def get_chat_from_storage(chat_id: str):
    bucket_name = "chat-logs"
    file_name = f"chat_{chat_id}.json"
    try:
        res = supabase.storage.from_(bucket_name).download(file_name)
        data = json.loads(res.decode("utf-8"))
        return {"chat_id": chat_id, "messages": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ストレージから取得失敗: {e}")
