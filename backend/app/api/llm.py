from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/summary/{pregnancy_id}")
def llm_summary(pregnancy_id: int) -> dict:
    raise HTTPException(501, "AI xulosa hali tayyor emas")
