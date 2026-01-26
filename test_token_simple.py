import os
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()

async def test():
    token = os.getenv("YANDEX_CALENDAR_TOKEN", "")
    
    if not token:
        print("Токен не найден в .env")
        return
    
    print(f"🔍 Тестирую токен: {token[:20]}...")
    
    headers = {"Authorization": f"OAuth {token}"}
    
    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.get(
                "https://calendars.api.cloud.yandex.net/calendar/v3/calendars"
            ) as resp:
                print(f"Статус: {resp.status}")
                
                if resp.status == 200:
                    data = await resp.json()
                    print(f"Успех! Календарей: {len(data.get('calendars', []))}")
                    return True
                else:
                    error = await resp.text()
                    print(f"Ошибка: {error[:100]}")
                    return False
        except Exception as e:
            print(f"Ошибка сети: {e}")
            return False

if __name__ == "__main__":
    asyncio.run(test())