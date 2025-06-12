from fastapi import APIRouter, Depends, Request
from utils.init import get_db  # FastAPIインスタンスと同じディレクトリならこれでOK

router = APIRouter()

@router.get("/health")
async def health_check(request: Request):
    db = getattr(request.app.state, "db_pool", None)
    return {"status": "ok" if db else "error"}


@router.get("/check_db")
async def check_database_connection(db=Depends(get_db)):
    try:
        async with db.acquire() as conn:
            result = await conn.fetch("SELECT 1;")
            if result:
                return {"status": "ok", "message": "Supabase DB接続成功"}
            return {"status": "error", "message": "応答なし"}
    except Exception as e:
        return {"status": "error", "message": f"DB接続エラー: {e}"}


