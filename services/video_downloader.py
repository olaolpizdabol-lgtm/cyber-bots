"""
🌐 Універсальний завантажувач відео за посиланнями
Підтримує Google Drive, Dropbox, прямі посилання на MP4, YouTube, Instagram Reels тощо (до 500 МБ)
повністю оминаючи будь-які ліміти Telegram Bot API!
"""
import os
import sys
import logging
import subprocess
from pathlib import Path
from typing import Optional
from config import DOWNLOADS_DIR

logger = logging.getLogger("video_downloader")
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)


def is_video_url(text: str) -> bool:
    """Визначає чи містить текст посилання на відеофайл або хмару"""
    t = text.lower().strip()
    if not (t.startswith("http://") or t.startswith("https://")):
        return False
    if any(ext in t for ext in [".mp4", ".mov", ".mkv", ".webm", ".avi"]):
        return True
    if any(dom in t for dom in ["drive.google.com", "dropbox.com", "youtube.com", "youtu.be", "vimeo.com", "instagram.com/reel"]):
        return True
    return False


def download_video_from_url(url: str) -> Optional[str]:
    """Завантажує відео за посиланням через yt-dlp у папку downloads/"""
    clean_url = url.strip()
    out_tmpl = str(DOWNLOADS_DIR / "url_%(epoch)s_%(id)s.%(ext)s")

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--no-playlist",
        "-f", "b[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
        "-o", out_tmpl,
        "--max-filesize", "500M",
        clean_url
    ]

    try:
        logger.info(f"Завантажуємо відео за посиланням: {clean_url}")
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
        
        # Шукаємо завантажений файл
        matched = sorted(DOWNLOADS_DIR.glob("url_*.*"), key=os.path.getmtime, reverse=True)
        for f in matched:
            if f.suffix.lower() in [".mp4", ".mov", ".mkv", ".webm"]:
                logger.info(f"✅ Відео успішно завантажено за посиланням: {f}")
                return str(f)
    except Exception as e:
        logger.error(f"Помилка завантаження за посиланням: {e}")

    return None
