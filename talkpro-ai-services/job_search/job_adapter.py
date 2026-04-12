import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from .superjob_client import SuperJobClient

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class JobSearchAdapter:
    def __init__(self, superjob_secret_key: str):
        """
        :param superjob_secret_key: Секретный ключ для SuperJob API
        """
        self.sj_client = SuperJobClient(superjob_secret_key)
        self._search_cache = {} 

    async def search_candidates(
        self,
        keyword: str,
        town: str = "Москва",
        limit: int = 20,
        min_salary: Optional[int] = None,
        experience_years: Optional[int] = None, 
    ) -> List[Dict[str, Any]]:
        """
        Поиск кандидатов по ключевому слову.

        :param keyword: Должность или ключевые навыки
        :param town: Город
        :param limit: Максимальное количество результатов
        :param min_salary: Минимальная зарплата (фильтр)
        :param experience_years: Минимальный опыт в годах
        :return: Список нормализованных кандидатов
        """
        cache_key = f"{keyword}_{town}_{limit}"
        if cache_key in self._search_cache:
            logger.info(f"Возвращаем кешированный результат для {keyword}")
            return self._search_cache[cache_key]

        logger.info(f"Поиск кандидатов: {keyword} в {town}")

        # Преобразуем опыт в ID SuperJob
        exp_id = self._experience_to_id(experience_years) if experience_years else None

        # Запрос к SuperJob
        resumes = await self.sj_client.search_resumes(
            keyword=keyword,
            town=town,
            count=limit,
            payment_from=min_salary,
            experience=exp_id
        )

        # Нормализуем каждое резюме
        normalized = [self._normalize_sj_resume(r) for r in resumes]

        # Кешируем на 5 минут (можно позже добавить TTL)
        self._search_cache[cache_key] = normalized
        asyncio.create_task(self._invalidate_cache_after(cache_key, 300))

        return normalized

    def _normalize_sj_resume(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Приведение резюме SuperJob к единому формату"""
        # Основные поля
        profession = raw.get("profession", "")
        payment_from = raw.get("payment_from")
        payment_to = raw.get("payment_to")
        currency = raw.get("currency", "rub")

        # Опыт работы
        exp_obj = raw.get("experience", {})
        exp_title = exp_obj.get("title") if isinstance(exp_obj, dict) else None

        # Образование
        edu_obj = raw.get("education", {})
        edu_title = edu_obj.get("title") if isinstance(edu_obj, dict) else None

        # Город
        town_obj = raw.get("town", {})
        town_title = town_obj.get("title") if isinstance(town_obj, dict) else None

        # Контакты (будут только при авторизации)
        contacts = {}
        if raw.get("contact"):
            contacts["name"] = raw["contact"]
        if raw.get("phone"):
            contacts["phone"] = raw["phone"]
        if raw.get("email"):
            contacts["email"] = raw["email"]

        return {
            "platform": "superjob",
            "id": raw.get("id"),
            "title": profession,
            "salary_from": payment_from,
            "salary_to": payment_to,
            "currency": currency,
            "experience": exp_title,
            "education": edu_title,
            "age": raw.get("age"),
            "gender": raw.get("gender", {}).get("title") if raw.get("gender") else None,
            "city": town_title,
            "skills": None,  # можно будет добавить парсинг навыков
            "contacts": contacts,
            "url": raw.get("link"),
            "raw": raw  # исходные данные на всякий случай
        }

    def _experience_to_id(self, years: int) -> Optional[int]:
        """Преобразует опыт в годах в ID SuperJob"""
        if years < 1:
            return 1   # без опыта
        elif years < 3:
            return 2   # от 1 года
        elif years < 6:
            return 3   # от 3 лет
        else:
            return 4   # от 6 лет

    async def _invalidate_cache_after(self, key: str, seconds: int):
        """Удаление ключа из кеша через заданное время"""
        await asyncio.sleep(seconds)
        if key in self._search_cache:
            del self._search_cache[key]
            logger.debug(f"Кеш {key} очищен")

    async def close(self):
        """Закрытие всех клиентов"""
        await self.sj_client.close()