"""
🚀 Крос-постинг короткого відео на ВСІ підключені платформи:
1. YouTube Shorts (Bohdan AI)
2. Instagram Reels (@bohdan.gpt)
3. TikTok (@bohdan.gpt)
4. Telegram Channel (@bohdan_gpt)

Запуск:
    .venv/bin/python scripts/test_publish_all_shorts.py
    .venv/bin/python scripts/test_publish_all_shorts.py --public
"""
import sys
import time
import os
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.publishers.youtube import youtube_publisher
from services.publishers.instagram import instagram_publisher
from services.publishers.telegram_channel import telegram_channel_publisher
from services.publishers.tiktok import tiktok_publisher
from core.content_type import ContentType
from core.security_guard import security_guard
from config import DATA_DIR
from services.publishers.tiktok import tiktok_publisher
from core.content_type import ContentType
from core.security_guard import security_guard
from config import DATA_DIR


def cross_post_short_video():
    print("=" * 65)
    print("🚀 СТАРТ КРОС-ПОСТИНГУ КОРОТКОГО ВІДЕО НА ВСІ ПЛАТФОРМИ")
    print("=" * 65)

    test_video = Path("data/tests/clean_test_video.mp4")
    if not test_video.exists():
        test_video = Path("data/tests/test_video.mp4")

    if not test_video.exists():
        print("❌ Не знайдено відеофайлу для публікації!")
        return

    print(f"📹 Відеофайл: {test_video} ({test_video.stat().st_size // 1024} КБ)")
    is_public = "--public" in sys.argv
    yt_privacy = "public" if is_public else "unlisted"
    print(f"🔒 Приватність YouTube: {yt_privacy}")

    # Уніфіковані метадані для кожної соцмережі
    title = "AI Automation in Action 🚀 #shorts #ai #automation #tech"
    caption = (
        "AI Automation in Action 🚀\n\n"
        "Автоматичний крос-постинг короткого контенту на YouTube, Instagram та TikTok.\n\n"
        "#shorts #reels #tiktok #ai #tech #automation #chatgpt #claude"
    )

    metadata = {
        "youtube_title": title,
        "youtube_desc": caption,
        "ig_caption": caption,
        "tt_caption": caption,
        "privacy_status": yt_privacy
    }

    results = []

    # 1. 🎥 YOUTUBE SHORTS
    print("\n--- [1/3] Завантаження на YouTube Shorts (Bohdan AI) ---")
    try:
        service = youtube_publisher._get_authenticated_service()
        if service:
            from googleapiclient.http import MediaFileUpload
            body = {
                "snippet": {
                    "title": title[:95],
                    "description": caption,
                    "tags": ["shorts", "ai", "automation", "tech"],
                    "categoryId": "22"
                },
                "status": {
                    "privacyStatus": yt_privacy,
                    "selfDeclaredMadeForKids": False
                }
            }
            media = MediaFileUpload(str(test_video), mimetype="video/mp4", resumable=True)
            req = service.videos().insert(part="snippet,status", body=body, media_body=media)
            resp = req.execute()
            vid_id = resp.get("id")
            url = f"https://youtube.com/shorts/{vid_id}"
            print(f"✅ YouTube Shorts успішно опубліковано: {url}")
            results.append({"platform": "YouTube Shorts", "success": True, "url": url})
        else:
            print("⚠️ YouTube клієнт не авторизовано")
            results.append({"platform": "YouTube Shorts", "success": False, "error": "Не авторизовано"})
    except Exception as e:
        err = security_guard.sanitize_error(str(e))
        print(f"❌ Помилка YouTube: {err}")
        results.append({"platform": "YouTube Shorts", "success": False, "error": err})

    # Anti-ban Jitter
    time.sleep(random.uniform(2.5, 4.0))

    # 2. 📸 INSTAGRAM REELS
    print("\n--- [2/3] Завантаження в Instagram Reels (@bohdan.gpt) ---")
    try:
        ig_client = instagram_publisher._get_client()
        if ig_client:
            print("⏳ Завантажуємо відео у Reels через мобільне API...")
            media = ig_client.clip_upload(path=str(test_video), caption=caption)
            media_code = getattr(media, "code", str(media.pk))
            ig_url = f"https://instagram.com/p/{media_code}"
            print(f"✅ Instagram Reels успішно опубліковано: {ig_url}")
            results.append({"platform": "Instagram Reels", "success": True, "url": ig_url})
        else:
            print("⚠️ Instagram клієнт не авторизовано")
            results.append({"platform": "Instagram Reels", "success": False, "error": "Не авторизовано"})
    except Exception as e:
        err = security_guard.sanitize_error(str(e))
        print(f"❌ Помилка Instagram Reels: {err}")
        results.append({"platform": "Instagram Reels", "success": False, "error": err})

    # Anti-ban Jitter
    time.sleep(random.uniform(2.5, 4.0))

    # 3. 🎵 TIKTOK (@bohdan.gpt via Creator Studio)
    print("\n--- [3/4] Завантаження на TikTok (@bohdan.gpt) ---")
    try:
        tt_res = tiktok_publisher.publish(ContentType.VIDEO, [str(test_video)], metadata)
        if tt_res.success:
            print(f"✅ TikTok успішно опубліковано: {tt_res.url}")
            results.append({"platform": "TikTok", "success": True, "url": tt_res.url})
        else:
            print(f"⚠️ TikTok: {tt_res.error}")
            results.append({"platform": "TikTok", "success": False, "error": tt_res.error})
    except Exception as e:
        err = security_guard.sanitize_error(str(e))
        print(f"❌ Помилка TikTok: {err}")
        results.append({"platform": "TikTok", "success": False, "error": err})

    # Anti-ban Jitter
    time.sleep(random.uniform(2.5, 4.0))

    # 4. ✈️ TELEGRAM CHANNEL
    print("\n--- [4/4] Завантаження в Telegram-канал (@bohdan_gpt) ---")
    try:
        tg_res = telegram_channel_publisher.publish(ContentType.VIDEO, [str(test_video)], metadata)
        if tg_res.success:
            print(f"✅ Telegram-канал успішно опубліковано: {tg_res.url or 'Опубліковано'}")
            results.append({"platform": "Telegram Channel", "success": True, "url": tg_res.url})
        else:
            print(f"⚠️ Telegram: {tg_res.error}")
            results.append({"platform": "Telegram Channel", "success": False, "error": tg_res.error})
    except Exception as e:
        err = security_guard.sanitize_error(str(e))
        print(f"❌ Помилка Telegram: {err}")
        results.append({"platform": "Telegram Channel", "success": False, "error": err})

    # ФІНАЛЬНИЙ ЗВІТ
    print("\n" + "=" * 65)
    print("📊 ПІДСУМОК КРОС-ПОСТИНГУ:")
    print("=" * 65)
    for r in results:
        status = "✅ УСПІШНО" if r["success"] else f"❌ ПОМИЛКА: {r.get('error')}"
        link = f"-> {r.get('url')}" if r.get("url") else ""
        print(f"• {r['platform']:<18} | {status} {link}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    cross_post_short_video()
