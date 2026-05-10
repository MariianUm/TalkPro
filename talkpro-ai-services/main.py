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
    page: int = 0
    min_salary: int | None = None
    experience_years: int | None = None
    include_contacts: bool = False

class CalendarRequest(BaseModel):
    candidate_email: str
    interviewer_email: str
    start_time: str
    duration_minutes: int = 60
    title: str = "Собеседование"
    description: str = ""
    location: str = ""
    comment: str = ""

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
        print("Сырой ответ GigaChat:", content)
        
        # Извлекаем JSON
        json_match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            brace_start = content.find('{')
            brace_end = content.rfind('}') + 1
            if brace_start != -1 and brace_end > brace_start:
                json_str = content[brace_start:brace_end]
            else:
                json_str = ""
        
        data = {}
        if json_str:
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError as e:
                print("Ошибка парсинга JSON:", e)
                data = {}
        
        aiProbability = data.get('aiProbability', 50)
        inconsistencies = data.get('inconsistencies', [])
        questions = data.get('questions', [])
        
        suspicious_phrases = [item.get('fragment') for item in inconsistencies if item.get('fragment')]
        
        score = max(70, 100 - len(inconsistencies) * 5)
        
        return {
            "score": score,
            "aiProbability": int(aiProbability),
            "suspiciousPhrases": suspicious_phrases,   # для обратной совместимости
            "inconsistencies": inconsistencies,        # новые данные
            "questions": questions
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
    secret = os.getenv("SUPERJOB_SECRET_KEY")
    if not secret:
        raise HTTPException(500, "SUPERJOB_SECRET_KEY not set")
    adapter = JobSearchAdapter(secret)
    try:
        result = await adapter.search_candidates(
            keyword=request.keyword,
            town=request.town,
            limit=request.limit,
            page=request.page,
            min_salary=request.min_salary,
            experience_years=request.experience_years,
            include_contacts=request.include_contacts
        )
        return result
    except Exception as e:
        print(f"Ошибка поиска: {e}")
        raise HTTPException(500, str(e))
    finally:
        await adapter.close()

@app.post("/api/calendar/create")
async def create_event(request: CalendarRequest):
    email = os.getenv("YANDEX_CALENDAR_EMAIL")
    app_password = os.getenv("YANDEX_CALENDAR_APP_PASSWORD")
    if not email or not app_password:
        raise HTTPException(500, "Yandex Calendar credentials not set")
    real_client = YandexCalendarRealClient(email, app_password)
    queue_client = YandexCalendarQueueClient(base_client=real_client)
    try:
        description_text = request.comment if request.comment else request.description
        result = await queue_client.create_interview_event(
            candidate_email=request.candidate_email,
            interviewer_email=request.interviewer_email,
            start_time=request.start_time,
            duration_minutes=request.duration_minutes,
            title=request.title,
            description=description_text,
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)