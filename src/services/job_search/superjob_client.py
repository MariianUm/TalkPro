import aiohttp
import asyncio
import ssl
import time
from typing import Dict, Any, List, Optional

class RateLimiter:
    def __init__(self, max_calls: int, interval: float):
        self.max_calls = max_calls
        self.interval = interval
        self.calls = []
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            now = time.time()
            self.calls = [t for t in self.calls if now - t < self.interval]
            if len(self.calls) >= self.max_calls:
                sleep_time = self.interval - (now - self.calls[0])
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                now = time.time()
                self.calls = [t for t in self.calls if now - t < self.interval]
            self.calls.append(now)

class SuperJobClient:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        self.base_url = "https://api.superjob.ru/2.0"
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limiter = RateLimiter(max_calls=120, interval=60.0)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self.session = aiohttp.ClientSession(
                connector=connector,
                headers={
                    "X-Api-App-Id": self.secret_key,
                    "Content-Type": "application/json"
                },
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self.session

    async def _request(self, method: str, url: str, **kwargs) -> Optional[Dict]:
        await self.rate_limiter.acquire()
        session = await self._get_session()
        try:
            async with session.request(method, url, **kwargs) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    error_text = await resp.text()
                    print(f"SuperJob API error {resp.status}: {error_text}")
                    return None
        except asyncio.TimeoutError:
            print("Timeout error")
            return None
        except Exception as e:
            print(f"Exception: {e}")
            return None

    async def search_resumes(
        self,
        keyword: str,
        town: str = "Москва",
        count: int = 20,
        page: int = 0,
        payment_from: Optional[int] = None,
        payment_to: Optional[int] = None,
        experience: Optional[int] = None,
        education: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        params = {
            "keyword": keyword,
            "town": town,
            "count": min(count, 100),
            "page": page,
        }
        if payment_from is not None:
            params["payment_from"] = payment_from
        if payment_to is not None:
            params["payment_to"] = payment_to
        if experience is not None:
            params["experience"] = experience
        if education is not None:
            params["education"] = education

        url = f"{self.base_url}/resumes/"
        data = await self._request("GET", url, params=params)
        if data:
            return data.get("objects", [])
        return []

    async def get_resume_contacts(self, resume_id: int) -> Dict[str, Any]:
        """Получение контактов резюме (требует авторизации и оплаты)."""
        url = f"{self.base_url}/resumes/{resume_id}/"
        # Контакты придут только если у вас есть права
        data = await self._request("GET", url)
        if data:
            # Извлекаем контакты из полей
            contacts = {}
            if data.get("phone1"):
                contacts["phone"] = data.get("phone1")
            if data.get("email"):
                contacts["email"] = data.get("email")
            if data.get("firstname") and data.get("lastname"):
                contacts["name"] = f"{data.get('firstname')} {data.get('lastname')}"
            return contacts
        return {}

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def normalize_resume(self, sj_resume: Dict[str, Any]) -> Dict[str, Any]:
        # Оставляем существующую логику
        town = sj_resume.get("town", {})
        town_title = town.get("title") if isinstance(town, dict) else None
        exp = sj_resume.get("experience", {})
        experience_title = exp.get("title") if isinstance(exp, dict) else None
        edu = sj_resume.get("education", {})
        education_title = edu.get("title") if isinstance(edu, dict) else None
        contacts = {}
        if "contact" in sj_resume:
            contacts["name"] = sj_resume.get("contact")
        if "phone" in sj_resume:
            contacts["phone"] = sj_resume.get("phone")
        if "email" in sj_resume:
            contacts["email"] = sj_resume.get("email")
        return {
            "platform": "superjob",
            "id": sj_resume.get("id"),
            "title": sj_resume.get("profession"),
            "salary_from": sj_resume.get("payment_from"),
            "salary_to": sj_resume.get("payment_to"),
            "currency": sj_resume.get("currency", "rub"),
            "experience": experience_title,
            "education": education_title,
            "age": sj_resume.get("age"),
            "gender": sj_resume.get("gender", {}).get("title") if sj_resume.get("gender") else None,
            "city": town_title,
            "languages": sj_resume.get("languages", []),
            "skills": None,
            "contacts": contacts,
            "url": sj_resume.get("link"),
            "raw_data": sj_resume
        }