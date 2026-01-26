from fastapi import APIRouter, HTTPException
from src.models import ResumeAnalysisRequest, CandidateSearchParams
from src.services.gigachat.simple_client import SimpleGigaChatClient
from src.services.gigachat.prompts import ANALYSIS_PROMPTS
from src.services.yandex_calendar import get_yandex_calendar_client
from src.models import ResumeAnalysisRequest, CandidateSearchParams, YandexCalendarEventRequest
from src.services.job_search import get_job_search_adapter
import asyncio

router = APIRouter()

@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "talkpro-backend",
        "version": "1.0.0"
    }

@router.post("/analyze/resume")
async def analyze_resume(request: ResumeAnalysisRequest):
    """
    Анализ резюме с использованием GigaChat API
    """
    client = SimpleGigaChatClient()
    
    try:
        result = await client.analyze_text(
            request.text, 
            ANALYSIS_PROMPTS["check_ai"]
        )
        
        if result is None:
            raise HTTPException(
                status_code=500,
                detail="Не удалось получить ответ от GigaChat API"
            )
        
        ai_probability = result["choices"][0]["message"]["content"]
        
        return {
            "status": "success",
            "message": "Анализ завершен",
            "resume_id": f"res_{hash(request.text) % 10000}",
            "ai_probability": ai_probability,
            "data_received": {
                "text_length": len(request.text),
                "check_ai": request.check_ai,
                "has_vacancy": bool(request.compare_with_vacancy)
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при анализе резюме: {str(e)}"
        )
    finally:
        await client.close()

@router.get("/search/candidates")
async def search_candidates(
    skills: str = "",  # "python,django"
    min_experience: int = 0,
    location: str = "Москва",
    limit: int = 20
):
    """
    Поиск кандидатов на job-площадках
    """
    adapter = get_job_search_adapter()
    
    # Парсим навыки из строки
    skills_list = [s.strip() for s in skills.split(",") if s.strip()] if skills else []
    
    try:
        results = await adapter.search_candidates(
            skills=skills_list,
            min_experience=min_experience,
            location=location,
            limit=limit
        )
        
        return {
            "status": "success",
            "search": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search/stats")
async def get_search_stats():
    """Статистика поиска кандидатов"""
    adapter = get_job_search_adapter()
    return {
        "status": "success",
        "stats": adapter.get_stats()
    }

@router.post("/yandex-calendar/event")
async def create_yandex_calendar_event(event_request: YandexCalendarEventRequest):
    """
    Создает событие собеседования в Яндекс.Календаре (мок)
    """
    client = get_yandex_calendar_client(use_queue=True)  # Используем очередь!
    
    try:
        event = await client.create_interview_event(
            candidate_email=event_request.candidate_email,
            interviewer_email=event_request.interviewer_email,
            start_time=event_request.start_time,
            duration_minutes=event_request.duration_minutes,
            title=event_request.title,
            description=event_request.description or "",
            location=event_request.location or ""
        )
        
        return {
            "status": "success",
            "message": "Событие создано (мок-режим)",
            "event": event,
            "note": "Используется мок-клиент, так как Яндекс API недоступно"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/yandex-calendar/stats")
async def get_yandex_calendar_stats():
    """Статистика работы Яндекс.Календарь"""
    client = get_yandex_calendar_client()
    
    stats = client.get_stats()
    
    if hasattr(client, 'get_metrics'):
        stats["metrics"] = client.get_metrics()
    
    return {
        "status": "success",
        "service": "yandex_calendar",
        "stats": stats
    }

@router.get("/yandex-calendar/queue/status")
async def get_yandex_calendar_queue_status():
    """Статус очереди"""
    client = get_yandex_calendar_client()
    
    if hasattr(client, 'get_queue_status'):
        return {
            "status": "success",
            "queue_status": client.get_queue_status()
        }
    return {"status": "success", "message": "Очередь не используется"}