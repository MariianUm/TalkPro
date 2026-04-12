import asyncio
import random
import time
import statistics
import hashlib
from typing import List, Dict, Any, Optional

# ========== Генерация промптов ==========
def generate_resume_texts(count: int) -> List[str]:
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

# ========== Мок-сервер ==========
class MockGigaChatServer:
    async def call(self, prompt: str) -> Dict:
        delay = random.uniform(0.5, 2.0)
        await asyncio.sleep(delay)
        if random.random() < 0.01:
            raise Exception("Mock error")
        return {"choices": [{"message": {"content": f"Analysis: {prompt[:30]}..."}}]}

# ========== Прямой клиент (базовый) ==========
class DirectClient:
    def __init__(self, server):
        self.server = server
        self.latencies = []
        self.total = 0
        self.errors = 0

    async def analyze(self, prompt):
        start = time.time()
        try:
            await self.server.call(prompt)
            self.latencies.append(time.time() - start)
            self.total += 1
        except Exception:
            self.errors += 1
            raise

# ========== Шлюз с кэшем и батчингом (экспериментальный) ==========
class Gateway:
    def __init__(self, server, batch_window=0.1, max_batch=10):
        self.server = server
        self.batch_window = batch_window
        self.max_batch = max_batch
        self.cache = {}
        self.pending = []
        self.stats = {"api_calls": 0, "cache_hits": 0}
        self.latencies = []
        self.total = 0
        self.errors = 0
        self.processing = True
        self.lock = asyncio.Lock()
        asyncio.create_task(self._process())

    async def _process(self):
        while self.processing:
            await asyncio.sleep(self.batch_window)
            await self._flush()

    async def _flush(self):
        if not self.pending:
            return
        # Блокируем на время обработки, чтобы избежать гонок
        async with self.lock:
            batch = self.pending[:self.max_batch]
            self.pending = self.pending[self.max_batch:]

        # Обрабатываем батч
        tasks = []
        for req in batch:
            h = hashlib.sha256(req['prompt'].encode()).hexdigest()
            if h in self.cache:
                req['future'].set_result(self.cache[h])
                self.stats["cache_hits"] += 1
            else:
                tasks.append((req, h))

        # Отправляем уникальные запросы
        for req, h in tasks:
            try:
                result = await self.server.call(req['prompt'])
                self.cache[h] = result
                req['future'].set_result(result)
                self.stats["api_calls"] += 1
            except Exception as e:
                req['future'].set_exception(e)
                self.errors += 1

    async def analyze(self, prompt):
        start = time.time()
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        async with self.lock:
            self.pending.append({"prompt": prompt, "future": fut})
        try:
            await fut
            self.latencies.append(time.time() - start)
            self.total += 1
            return fut.result()
        except Exception:
            self.errors += 1
            raise

    async def close(self):
        self.processing = False
        # Ждём окончания текущего батча
        await asyncio.sleep(self.batch_window + 0.1)

# ========== Запуск теста с прогрессом ==========
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
            if completed % 100 == 0:
                print(f"Прогресс: {completed}/{total} запросов")

    tasks = [worker(p) for p in prompts]
    await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.time() - start_time

    # Собираем метрики
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
    TOTAL = 100          # уменьшаем для теста
    UNIQUE = 70
    CONCURRENCY = 20

    unique = generate_resume_texts(UNIQUE)
    dups = random.choices(unique, k=TOTAL - UNIQUE)
    prompts = unique + dups
    random.shuffle(prompts)
    print(f"Всего запросов: {TOTAL}, уникальных: {UNIQUE}, дублей: {TOTAL-UNIQUE}")

    server = MockGigaChatServer()

    # Базовая
    print("\n--- Базовая конфигурация (прямые вызовы) ---")
    direct = DirectClient(server)
    base = await run_test(direct, prompts, CONCURRENCY)

    # Шлюз
    print("\n--- Экспериментальная конфигурация (шлюз) ---")
    gateway = Gateway(server)
    exp = await run_test(gateway, prompts, CONCURRENCY)
    await gateway.close()

    # Вывод
    print("\n" + "="*60)
    print("РЕЗУЛЬТАТЫ")
    print("="*60)
    print(f"Базовый: успех {base['success']}/{base['total']} ({base['success']/base['total']*100:.1f}%), "
          f"среднее {base['avg']:.2f}c, P95 {base['p95']:.2f}c, вызовов API {base['api_calls']}")
    print(f"Шлюз:   успех {exp['success']}/{exp['total']} ({exp['success']/exp['total']*100:.1f}%), "
          f"среднее {exp['avg']:.2f}c, P95 {exp['p95']:.2f}c, вызовов API {exp['api_calls']}, кэш-хитов {exp['cache_hits']}")

    p95_reduction = (base['p95'] - exp['p95']) / base['p95'] * 100 if base['p95'] > 0 else 0
    query_reduction = (base['api_calls'] - exp['api_calls']) / base['api_calls'] * 100

    print(f"\nСнижение P95: {p95_reduction:.1f}% (цель ≥25%)")
    print(f"Сокращение платных запросов: {query_reduction:.1f}% (цель ≥35%)")

if __name__ == "__main__":
    asyncio.run(main())