"""
📦 Експорт усіх сесій та налаштувань для Railway Variables
Генерує готові значення для вставки у Railway Dashboard -> Variables

Запуск:
    .venv/bin/python scripts/export_railway_env.py
"""
import os
import sys
import base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BASE_DIR, DATA_DIR, CREDENTIALS_DIR

FILES_TO_EXPORT = [
    ("credentials/youtube_token.json", "YOUTUBE_TOKEN_B64"),
    ("credentials/youtube_client_secrets.json", "YOUTUBE_SECRETS_B64"),
    ("credentials/instagram_session.json", "INSTAGRAM_SESSION_B64"),
    ("data/tiktok_channel_state.json", "TIKTOK_CHANNEL_STATE_B64"),
    ("data/tiktok_state.json", "TIKTOK_STATE_B64"),
]

def main():
    print("=" * 65)
    print("🚀 ЗМІННІ ДЛЯ ВСТАВКИ У RAILWAY DASHBOARD -> VARIABLES:")
    print("=" * 65)
    print("\n# Скопіюйте ці значення і додайте у Railway Variables:\n")

    for rel_path, env_name in FILES_TO_EXPORT:
        full_path = BASE_DIR / rel_path
        if full_path.exists():
            content = full_path.read_bytes()
            b64_str = base64.b64encode(content).decode("utf-8")
            print(f"{env_name}={b64_str}\n")
        else:
            print(f"# ⚠️ {rel_path} не знайдено локально")

    print("=" * 65)
    print("✅ Коли ці змінні додані в Railway, бот на сервері автоматично")
    print("   відновить усі сесії YouTube, Instagram та TikTok при старті!")
    print("=" * 65)

if __name__ == "__main__":
    main()
