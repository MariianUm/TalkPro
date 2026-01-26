from fastapi import FastAPI
from src.api.router import router
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="TalkPro Backend API",
    description="API для анализа резюме и поиска кандидатов",
    version="1.0.0"
)

app.include_router(router, prefix="/api")

@app.get("/")
def read_root():
    return {
        "message": "TalkPro Backend API",
        "endpoints": {
            "health": "/api/health",
            "analyze_resume": "/api/analyze/resume",
            "search_candidates": "/api/search/candidates",
            "calendar_event": "/api/calendar/event"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)