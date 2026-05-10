import asyncio
import os
from gigachat.gateway import GigaChatGateway

async def test_gigachat():
    api_key = os.getenv("GIGACHAT_API_KEY", "test_key")
    
    # Создаём экземпляр шлюза
    gateway = GigaChatGateway(
        api_key=api_key,
        use_redis=False,            
        max_rps=5,                  
        batch_window=0.2,             
        max_batch_size=3
    )
    
    sample_text = """
    Иван Иванов, 5 лет опыта в разработке на Python.
    Работал в компании X: разрабатывал бэкенд на Django,
    оптимизировал запросы к БД, участвовал в код-ревью.
    Знания: Python, Django, PostgreSQL, Docker.
    """
    
    print("Отправляем запрос на анализ...")
    
    # Вызываем метод analyze с ключом "check_ai"
    result = await gateway.analyze("check_ai", sample_text)
    
    print("Результат:", result)
    print("Статистика шлюза:", gateway.get_stats())
    
    # Закрываем клиент
    await gateway.close()

if __name__ == "__main__":
    asyncio.run(test_gigachat())