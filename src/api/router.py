from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from ..job_search.job_adapter import JobSearchAdapter
import os

router = APIRouter()

superjob_secret = os.getenv("SUPERJOB_SECRET_KEY")
adapter = JobSearchAdapter(superjob_secret) if superjob_secret else None

@router.get("/search/candidates")
async def search_candidates(
    keyword: str = Query(..., description="Ключевое слово для поиска"),
    town: str = Query("Совхоз имени Ленина", description="Город (ID или название)"),
    limit: int = Query(20, ge=1, le=100),
    min_salary: Optional[int] = None,
    experience_years: Optional[int] = None,
    include_contacts: bool = Query(False, description="Получить контакты (не более 100 в сутки)")
):
    if not adapter:
        raise HTTPException(500, "SuperJob API key not configured")
    try:
        candidates = await adapter.search_candidates(
            keyword=keyword,
            town=town,
            limit=limit,
            min_salary=min_salary,
            experience_years=experience_years,
            include_contacts=include_contacts
        )
        return {"candidates": candidates}
    except Exception as e:
        raise HTTPException(500, str(e))