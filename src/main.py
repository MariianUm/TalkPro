import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv
import json
import re
import hashlib

load_dotenv()

from src.services.gigachat.gateway import GigaChatGateway
from src.services.job_search.job_adapter import JobSearchAdapter
from src.services.yandex_calendar.queue_client import YandexCalendarQueueClient
from src.services.yandex_calendar.yandex_calendar_real import YandexCalendarRealClient
from src.services.yandex_calendar.mock_client import MockYandexCalendarClient

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
    include_contacts: bool = False

class CalendarRequest(BaseModel):
    candidate_email: str
    interviewer_email: str
    start_time: str
    duration_minutes: int = 60
    title: str = "Собеседование"
    description: str = ""
    location: str = ""

def _fallback_analysis(text: str) -> dict:
    normalized = (text or "").strip()
    if not normalized:
        return {"score": 70, "aiProbability": 50, "suspiciousPhrases": [], "inconsistencies": [], "questions": []}
    lowered = normalized.lower()
    markers = [
        "оптимизация",
        "инновацион",
        "эффективн",
        "синерги",
        "digital",
        "agile",
        "leading",
        "expert",
    ]
    marker_hits = sum(1 for marker in markers if marker in lowered)
    exclamations = normalized.count("!")
    hash_tail = int(hashlib.sha256(normalized.encode("utf-8")).hexdigest()[-2:], 16) % 15
    ai_probability = min(95, max(10, 30 + marker_hits * 10 + exclamations * 3 + hash_tail))
    score = max(55, 100 - ai_probability // 2)
    suspicious = []
    for marker in markers:
        if marker in lowered and len(suspicious) < 5:
            suspicious.append(marker)
    inconsistencies = [
        {
            "fragment": marker,
            "issue": "Формулировка выглядит шаблонной и требует уточнения на интервью.",
            "confidence": min(95, ai_probability)
        }
        for marker in suspicious
    ]
    questions = [
        f"Опишите конкретный кейс, где вы применяли: {item['fragment']}."
        for item in inconsistencies[:5]
    ]
    return {
        "score": int(score),
        "aiProbability": int(ai_probability),
        "suspiciousPhrases": suspicious,
        "inconsistencies": inconsistencies,
        "questions": questions
    }

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
        if not result or "choices" not in result:
            return _fallback_analysis(request.text)
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
        inconsistencies = []
        for item in exaggerations:
            fragment = item.get("fragment")
            issue = item.get("issue")
            confidence = item.get("confidence")
            if fragment:
                inconsistencies.append({
                    "fragment": fragment,
                    "issue": issue or "Требуется дополнительная проверка на собеседовании.",
                    "confidence": confidence if isinstance(confidence, int) else None
                })
        suspicious_phrases = [item["fragment"] for item in inconsistencies]
        questions = [
            f"Расскажите подробнее про опыт, где вы указывали: {item['fragment']}."
            for item in inconsistencies[:5]
        ]
        avg_confidence = sum(item.get('confidence', 0) for item in exaggerations) / len(exaggerations) if exaggerations else 0
        aiProbability = int(avg_confidence) if avg_confidence else _fallback_analysis(request.text)["aiProbability"]
        score = max(70, 100 - len(exaggerations) * 5)
        return {
            "score": score,
            "aiProbability": aiProbability,
            "suspiciousPhrases": suspicious_phrases,
            "inconsistencies": inconsistencies,
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
        candidates = await adapter.search_candidates(
            keyword=request.keyword,
            town=request.town,
            limit=request.limit,
            min_salary=request.min_salary,
            experience_years=request.experience_years,
            include_contacts=getattr(request, 'include_contacts', False)
        )
        return {"candidates": candidates}
    except Exception as e:
        print(f"Ошибка поиска: {e}")
        raise HTTPException(500, str(e))
    finally:
        await adapter.close()

@app.post("/api/calendar/create")
async def create_event(request: CalendarRequest):
    use_real_calendar = os.getenv("USE_REAL_YANDEX_CALENDAR", "false").lower() == "true"
    email = os.getenv("YANDEX_CALENDAR_EMAIL")
    app_password = os.getenv("YANDEX_CALENDAR_APP_PASSWORD")
    real_client = None
    if use_real_calendar:
        if not email or not app_password:
            raise HTTPException(500, "Yandex Calendar credentials not set")
        real_client = YandexCalendarRealClient(email, app_password)
        base_client = real_client
    else:
        base_client = MockYandexCalendarClient(fail_rate=0.0)
    queue_client = YandexCalendarQueueClient(base_client=base_client)
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
        if real_client:
            await real_client.close()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)