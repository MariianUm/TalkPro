import os
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv
import json
import re

load_dotenv()

sys.path.append(str(Path(__file__).parent))

from gigachat.gateway import GigaChatGateway
from job_search.job_adapter import JobSearchAdapter
from yandex_calendar.queue_client import YandexCalendarQueueClient
from yandex_calendar.yandex_calendar_real import YandexCalendarRealClient

app = FastAPI(title="TalkPro AI Services")

# Модели запросов
class AnalyzeRequest(BaseModel):
    text: str
    prompt_key: str = "find_exaggerations"

class SearchRequest(BaseModel):
    keyword: str
    town: str = "Москва"
    limit: int = 20
    min_salary: int | None = None
    experience_years: int | None = None

class CalendarRequest(BaseModel):
    candidate_email: str
    interviewer_email: str
    start_time: str
    duration_minutes: int = 60
    title: str = "Собеседование"
    description: str = ""
    location: str = ""

@app.post("/api/gigachat/analyze")
async def analyze_resume(request: AnalyzeRequest):
    api_key = os.getenv("GIGACHAT_API_KEY")
    if not api_key:
        raise HTTPException(500, "GIGACHAT_API_KEY not set")
    gateway = GigaChatGateway(api_key=api_key)
    try:
        result = await gateway.analyze(
            prompt_key=request.prompt_key,
            text=request.text
        )
        
        content = result["choices"][0]["message"]["content"]
        
        json_match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            start = content.find('[')
            end = content.rfind(']') + 1
            if start != -1 and end > start:
                json_str = content[start:end]
            else:
                json_str = "[]"
        
        try:
            exaggerations = json.loads(json_str)
        except:
            exaggerations = []
        
        suspicious_phrases = []
        for item in exaggerations:
            fragment = item.get('fragment')
            if fragment:
                suspicious_phrases.append(fragment)
        
        # Вычисляем aiProbability (здесь можно сделать отдельный запрос к GigaChat,
        # Пока возьмём среднюю уверенность
        avg_confidence = 0
        if exaggerations:
            avg_confidence = sum(item.get('confidence', 0) for item in exaggerations) / len(exaggerations)
        aiProbability = int(avg_confidence) if avg_confidence else 50
        
        # score можно вычислить на основе количества проблем
        score = max(70, 100 - len(exaggerations) * 5) 
        
        return {
            "score": score,
            "aiProbability": aiProbability,
            "suspiciousPhrases": suspicious_phrases
        }
    except Exception as e:
        print(f"Ошибка при вызове GigaChat: {repr(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))
    finally:
        await gateway.close()

@app.post("/api/superjob/search")
async def search_candidates(request: SearchRequest):
    # Пока заглушка
    return {
        "candidates": [
            {
                "id": 1,
                "title": "Python разработчик",
                "salary_from": 150000,
                "salary_to": 250000,
                "currency": "rub",
                "experience": "от 3 лет",
                "city": "Москва",
                "url": "https://example.com/resume1"
            }
        ]
    }

@app.post("/api/calendar/create")
async def create_event(request: CalendarRequest):
    email = os.getenv("YANDEX_CALENDAR_EMAIL")
    app_password = os.getenv("YANDEX_CALENDAR_APP_PASSWORD")
    if not email or not app_password:
        raise HTTPException(500, "Yandex Calendar credentials not set")
    real_client = YandexCalendarRealClient(email, app_password)
    queue_client = YandexCalendarQueueClient(base_client=real_client)
    try:
        result = await queue_client.create_interview_event(
            candidate_email=request.candidate_email,
            interviewer_email=request.interviewer_email,
            start_time=request.start_time,
            duration_minutes=request.duration_minutes,
            title=request.title,
            description=request.description,
            location=request.location
        )
        return result
    except Exception as e:
        print(f"Ошибка при создании события календаря: {repr(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))
    
    finally:
        await real_client.close()