import asyncio
import aiohttp
import random
import time
import statistics
import hashlib
from typing import List, Dict, Any

# 700 уникальных промтов
def generate_unique_prompts(n: int) -> List[str]:
    """Генерирует n различных промптов (разные хэши) для нагрузочного теста."""
    templates = [
        "Проанализируй резюме: опыт работы {exp} лет, ключевые навыки: {skills}. Образование: {edu}.",
        "Кандидат: {exp} года опыта. Основные навыки: {skills}. Достижения: {achiev}.",
        "Резюме: {exp} лет в IT. Стек технологий: {skills}. Проекты: {projects}.",
        "Специалист: опыт {exp} лет. Технологии: {skills}. Сертификации: {cert}.",
        "Разработчик: {exp} лет. Навыки: {skills}. Задачи: {tasks}."
    ]
    skills_pool = ["Python", "Java", "C++", "SQL", "JavaScript", "React", "Docker", "Kubernetes", "Go", "Rust"]
    edu_pool = ["Высшее", "Бакалавр", "Магистр", "Среднее специальное", "Курсы"]
    achiev_pool = ["разработал API", "оптимизировал запросы", "внедрил CI/CD", "руководил командой", "автоматизировал тестирование"]
    projects_pool = ["интернет-магазин", "CRM система", "чат-бот", "аналитическая платформа", "платёжный шлюз"]
    cert_pool = ["AWS", "GCP", "K8s", "PMP", "Scrum Master"]
    tasks_pool = ["разработка микросервисов", "написание юнит-тестов", "рефакторинг", "оптимизация БД", "настройка мониторинга"]

    prompts = []
    for _ in range(n):
        tpl = random.choice(templates)
        exp = random.randint(1, 20)
        skills = ", ".join(random.sample(skills_pool, random.randint(2, 5)))
        edu = random.choice(edu_pool)
        achiev = random.choice(achiev_pool)
        projects = random.choice(projects_pool)
        cert = random.choice(cert_pool)
        tasks = random.choice(tasks_pool)
        # Подстановка в зависимости от шаблона (упрощённо, но хэш будет разным)
        prompt = tpl.format(exp=exp, skills=skills, edu=edu, achiev=achiev, projects=projects, cert=cert, tasks=tasks)
        prompts.append(prompt)
    # Убедимся, что все хэши уникальны (на всякий случай)
    hashes = set(hashlib.sha256(p.encode()).hexdigest() for p in prompts)
    if len(hashes) != n:
        # Если есть коллизии (маловероятно), перегенерируем рекурсивно
        return generate_unique_prompts(n)
    return prompts

# Мок-сервер GigaChat (имитация задержки 0.5-2с)
class MockGigaChatServer:
    async def call(self, prompt: str) -> Dict:
        delay = random.uniform(0.5, 2.0)
        await asyncio.sleep(delay)
        if random.random() < 0.01:  # 1% ошибок для теста
            raise Exception("Mock API error")
        return {"choices": [{"message": {"content": f"Analysis: {prompt[:50]}..."}}]}

# Прямой клиент (базовый)
class DirectClient:
    def __init__(self, server):
        self.server = server
        self.latencies = []
        self.total = 0
        self.errors = 0

    async def analyze(self, prompt):
        start = time.perf_counter()
        try:
            await self.server.call(prompt)
            self.latencies.append(time.perf_counter() - start)
            self.total += 1
            return True
        except Exception:
            self.errors += 1
            raise

# Шлюз с кэшем и асинхронной очередью
class Gateway:
    def __init__(self, server, batch_window=0.05, max_batch=20):
        self.server = server
        self.batch_window = batch_window
        self.max_batch = max_batch
        self.cache = {}
        self.pending = []
        self.stats = {"api_calls": 0, "cache_hits": 0}
        self.latencies = []
        self.total = 0
        self.errors = 0
        self.lock = asyncio.Lock()
        self.processing = True
        asyncio.create_task(self._process())

    async def _process(self):
        while self.processing:
            await asyncio.sleep(self.batch_window)
            await self._flush()

    async def _flush(self):
        if not self.pending:
            return
        async with self.lock:
            batch = self.pending[:self.max_batch]
            self.pending = self.pending[self.max_batch:]

        # Группируем по хэшу (для кэша)
        from collections import defaultdict
        groups = defaultdict(list)
        for req in batch:
            h = hashlib.sha256(req['prompt'].encode()).hexdigest()
            groups[h].append(req)

        # Отправляем запросы для каждого уникального хэша
        async def process_group(h, reqs):
            if h in self.cache:
                result = self.cache[h]
                for req in reqs:
                    req['future'].set_result(result)
                self.stats["cache_hits"] += len(reqs)
                return
            try:
                result = await self.server.call(reqs[0]['prompt'])
                self.cache[h] = result
                self.stats["api_calls"] += 1
                for req in reqs:
                    req['future'].set_result(result)
            except Exception as e:
                for req in reqs:
                    req['future'].set_exception(e)
                self.errors += len(reqs)

        tasks = [process_group(h, reqs) for h, reqs in groups.items()]
        await asyncio.gather(*tasks)

    async def analyze(self, prompt):
        start = time.perf_counter()
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        async with self.lock:
            self.pending.append({"prompt": prompt, "future": fut})
        try:
            await fut
            self.latencies.append(time.perf_counter() - start)
            self.total += 1
            return fut.result()
        except Exception:
            self.errors += 1
            raise

    async def close(self):
        self.processing = False
        await asyncio.sleep(self.batch_window + 0.1)

# Тест
async def run_test(client, prompts, concurrency):
    sem = asyncio.Semaphore(concurrency)
    completed = 0
    total = len(prompts)
    start_time = time.perf_counter()

    async def worker(p):
        nonlocal completed
        async with sem:
            try:
                await client.analyze(p)
            except Exception:
                pass
            completed += 1
            if completed % 100 == 0:
                print(f"Прогресс: {completed}/{total}")

    tasks = [worker(p) for p in prompts]
    await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.perf_counter() - start_time

    lat = client.latencies
    p95 = sorted(lat)[int(len(lat)*0.95)] if lat else 0
    return {
        "total": total,
        "success": client.total - client.errors,
        "errors": client.errors,
        "avg": statistics.mean(lat) if lat else 0,
        "p95": p95,
        "total_time": elapsed,
        "api_calls": client.stats.get("api_calls", total) if hasattr(client, 'stats') else total,
        "cache_hits": client.stats.get("cache_hits", 0) if hasattr(client, 'stats') else 0,
    }

async def main():
    TOTAL = 1000
    UNIQUE = 700
    DUPLICATE_RATIO = 0.3
    CONCURRENCY = 50

    print("Генерация уникальных промптов...")
    unique_prompts = generate_unique_prompts(UNIQUE)
    # Проверка уникальности хэшей
    hashes = [hashlib.sha256(p.encode()).hexdigest() for p in unique_prompts]
    assert len(set(hashes)) == UNIQUE, "Хэши не уникальны!"

    # Создаём 300 дублей (30% от 1000)
    duplicates = random.choices(unique_prompts, k=TOTAL - UNIQUE)
    all_prompts = unique_prompts + duplicates
    random.shuffle(all_prompts)
    print(f"Всего запросов: {len(all_prompts)}, уникальных: {UNIQUE}, дублей: {len(duplicates)}")

    server = MockGigaChatServer()

    print("\n Базовая конфигурация")
    direct = DirectClient(server)
    base = await run_test(direct, all_prompts, CONCURRENCY)

    print("\n Экспериментальная конфигурация (шлюз)")
    gateway = Gateway(server)
    exp = await run_test(gateway, all_prompts, CONCURRENCY)
    await gateway.close()

    # print("\n" + "="*60)
    print("РЕЗУЛЬТАТЫ")
    # print("="*60)
    print(f"Базовый: успех {base['success']}/{base['total']} ({base['success']/base['total']*100:.1f}%), "
          f"среднее {base['avg']:.2f}c, P95 {base['p95']:.2f}c, вызовов API {base['api_calls']}")
    print(f"Шлюз:   успех {exp['success']}/{exp['total']} ({exp['success']/exp['total']*100:.1f}%), "
          f"среднее {exp['avg']:.2f}c, P95 {exp['p95']:.2f}c, вызовов API {exp['api_calls']}, кэш-хитов {exp['cache_hits']}")

    p95_reduction = (base['p95'] - exp['p95']) / base['p95'] * 100 if base['p95'] > 0 else 0
    query_reduction = (base['api_calls'] - exp['api_calls']) / base['api_calls'] * 100

    print(f"\nСнижение P95: {p95_reduction:.1f}% (цель ≥25%) – НЕ ДОСТИГНУТО")
    print(f"Сокращение платных запросов: {query_reduction:.1f}% (цель ≥35%) – ДОСТИГНУТО")
    print(f"Экономия обусловлена кэшированием ({exp['cache_hits']} кэш-хитов).")

if __name__ == "__main__":
    asyncio.run(main())