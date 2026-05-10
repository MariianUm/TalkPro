import asyncio
import aiohttp
import time
import os
from dotenv import load_dotenv
import statistics

load_dotenv()

SUPERJOB_CLIENT_ID = os.getenv("SUPERJOB_CLIENT_ID")
SUPERJOB_CLIENT_SECRET = os.getenv("SUPERJOB_CLIENT_SECRET")
SUPERJOB_USERNAME = os.getenv("SUPERJOB_USERNAME")
SUPERJOB_PASSWORD = os.getenv("SUPERJOB_PASSWORD")
APP_KEY = os.getenv("SUPERJOB_SECRET_KEY")

REQUESTS = 5
KEYWORDS = ["разработчик", "аналитик", "менеджер", "тестировщик", "администратор"]

async def get_superjob_token():
    url = "https://api.superjob.ru/2.0/oauth2/password/"
    data = {
        "login": SUPERJOB_USERNAME,
        "password": SUPERJOB_PASSWORD,
        "client_id": SUPERJOB_CLIENT_ID,
        "client_secret": SUPERJOB_CLIENT_SECRET,
        "hr": 1
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data) as resp:
            if resp.status == 200:
                token_data = await resp.json()
                return token_data["access_token"]
            else:
                print("Ошибка получения токена SuperJob:", await resp.text())
                return None

async def search_resumes(token, keyword, town="Совхоз имени Ленина"):
    url = "https://api.superjob.ru/2.0/resumes/"
    headers = {
        "X-Api-App-Id": APP_KEY,
        "Authorization": f"Bearer {token}"
    }
    params = {"keyword": keyword, "town": town, "count": 5}
    start = time.perf_counter()
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as resp:
            duration = time.perf_counter() - start
            if resp.status == 200:
                data = await resp.json()
                objects = data.get("objects", [])
                return duration, len(objects) > 0
            else:
                return duration, False

async def main():
    print("Получение токена SuperJob...")
    token = await get_superjob_token()
    if not token:
        return
    print("Токен получен")

    latencies = []
    successes = 0
    for kw in KEYWORDS[:REQUESTS]:
        dur, ok = await search_resumes(token, kw)
        latencies.append(dur)
        successes += ok
        print(f"Поиск '{kw}': время {dur:.2f}с, успех {ok}")
        await asyncio.sleep(1)

    print(f"\nИТОГИ:")
    print(f"Успешность получения данных: {successes/REQUESTS*100:.1f}% (цель ≥99%)")
    print(f"Среднее время ответа: {statistics.mean(latencies):.2f}с (цель ≤15с)")
    if len(latencies) >= 20:
        print(f"P95: {statistics.quantiles(latencies, n=100)[94]:.2f}с (цель ≤25с)")
    else:
        print("P95 не вычислен (мало выборки)")

if __name__ == "__main__":
    asyncio.run(main())