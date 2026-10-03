"""
🎬 Перевірка надісланих TikTok відео від друзів та генерація реакцій у стилі Боді

Запуск:
    .venv/bin/python scripts/check_tiktok_incoming_videos.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.automations.automation_2 import automation_two

async def run():
    print("🚀 Перевірка чатів TikTok на нові надіслані відео від друзів...")
    res = await automation_two.check_and_react_to_shared_videos()
    if res:
        print(f"\n🎉 Оброблено та надіслано реакцій: {len(res)}")
        for r in res:
            print(f"  👤 @{r['username']}: {r['video_url']}")
            print(f"  💬 Реакція: {r['reaction']}\n")
    else:
        print("👌 Нових непрокоментованих відео у чатах не знайдено.")

if __name__ == "__main__":
    asyncio.run(run())
