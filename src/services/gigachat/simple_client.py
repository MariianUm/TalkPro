import os
import httpx
from typing import Optional

class SimpleGigaChatClient:
    def __init__(self):
        # Получаем API ключ из переменных окружения
        self.api_key = os.getenv("GIGACHAT_API_KEY", "test_key")
        self.base_url = "https://gigachat.devices.sberbank.ru/api/v1"
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def analyze_text(self, text: str, prompt_template: str) -> Optional[dict]:
        """Простой запрос к GigaChat без кэширования"""
        try:
            prompt = prompt_template.format(text=text)
            if self.api_key == "test_key":
                print("Используется тестовый ключ, возвращаем заглушку")
                return {
                    "choices": [{
                        "message": {
                            "content": "85"  # Заглушка для проверки AI
                        }
                    }]
                }
            
            # Реальный запрос к API
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "GigaChat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Ошибка GigaChat: {e}")
            return None
    
    async def close(self):
        await self.client.aclose()