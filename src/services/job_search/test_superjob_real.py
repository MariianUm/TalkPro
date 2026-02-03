import asyncio
import os
from dotenv import load_dotenv
from src.job_search.job_adapter import JobSearchAdapter

load_dotenv()
secret = os.getenv("SUPERJOB_SECRET_KEY")

async def test():
    adapter = JobSearchAdapter(secret)
    candidates = await adapter.search_candidates(
        keyword="Python",
        town="Совхоз имени Ленина",
        limit=5
    )
    print(f"Найдено кандидатов: {len(candidates)}")
    for c in candidates:
        print(f"{c['title']} – {c['city']} – {c['url']}")
    await adapter.close()

if __name__ == "__main__":
    asyncio.run(test())