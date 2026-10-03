import os
from pathlib import Path
from dotenv import load_dotenv

# Завантажуємо змінні оточення
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# Папки проекту
DOWNLOADS_DIR = BASE_DIR / "downloads"
CREDENTIALS_DIR = BASE_DIR / "credentials"
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = BASE_DIR / "temp"

for folder in (DOWNLOADS_DIR, CREDENTIALS_DIR, DATA_DIR, TEMP_DIR):
    folder.mkdir(parents=True, exist_ok=True)

# ==========================================
# 🤖 БОТ 1: КАНАЛ АВТОМАТИЗАЦІЯ (Публікації, TikTok вогники, аналітика)
# ==========================================
CHANNEL_AUTOMATION_BOT_TOKEN = (
    os.getenv("CHANNEL_AUTOMATION_BOT_TOKEN", "").strip()
    or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
)
TELEGRAM_BOT_TOKEN = CHANNEL_AUTOMATION_BOT_TOKEN  # Зворотна сумісність

ALLOWED_USER_IDS_RAW = os.getenv("ALLOWED_TELEGRAM_USER_IDS", "").strip()
ALLOWED_USER_IDS = [
    int(uid.strip())
    for uid in ALLOWED_USER_IDS_RAW.split(",")
    if uid.strip().isdigit()
]
TELEGRAM_TARGET_CHANNEL_ID = os.getenv("TELEGRAM_TARGET_CHANNEL_ID", "").strip()

# Google Gemini AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
_gemini_keys_raw = os.getenv("GEMINI_API_KEYS", "").strip()
if _gemini_keys_raw:
    GEMINI_API_KEYS = [k.strip() for k in _gemini_keys_raw.split(",") if k.strip()]
elif GEMINI_API_KEY:
    GEMINI_API_KEYS = [GEMINI_API_KEY]
else:
    GEMINI_API_KEYS = []

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()
DEFAULT_AI_PROMPT = os.getenv(
    "DEFAULT_AI_PROMPT",
    "Проаналізуй контент та оптимізуй опис під пошукові запити (Social SEO 2026) для TikTok Search, Instagram Explore, YouTube Search, Pinterest та Google. "
    "1. Визнач головний пошуковий запит (Primary Search Keyword), який користувачі вбивають у пошук. "
    "2. Органічно інтегруй його у перші 1-2 рядки опису для закріплення у пошуковому рядку TikTok та Instagram. "
    "3. Додай 3-5 LSI-ключових слів та синонімів у тіло тексту без переспаму. "
    "4. Поєднай пошуковий намір (Search Intent) із вірусним гачком (Hook) та закликом до дії (CTA). "
    "5. Підбери релевантні нішеві SEO-хештеги (пошукові кластери)."
).strip()

# US / New York Proxy
US_NY_PROXY_URL = os.getenv("US_NY_PROXY_URL", "").strip()

# YouTube Settings
YOUTUBE_CLIENT_SECRETS_FILE = os.getenv(
    "YOUTUBE_CLIENT_SECRETS_FILE",
    str(CREDENTIALS_DIR / "youtube_client_secrets.json")
)
YOUTUBE_TOKEN_FILE = os.getenv(
    "YOUTUBE_TOKEN_FILE",
    str(CREDENTIALS_DIR / "youtube_token.json")
)

# Instagram Settings
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME", "").strip()
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD", "").strip()
INSTAGRAM_SESSION_FILE = os.getenv(
    "INSTAGRAM_SESSION_FILE",
    str(CREDENTIALS_DIR / "instagram_session.json")
)

# TikTok Settings (Розділені канали: Залив відео vs Вогники)
# 🎬 Канал 1: Відео та контент (куди заливаються відео)
TIKTOK_UPLOAD_SESSION_ID = (
    os.getenv("TIKTOK_UPLOAD_SESSION_ID", "").strip()
    or os.getenv("TIKTOK_SESSION_ID", "").strip()
)
TIKTOK_SESSION_ID = TIKTOK_UPLOAD_SESSION_ID  # Зворотна сумісність

# 🔥 Канал 2: Особистий акаунт для вогників (TikTok Streaks & Сердечка)
TIKTOK_STREAKS_SESSION_ID = (
    os.getenv("TIKTOK_STREAKS_SESSION_ID", "").strip()
    or os.getenv("TIKTOK_PERSONAL_SESSION_ID", "").strip()
)
TIKTOK_STREAKS_ACCOUNT_NAME = os.getenv("TIKTOK_STREAKS_ACCOUNT_NAME", "Особистий акаунт").strip()
TIKTOK_STREAKS_ENABLED = os.getenv("TIKTOK_STREAKS_ENABLED", "true").lower() in ("true", "1", "yes")
TIKTOK_GIRLFRIEND_USERNAME = os.getenv("TIKTOK_GIRLFRIEND_USERNAME", "").strip().lstrip("@")
TIKTOK_STREAK_SCHEDULE_TIME = os.getenv("TIKTOK_STREAK_SCHEDULE_TIME", "10:00").strip()

# Groq API & "Кібер Рижий" Settings
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
_groq_keys_raw = os.getenv("GROQ_API_KEYS", "").strip()
if _groq_keys_raw:
    GROQ_API_KEYS = [k.strip() for k in _groq_keys_raw.split(",") if k.strip()]
elif GROQ_API_KEY:
    GROQ_API_KEYS = [GROQ_API_KEY]
else:
    GROQ_API_KEYS = []

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
CYBER_RIZHYI_ENABLED = os.getenv("CYBER_RIZHYI_ENABLED", "true").lower() in ("true", "1", "yes")
CYBER_RIZHYI_RESPOND_ALL_GROUP_MSGS = os.getenv("CYBER_RIZHYI_RESPOND_ALL_GROUP_MSGS", "true").lower() in ("true", "1", "yes")
CYBER_RIZHYI_BOT_TOKEN = os.getenv("CYBER_RIZHYI_BOT_TOKEN", "").strip()
CYBER_TURIKOV_BOT_TOKEN = os.getenv("CYBER_TURIKOV_BOT_TOKEN", "").strip()

# Anti-Detection & Safeguards
ANTI_DETECTION_CLEANING = os.getenv("ANTI_DETECTION_CLEANING", "true").lower() in ("true", "1", "yes")
STRICT_PROXY_CHECK = os.getenv("STRICT_PROXY_CHECK", "true").lower() in ("true", "1", "yes")
DRY_RUN_MODE = os.getenv("DRY_RUN_MODE", "false").lower() in ("true", "1", "yes")

# Database Path
DB_PATH = DATA_DIR / "automations.db"


def is_user_allowed(user_id: int) -> bool:
    """Перевірка чи користувач має доступ до бота"""
    if not ALLOWED_USER_IDS:
        return True  # Якщо список пустий - дозволено всім (рекомендується вказати свій ID)
    return user_id in ALLOWED_USER_IDS
