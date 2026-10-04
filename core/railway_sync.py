"""
🔄 Автоматичне відновлення сесійних файлів з оточення Railway
Працює при старті контейнера в хмарі
"""
import os
import base64
import logging
from pathlib import Path
from config import BASE_DIR, DATA_DIR, CREDENTIALS_DIR

logger = logging.getLogger("railway_sync")

ENV_FILES_MAP = [
    ("YOUTUBE_TOKEN_B64", BASE_DIR / "credentials" / "youtube_token.json"),
    ("YOUTUBE_SECRETS_B64", BASE_DIR / "credentials" / "youtube_client_secrets.json"),
    ("INSTAGRAM_SESSION_B64", BASE_DIR / "credentials" / "instagram_session.json"),
    ("TIKTOK_CHANNEL_STATE_B64", BASE_DIR / "data" / "tiktok_channel_state.json"),
    ("TIKTOK_STATE_B64", BASE_DIR / "data" / "tiktok_state.json"),
    ("SNAPCHAT_STATE_B64", BASE_DIR / "data" / "snapchat_state.json"),
]

def restore_sessions_from_env():
    """Перевіряє наявність B64 змінних і записує файли сесій на диск"""
    restored = 0
    for env_name, target_path in ENV_FILES_MAP:
        val = os.getenv(env_name)
        if val:
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                raw_bytes = base64.b64decode(val.strip())
                target_path.write_bytes(raw_bytes)
                logger.info(f"✅ Відновлено сесію з {env_name} -> {target_path}")
                restored += 1
            except Exception as e:
                logger.error(f"❌ Помилка відновлення {env_name}: {e}")
    if restored > 0:
        logger.info(f"🎉 Успішно відновлено {restored} сесійних файлів у хмарі!")
