import aiohttp
import asyncio
import ssl  # <-- добавили импорт
from typing import Dict, Any, List, Optional
from urllib.parse import quote


class SuperJobClient:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        self.base_url = "https://api.superjob.ru/2.0"
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Создаёт или возвращает существующую сессию с заголовками авторизации"""
        if self.session is None or self.session.closed:
            # Создаём SSL-контекст с отключённой проверкой (для разработки на macOS)
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

    async def search_resumes(
        self,
        keyword: str,
        town: str = "Москва",
        count: int = 20,
        page: int = 0,
        payment_from: Optional[int] = None,
        payment_to: Optional[int] = None,
        experience: Optional[int] = None,  # 1 - без опыта, 2 - от 1 года, 3 - от 3 лет, 4 - от 6 лет
        education: Optional[int] = None,    # 2 - высшее, 3 - неполное высшее и т.д.
    ) -> List[Dict[str, Any]]:
        """
        Поиск резюме по заданным критериям.

        :param keyword: Ключевое слово (например, "Python разработчик")
        :param town: Город (название или ID)
        :param count: Количество результатов на страницу (1-100)
        :param page: Номер страницы (0-499)
        :param payment_from: Зарплата от
        :param payment_to: Зарплата до
        :param experience: Опыт работы (ID)
        :param education: Образование (ID)
        :return: Список резюме (каждое резюме — словарь)
        """
        session = await self._get_session()

        # Формируем параметры запроса
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

        try:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("objects", [])
                else:
                    error_text = await resp.text()
                    print(f"Ошибка SuperJob API (статус {resp.status}): {error_text}")
                    return []
        except asyncio.TimeoutError:
            print("Таймаут при запросе к SuperJob API")
            return []
        except Exception as e:
            print(f"Исключение при запросе к SuperJob: {e}")
            return []

    async def get_resume_by_id(self, resume_id: int) -> Optional[Dict[str, Any]]:
        """
        Получение детальной информации о конкретном резюме по ID.
        """
        session = await self._get_session()
        url = f"{self.base_url}/resumes/{resume_id}/"
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    print(f"Ошибка получения резюме {resume_id}: {resp.status}")
                    return None
        except Exception as e:
            print(f"Исключение: {e}")
            return None

    async def close(self):
        """Закрытие сессии (вызывать при завершении работы)"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def normalize_resume(self, sj_resume: Dict[str, Any]) -> Dict[str, Any]:
        """
        Приводит резюме SuperJob к единому формату, который будет использоваться в адаптере.
        """
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

        normalized = {
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
        return normalized