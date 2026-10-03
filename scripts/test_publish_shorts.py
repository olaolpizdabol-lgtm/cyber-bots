"""
🎬 Тестова публікація YouTube Shorts на каналі "Bohdan AI"

Запуск:
    .venv/bin/python scripts/test_publish_shorts.py
    .venv/bin/python scripts/test_publish_shorts.py --privacy public
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.publishers.youtube import youtube_publisher
from core.content_type import ContentType

def test_shorts():
    print("🚀 Тестове завантаження YouTube Shorts на канал 'Bohdan AI'...")

    privacy = "public" if "--public" in sys.argv else "unlisted"
    print(f"🔒 Режим приватності: {privacy} ({'видиме всім' if privacy == 'public' else 'доступ тільки за посиланням, безпечно для тесту'})")

    test_video = Path("data/tests/clean_test_video.mp4")
    if not test_video.exists():
        test_video = Path("data/tests/test_video.mp4")

    if not test_video.exists():
        print("❌ Не знайдено тестового відео у data/tests/")
        return

    print(f"📹 Відеофайл: {test_video} ({test_video.stat().st_size // 1024} КБ)")

    title = "AI Automation Test #shorts #ai #tech"
    desc = "Тестове відео для перевірки автоматизації каналу Bohdan AI. #shorts #automation #ai"

    metadata = {
        "youtube_title": title,
        "youtube_desc": desc,
        "privacy_status": privacy
    }

    # Підміняємо privacyStatus у publish якщо потрібно
    original_publish = youtube_publisher.publish
    
    def custom_publish(content_type, media_paths, meta):
        # Якщо в meta задано privacy_status, використовуємо його
        service = youtube_publisher._get_authenticated_service()
        if not service:
            return original_publish(content_type, media_paths, meta)
            
        from googleapiclient.http import MediaFileUpload
        body = {
            "snippet": {
                "title": meta.get("youtube_title", "Shorts Video #shorts"),
                "description": meta.get("youtube_desc", ""),
                "tags": ["shorts", "ai", "automation"],
                "categoryId": "22"
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False
            }
        }
        media = MediaFileUpload(media_paths[0], mimetype="video/mp4", resumable=True)
        request = service.videos().insert(part="snippet,status", body=body, media_body=media)
        response = request.execute()
        vid_id = response.get("id")
        from services.publishers.base import PublishResult
        return PublishResult(
            success=True,
            platform="YouTube Shorts",
            external_id=vid_id,
            url=f"https://youtube.com/shorts/{vid_id}"
        )

    res = custom_publish(ContentType.VIDEO, [str(test_video)], metadata)

    if res.success:
        print("\n" + "="*60)
        print("🎉 ВІДЕО УСПІШНО ОПУБЛІКОВАНО НА YOUTUBE SHORTS!")
        print(f"👉 Пряме посилання на відео: {res.url}")
        print(f"🆔 Video ID: {res.external_id}")
        print("="*60 + "\n")
    else:
        print(f"❌ Помилка завантаження: {res.error}")

if __name__ == "__main__":
    test_shorts()
