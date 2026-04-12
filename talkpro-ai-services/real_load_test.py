import asyncio
import random
import time
import statistics
import os
from dotenv import load_dotenv

# Импортируем ваш шлюз
from gigachat.gateway import GigaChatGateway

# Загружаем ключ из .env
load_dotenv()
API_KEY = os.getenv("GIGACHAT_API_KEY")
if not API_KEY:
    raise ValueError("Не задан GIGACHAT_API_KEY")

# ========== 1. Простой клиент для базовой конфигурации (прямые вызовы без оптимизаций) ==========
class DirectGigaChatClient:
    """Клиент, который напрямую вызывает GigaChat API, используя ту же логику получения токена, что и шлюз."""
    def __init__(self, api_key):
        self.api_key = api_key
        self.latencies = []
        self.total = 0
        self.errors = 0
        self._access_token = None
        self._token_expires = 0

    async def _get_access_token(self):
        """Копия метода из GigaChatGateway для получения токена (без кэша)"""
        import time
        import base64
        import httpx
        import uuid

        if self._access_token and time.time() < self._token_expires:
            return self._access_token

        auth = base64.b64encode(f"{self.api_key}:".encode()).decode()
        rquid = str(uuid.uuid4())
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
            "RqUID": rquid,
        }
        data = {"scope": "GIGACHAT_API_PERS"}

        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                headers=headers,
                data=data,
            )
            resp.raise_for_status()
            token_data = resp.json()
            self._access_token = token_data["access_token"]
            self._token_expires = token_data["expires_at"] / 1000  # в секундах
            return self._access_token

    async def analyze(self, prompt):
        import httpx
        start = time.time()
        try:
            token = await self._get_access_token()
            async with httpx.AsyncClient(verify=False) as client:
                resp = await client.post(
                    "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "GigaChat",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.7,
                    },
                    timeout=30.0,
                )
                resp.raise_for_status()
                _ = resp.json()
            latency = time.time() - start
            self.latencies.append(latency)
            self.total += 1
        except Exception as e:
            self.errors += 1
            raise

# ========== 2. Генерация промптов ==========
def generate_resume_texts(count):
    templates = [
        "Кандидат {} лет, опыт {} лет. Навыки: Python, SQL.",
        "Специалист по анализу данных, стаж {} года. Python, Pandas.",
        "Разработчик на Java, опыт {} лет. Spring, Hibernate.",
        "Frontend-разработчик, {} лет опыта. React, TypeScript.",
    ]
    texts = []
    for i in range(count):
        tpl = random.choice(templates)
        age = random.randint(22, 50)
        exp = random.randint(1, 15)
        texts.append(tpl.format(age, exp))
    return texts

# ========== 3. Запуск теста ==========
async def run_test(client, prompts, concurrency):
    sem = asyncio.Semaphore(concurrency)
    completed = 0
    total = len(prompts)
    start_time = time.time()

    async def worker(p):
        nonlocal completed
        async with sem:
            try:
                await client.analyze(p)
            except Exception:
                pass
            completed += 1
            if completed % 5 == 0 or completed == total:
                print(f"  Прогресс: {completed}/{total} запросов")

    tasks = [worker(p) for p in prompts]
    await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.time() - start_time

    lat = client.latencies
    p95 = sorted(lat)[int(len(lat) * 0.95)] if lat else 0
    return {
        "total": total,
        "success": client.total - client.errors,
        "errors": client.errors,
        "avg": statistics.mean(lat) if lat else 0,
        "p95": p95,
        "total_time": elapsed,
    }

async def main():
    TOTAL = 20            # общее количество запросов
    UNIQUE = 14           # уникальных (остальные 6 – дубли)
    CONCURRENCY = 5       # ограничим параллелизм, чтобы не перегружать API

    # Генерируем промпты
    unique_prompts = generate_resume_texts(UNIQUE)
    dup_prompts = random.choices(unique_prompts, k=TOTAL - UNIQUE)
    all_prompts = unique_prompts + dup_prompts
    random.shuffle(all_prompts)

    print(f"Всего запросов: {TOTAL}, уникальных: {UNIQUE}, дублей: {TOTAL-UNIQUE}")
    print(f"Параллелизм: {CONCURRENCY}")

    # Базовый клиент (прямые вызовы)
    print("\n--- Базовая конфигурация (прямые вызовы) ---")
    base_client = DirectGigaChatClient(API_KEY)
    base_metrics = await run_test(base_client, all_prompts, CONCURRENCY)

    # Шлюз (с кэшем и батчингом)
    print("\n--- Экспериментальная конфигурация (шлюз) ---")
    gateway = GigaChatGateway(api_key=API_KEY, max_rps=10, batch_window=0.1, max_batch_size=10)
    # Обёртка для единообразия
    class GatewayWrapper:
        def __init__(self, g):
            self.g = g
            self.latencies = []
            self.total = 0
            self.errors = 0
        async def analyze(self, prompt):
            start = time.time()
            try:
                await self.g.analyze(prompt_key="find_exaggerations", text=prompt)
                self.latencies.append(time.time() - start)
                self.total += 1
            except Exception:
                self.errors += 1
                raise

    wrapper = GatewayWrapper(gateway)
    exp_metrics = await run_test(wrapper, all_prompts, CONCURRENCY)
    await gateway.close()

    # Получаем статистику шлюза
    stats = gateway.get_stats()

    # Вывод результатов
    print("\n" + "="*60)
    print("РЕЗУЛЬТАТЫ РЕАЛЬНОГО ТЕСТА GigaChat")
    print("="*60)
    print(f"Базовый: успех {base_metrics['success']}/{base_metrics['total']} ({base_metrics['success']/base_metrics['total']*100:.1f}%), "
          f"среднее {base_metrics['avg']:.2f}c, P95 {base_metrics['p95']:.2f}c")
    print(f"Шлюз:   успех {exp_metrics['success']}/{exp_metrics['total']} ({exp_metrics['success']/exp_metrics['total']*100:.1f}%), "
          f"среднее {exp_metrics['avg']:.2f}c, P95 {exp_metrics['p95']:.2f}c")
    print(f"Статистика шлюза: вызовов API {stats['api_calls']}, кэш-хитов {stats['cache_hits']}")

    p95_reduction = (base_metrics['p95'] - exp_metrics['p95']) / base_metrics['p95'] * 100 if base_metrics['p95'] else 0
    query_reduction = (base_metrics['total'] - stats['api_calls']) / base_metrics['total'] * 100 if base_metrics['total'] else 0

    print(f"\nСнижение P95: {p95_reduction:.1f}% (цель ≥25%)")
    print(f"Сокращение платных запросов: {query_reduction:.1f}% (цель ≥35%)")

if __name__ == "__main__":
    asyncio.run(main())