"""
Модели данных Pydantic для всего приложения
"""
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime

class ResumeAnalysisRequest(BaseModel):
    text: str
    check_ai: bool = True
    compare_with_vacancy: Optional[dict] = None

class CandidateSearchParams(BaseModel):
    skills: List[str] = []
    min_experience: int = 0  # лет
    location: str = "Москва"
    limit: int = 50
    
    class Config:
        json_schema_extra = {
            "example": {
                "skills": ["Python", "Django"],
                "min_experience": 3,
                "location": "Москва",
                "limit": 20
            }
        }

class YandexCalendarEventRequest(BaseModel):
    candidate_email: str
    interviewer_email: str
    start_time: str  # ISO формат: "2024-01-20T14:00:00"
    duration_minutes: int = Field(60, ge=15, le=240)
    title: str = "Техническое собеседование"
    description: Optional[str] = None
    location: Optional[str] = "Онлайн (Яндекс.Телемост)"
    
    @validator('start_time')
    def validate_start_time(cls, v):
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError(
                'Некорректный формат времени. Используйте ISO формат: YYYY-MM-DDTHH:MM:SS'
            )
    
    class Config:
        json_schema_extra = {
            "example": {
                "candidate_email": "candidate@example.com",
                "interviewer_email": "hr@company.ru",
                "start_time": "2024-01-20T14:00:00",
                "duration_minutes": 60,
                "title": "Собеседование на позицию Python разработчика",
                "description": "Обсуждение технических навыков и опыта работы",
                "location": "Яндекс.Телемост"
            }
        }

