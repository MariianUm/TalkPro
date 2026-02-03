import asyncio
import os
from dotenv import load_dotenv
from gigachat.gateway import GigaChatGateway

async def test():
    load_dotenv()
    api_key = os.getenv("GIGACHAT_API_KEY")
    if not api_key:
        print("Ключ не найден")
        return
    print(f"✅ Ключ загружен, длина {len(api_key)}")

    gateway = GigaChatGateway(api_key=api_key)
    try:
        result = await gateway.analyze(
            prompt_key="find_exaggerations",
            text="Тестовое резюме. Опыт работы: 8 месяцев, должность: директор."
        )
        print("✅ Успех:", result)
    except Exception as e:
        print(f"Ошибка: {repr(e)}")
        import traceback
        traceback.print_exc()
    finally:
        await gateway.close()

if __name__ == "__main__":
    asyncio.run(test())