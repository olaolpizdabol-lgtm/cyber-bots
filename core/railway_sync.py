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
    ("FACEBOOK_STATE_B64", BASE_DIR / "data" / "facebook_state.json"),
    ("INSTAGRAM_STATE_B64", BASE_DIR / "data" / "instagram_state.json"),
]

def restore_sessions_from_env():
    """Перевіряє наявність B64 змінних і записує файли сесій на диск"""
    restored = 0
    import json
    for env_name, target_path in ENV_FILES_MAP:
        val = os.getenv(env_name)
        if val:
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                val_clean = val.strip().strip("\"'")
                # Якщо користувач вставив рядок вигляду ENV_NAME=value
                if "=" in val_clean and val_clean.split("=", 1)[0].strip() == env_name:
                    val_clean = val_clean.split("=", 1)[1].strip().strip("\"'")

                if val_clean.startswith("{") and val_clean.endswith("}"):
                    # Сирий JSON напряму
                    raw_bytes = val_clean.encode("utf-8")
                else:
                    raw_bytes = base64.b64decode(val_clean)

                if target_path.suffix == ".json":
                    decoded_text = raw_bytes.decode("utf-8")
                    json.loads(decoded_text)
                    target_path.write_text(decoded_text, encoding="utf-8")
                else:
                    target_path.write_bytes(raw_bytes)

                logger.info(f"✅ Відновлено сесію з {env_name} -> {target_path}")
                restored += 1
            except Exception as e:
                logger.error(f"❌ Помилка відновлення {env_name}: {type(e).__name__} ({e})")
    if restored > 0:
        logger.info(f"🎉 Успішно відновлено {restored} сесійних файлів у хмарі!")
