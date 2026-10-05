"""
🔥 АВТОМАТИЗАЦІЯ #2: TikTok Вогники (Streaks) & Сердечка для Дівчини (2026)

Функціонал:
1. Щоденне автоматичне підтримання вогників (TikTok Streaks) мінімум раз на день.
2. Спеціальний романтичний режим для дівчини: надсилання теплих, ніжних повідомлень
   із різноманітними сердечками (❤️, 🥰, 💖, 💕, 💓, 💞), компліментами та побажаннями.
3. Дружні streak-нагадування для решти контактів із вогниками (🔥).
4. ШІ-генерація через Gemini AI (повідомлення ніколи не повторюються) + надійна офлайн-бібліотека.
5. Захист від тіньового бану: маршрутизація через US/NY проксі, рандомізований часовий jitter.
6. Безпечний режим очікування ключів (Mock / Dry-Run), що дозволяє протестувати весь цикл
   у Telegram-боті ще до внесення реальних cookies.
"""
import logging
import random
import time
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

import json
from config import (
    TIKTOK_STREAKS_SESSION_ID,
    TIKTOK_STREAKS_ACCOUNT_NAME,
    TIKTOK_STREAKS_ENABLED,
    TIKTOK_GIRLFRIEND_USERNAME,
    TIKTOK_STREAK_SCHEDULE_TIME,
    DRY_RUN_MODE,
    CHANNEL_AUTOMATION_BOT_TOKEN,
    TELEGRAM_BOT_TOKEN,
    ALLOWED_USER_IDS,
    DATA_DIR
)
from core.database import (
    get_setting,
    set_setting,
    get_streak_targets,
    get_streak_target_by_username,
    get_girlfriend_target,
    set_girlfriend_target,
    add_streak_target,
    remove_streak_target,
    update_streak_target_sent,
    save_streak_log,
    get_recent_streak_logs,
    get_streak_stats
)
from core.security_guard import security_guard
from services.gemini_ai import gemini_service, sanitize_typography
from services.proxy_manager import proxy_manager

logger = logging.getLogger(__name__)

# Розширені романтичні шаблони для дівчини з урахуванням часу доби
# Живі, автентичні романтичні повідомлення для дівчини (як пишуть справжні люди в чатах, без ШІ-кліше)
GIRLFRIEND_HEART_TEMPLATES: List[str] = [
    "Доброго ранку, моє сонечко! ❤️ Нехай день буде чудовим і легким! Люблю тебе безмежно 🥰💖",
    "Ти моє найбільше щастя і натхнення! 💕 Сяй сьогодні та посміхайся, цьомаю міцно! ✨❤️",
    "Просто хотів нагадати, що ти в мене найрідніша і найгарніша у світі! 💖🥰 Тримаємо наш вогник! 🔥❤️",
    "Люблю тебе з кожним днем все сильніше! 💓 Мільйон обіймів і сердечок тобі: ❤️💕💖🥰",
    "Ти мій найулюбленіший вогник у житті 🔥❤️ Бажаю тобі найкращого та найзатишнішого дня! 🥰🌸",
    "Навіть коли багато справ, завжди думаю про тебе! 💘 Гарного настрою, моє кохання! ❤️✨",
    "Цьом у щічку! 🥰 Нехай сьогодні все вдається легко! Обіймаю міцно-міцно! 💖💓❤️",
    "Ти робиш кожен мій день особливим! 💕 Дякую, що ти є в мене! Люблю сильно! ❤️🥰🔥",
    "Посилаю тобі промінчик тепла і купу сердечок! 🌸💖 Ти найкраща дівчина у всесвіті! ❤️✨",
    "Мій вогник палає тільки для тебе! 🔥❤️ Усміхнися, кохана, ти неймовірна! 🥰💕"
]

GIRLFRIEND_TIME_TEMPLATES: Dict[str, List[str]] = {
    "morning": [
        "Доброго ранку, моє найдорожче сонечко! ☀️❤️ Нехай твій день буде легким, радісним і сповненим посмішок! Цьомаю міцно! 🥰💖✨",
        "Прокидайся, красуне! 🌸 Ти перша, про кого я подумав зранку! Посилаю море ніжності та сердечок: ❤️💕💖🥰",
        "Чудового ранку, моє кохання! ☕️❤️ Нехай кожен момент сьогодні тішить тебе! Тримаємо наш вогник! 🔥❤️✨"
    ],
    "afternoon": [
        "Як твій день, моє щастя? 🌸 Сподіваюся, все вдається легко! Люблю тебе дуже сильно і сумую! 🥰💖❤️",
        "Просто тепле нагадування посеред дня: ти найкраща і найрідніша дівчина у світі! 💕✨ Обіймаю міцно! ❤️🥰",
        "Сил тобі та чудового настрою на залишок дня, кохана! 💘 Посилаю мільйон поцілунків! 💖💓❤️"
    ],
    "evening": [
        "Затишного і теплого вечора, моє сонечко! ✨❤️ Відпочивай, ти сьогодні велика розумничка! Люблю безмежно! 🥰💖",
        "Хай вечір принесе тобі спокій та тепло! 🌸💕 Дуже хочу тебе обійняти прямо зараз! Цьом! ❤️🥰✨",
        "Затишку тобі, моя найгарніша! 🕯❤️ Дякую за те, що ти робиш кожен мій день світлішим! 💖💓"
    ],
    "night": [
        "Солодких і казкових снів, моя радість! 🌙❤️ Нехай тобі насниться щось дуже приємне! Обіймаю ніжно-ніжно! 🥰💖✨",
        "Добраніч, моє найдорожче серденько! 🌟💕 Спи солодко, я завжди поруч у думках! Люблю сильно! ❤️🥰"
    ]
}

# Шаблони для звичайних вогників із друзями
FRIEND_STREAK_TEMPLATES: List[str] = [
    "🔥 Тримаємо вогник! Гарного та продуктивного дня!",
    "🔥 Щоденний streak чек! Як твої справи? ✌️",
    "🔥 +1 день у нашу серію вогників! Не пропускай 😎",
    "🔥 Вогник збережено! Бажаю крутого настрою сьогодні! 💪",
    "Streak on fire! 🔥🔥 Відповідай, щоб наш вогник не згас!",
    "🔥 Вогник у скарбничку! Тримаємо темп 🚀"
]


class TikTokStreakService:
    def __init__(self):
        self.enabled = TIKTOK_STREAKS_ENABLED
        self._ensure_girlfriend_initialized()

    def _ensure_girlfriend_initialized(self):
        """Ініціалізує акаунт дівчини з .env якщо він ще не в БД або якщо змінився"""
        if TIKTOK_GIRLFRIEND_USERNAME:
            clean_gf = TIKTOK_GIRLFRIEND_USERNAME.strip().lstrip("@")
            current_gf = get_girlfriend_target()
            if not current_gf or current_gf.get("username", "").lower() != clean_gf.lower():
                logger.info(f"Синхронізація акаунта дівчини з .env: @{clean_gf}")
                set_girlfriend_target(clean_gf, "Кохана")

    def _get_time_of_day_context(self) -> Tuple[str, str]:
        """Визначає поточний час доби для контекстного привітання"""
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "morning", "ранок (побажай доброго ранку, сонячного дня)"
        elif 12 <= hour < 18:
            return "afternoon", "день (поцікався як проходить день, побажай легких справ)"
        elif 18 <= hour < 23:
            return "evening", "вечір (побажай затишного вечора, гарного відпочинку)"
        else:
            return "night", "ніч (побажай солодких снів, добраніч)"

    def generate_girlfriend_heart_message(self, custom_note: Optional[str] = None) -> str:
        """
        Генерує ніжне, романтичне повідомлення для дівчини з сердечками
        з точним урахуванням поточного часу доби (ранок/день/вечір/ніч).
        Використовує Gemini AI для унікальності або перевірену романтичну бібліотеку.
        СТРОГО: тільки дефіс '-', жодних довгих тире.
        """
        period_key, period_desc = self._get_time_of_day_context()

        if gemini_service.api_key and not gemini_service.api_key.startswith("AIzaSyYour") and gemini_service.client:
            prompt = f"""
Ти - турботливий, закоханий хлопець. Зараз на дворі {period_desc}.
Напиши коротке (1-2 речення) ніжне, романтичне, тепле повідомлення для своєї дівчини в TikTok, щоб підтримати вогник (streak).

ВИМОГИ:
1. Враховуй час доби: {period_desc}.
2. Багато милих сердечок та емодзі (❤️, 🥰, 💖, 💕, 💓, ✨, 🌸).
3. Щирий комплімент або побажання затишку.
4. Свіже, живе, тепле повідомлення (без канцеляризмів і шаблонності).
5. КРИТИЧНЕ ПРАВИЛО: ТІЛЬКИ звичайний дефіс '-', НІКОЛИ не використовуй довге тире '—' або '–'!
6. Поверни ВИКЛЮЧНО готовий текст повідомлення без лапок і коментарів.
{"Контекст/побажання: " + custom_note if custom_note else ""}
"""
            try:
                resp = gemini_service.generate_content([prompt])
                if resp:
                    clean = sanitize_typography(resp.text.strip())
                    if clean:
                        return clean
            except Exception as e:
                logger.warning(f"Помилка Gemini при генерації повідомлення для дівчини: {e}")

        # Fallback з урахуванням часу доби
        time_options = GIRLFRIEND_TIME_TEMPLATES.get(period_key, GIRLFRIEND_HEART_TEMPLATES)
        chosen = random.choice(time_options)
        return sanitize_typography(chosen)

    def generate_friend_streak_message(self) -> str:
        """
        Генерує дружнє повідомлення про вогник з реальною актуальною погодою (Чернівці).
        Використовує Gemini AI для унікальності або перевірені погодні шаблони.
        """
        from services.weather_service import get_current_weather, format_friend_weather_streak_message
        w = get_current_weather("Chernivtsi")
        weather_summary = w.get("summary", "+18°C, комфортно 🌤")

        if gemini_service.api_key and not gemini_service.api_key.startswith("AIzaSyYour") and gemini_service.client:
            prompt = f"""
Ти - Бодя. Напиши коротке (1-2 речення) повідомлення кенту/другу в TikTok для щоденного вогника (streak).
ОБОВ'ЯЗКОВО згадай сьогоднішню реальну погоду в Чернівцях: {weather_summary}.
СТИЛЬ:
1. Жива українська мова, дотепний дружній вайб ("йоу", "бро", "одягайся тепліше", "не мерзни", "тримаєм вогник").
2. Обов'язково емодзі вогника 🔥.
3. Тільки дефіс '-', ніяких довгих тире.
4. Поверни ТІЛЬКИ готовий текст повідомлення без лапок і вступних слів.
"""
            try:
                resp = gemini_service.generate_content([prompt])
                if resp and getattr(resp, "text", None):
                    clean = sanitize_typography(resp.text.strip())
                    if clean:
                        return clean
            except Exception as e:
                logger.debug(f"Помилка Gemini для погоди друзів: {e}")

        return sanitize_typography(format_friend_weather_streak_message("Chernivtsi"))

    def get_streaks_session_id(self) -> str:
        """Повертає sessionid окремого акаунта вогників (з БД, .env або tiktok_state.json)"""
        sess = get_setting("tiktok_streaks_session_id", TIKTOK_STREAKS_SESSION_ID)
        if sess and not sess.startswith("your_") and not sess.startswith("mock_"):
            return sess

        # Спробуємо витягнути з tiktok_state.json
        state_file = DATA_DIR / "tiktok_state.json"
        if state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    state_data = json.load(f)
                    for cookie in state_data.get("cookies", []):
                        if cookie.get("name") == "sessionid" and cookie.get("value"):
                            return cookie["value"]
            except Exception as e:
                logger.debug(f"Не вдалося зчитати sessionid з {state_file}: {e}")

        cookies_file = DATA_DIR / "tiktok_cookies.json"
        if cookies_file.exists():
            try:
                with open(cookies_file, "r", encoding="utf-8") as f:
                    cookies_data = json.load(f)
                    if isinstance(cookies_data, list):
                        for cookie in cookies_data:
                            if cookie.get("name") == "sessionid" and cookie.get("value"):
                                return cookie["value"]
            except Exception as e:
                logger.debug(f"Не вдалося зчитати sessionid з {cookies_file}: {e}")

        return ""

    def is_streaks_session_configured(self) -> bool:
        """Перевіряє чи налаштовано сесію для вогників (через sessionid або збережений tiktok_state.json)"""
        state_file = DATA_DIR / "tiktok_state.json"
        if state_file.exists():
            return True
        sess = self.get_streaks_session_id()
        return bool(sess and not sess.startswith("your_") and not sess.startswith("mock_"))

    def _notify_admin_telegram(self, text: str):
        """Надсилає оперативне сповіщення адміністраторам у Telegram через Bot API"""
        token = CHANNEL_AUTOMATION_BOT_TOKEN or TELEGRAM_BOT_TOKEN
        if not token or token.startswith("123456789:") or not ALLOWED_USER_IDS:
            return
        import requests
        for uid in ALLOWED_USER_IDS:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": uid, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
                    timeout=5
                )
            except Exception as e:
                logger.debug(f"Не вдалося надіслати сповіщення вогника в Telegram: {e}")

    async def _send_via_playwright(self, username: str, message_text: str, session_id: str) -> Tuple[bool, Optional[str]]:
        """
        Автоматизована відправка Direct Message через Playwright Chromium у фоновому браузері.
        Підтримує авто-перемикання на пряме з'єднання при збоях проксі тунелю.
        """
        configured_proxy = proxy_manager.get_playwright_proxy()
        proxy_configs = [configured_proxy, None] if configured_proxy else [None]

        last_err = None
        for p_cfg in proxy_configs:
            try:
                success, err = await self._send_single_dm_attempt(username, message_text, session_id, p_cfg)
                if success:
                    return True, None
                last_err = err
                if p_cfg is not None and any(w in str(err).lower() for w in ["tunnel", "proxy", "connection", "err_"]):
                    logger.warning(f"Проксі не зміг підключитися ({err}). Автоматично перемикаємо на пряме з'єднання...")
                    continue
                return False, err
            except Exception as e:
                last_err = str(e)
                if p_cfg is not None:
                    logger.warning(f"Збій проксі ({e}), пробуємо пряме з'єднання...")
                    continue
                return False, last_err

        return False, last_err

    async def _send_single_dm_attempt(self, username: str, message_text: str, session_id: str, proxy_cfg: Optional[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return False, "Playwright не встановлено у системі (запустіть: pip install playwright && playwright install chromium)"

        try:
            from playwright_stealth import stealth_async
            has_stealth = True
        except ImportError:
            has_stealth = False

        try:
            async with async_playwright() as p:
                launch_args = [
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check"
                ]
                browser = await p.chromium.launch(
                    headless=True,
                    proxy=proxy_cfg,
                    args=launch_args
                )

                try:
                    state_file = DATA_DIR / "tiktok_state.json"
                    cookies_file = DATA_DIR / "tiktok_cookies.json"

                    context_kwargs = {
                        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        "viewport": {"width": 1280, "height": 800},
                        "locale": "uk-UA"
                    }
                    if state_file.exists():
                        logger.info(f"Використовуємо збережену сесію: {state_file}")
                        context_kwargs["storage_state"] = str(state_file)

                    context = await browser.new_context(**context_kwargs)

                    if cookies_file.exists():
                        try:
                            with open(cookies_file, "r", encoding="utf-8") as cf:
                                raw_cookies = json.load(cf)
                                if isinstance(raw_cookies, list):
                                    await context.add_cookies(raw_cookies)
                                    logger.info(f"Завантажено {len(raw_cookies)} cookies з {cookies_file}")
                        except Exception as ce:
                            logger.warning(f"Помилка завантаження cookies: {ce}")
                    elif not state_file.exists() and session_id:
                        await context.add_cookies([
                            {"name": "sessionid", "value": session_id, "domain": ".tiktok.com", "path": "/", "secure": True, "httpOnly": True},
                            {"name": "sessionid_ss", "value": session_id, "domain": ".tiktok.com", "path": "/", "secure": True, "httpOnly": True}
                        ])

                    page = await context.new_page()
                    if has_stealth:
                        try:
                            await stealth_async(page)
                        except Exception:
                            pass

                    # 1. Відкриваємо розділ повідомлень TikTok
                    logger.info(f"Відкриваємо повідомлення TikTok для діалогу з @{username}...")
                    try:
                        await page.goto("https://www.tiktok.com/messages", timeout=40000, wait_until="domcontentloaded")
                    except Exception:
                        await page.goto("https://www.tiktok.com/messages", timeout=40000)
                    await page.wait_for_timeout(4000)

                    if "login" in page.url.lower():
                        return False, "❌ TikTok сесія не авторизована. Запустіть 'python scripts/login_tiktok_once.py'"

                    # Шукаємо контакт у списку чатів
                    KNOWN_DISPLAY_NAMES = {
                        "jungajak8123": ["Бо Бо Рис", "jungajak8123"],
                        "lady_valeri1": ["Lady_Valeri", "lady_valeri", "lady_valeriiiii", "Кохана"],
                        "davidka223": ["davidkaaa", "davidka223", "Давід"],
                        "lesko.new": ["Лесько", "lesko.new", "lesko"],
                        "crypton_freedom": ["chicken gunner", "crypton_freedom", "crypton"],
                        "13podpivasnik37": ["ПОЛЯРНИЙ МИШКА", "13podpivasnik37", "мишка"]
                    }

                    aliases = KNOWN_DISPLAY_NAMES.get(username.lower(), [username])
                    target_row = None
                    for alias in aliases:
                        row = page.locator(f'div[data-e2e="dm-new-conversation-item"]:has-text("{alias}")')
                        if await row.count() > 0:
                            target_row = row.first
                            break
                        txt_loc = page.locator(f'[data-e2e="dm-new-conversation-list"] :text-is("{alias}")')
                        if await txt_loc.count() > 0:
                            target_row = txt_loc.first
                            break

                    target_found = False
                    if target_row:
                        logger.info(f"Знайдено контакт @{username} у списку повідомлень, відкриваємо...")
                        await target_row.click(force=True)
                        await page.wait_for_timeout(3000)
                        target_found = True
                    else:
                        # 2. Якщо контакту немає серед недавніх — переходимо на прямий профіль
                        logger.info(f"Контакт не знайдено в недавніх чатах, переходимо на профіль @{username}...")
                        try:
                            await page.goto(f"https://www.tiktok.com/@{username}", timeout=40000, wait_until="networkidle")
                        except Exception:
                            await page.goto(f"https://www.tiktok.com/@{username}", timeout=40000, wait_until="domcontentloaded")
                        await page.wait_for_timeout(3500)

                        if "login" in page.url.lower():
                            return False, "❌ TikTok сесія не авторизована."

                        # Закриваємо pop-up сповіщення якщо є
                        close_btns = page.locator('button[aria-label="Close"], button:has-text("✕"), button[data-e2e="toast-close"]')
                        for _ in range(await close_btns.count()):
                            try:
                                await close_btns.first.click(timeout=1000)
                            except Exception:
                                break

                        message_btn = page.locator('button[data-e2e="message-button"], button:has-text("Message"), button:has-text("Повідомлення")')
                        if await message_btn.count() == 0:
                            return False, f"⚠️ Кнопку Message не знайдено у @{username} (профіль приватний або закриті DM)"
                        await message_btn.first.click(force=True)
                        await page.wait_for_timeout(3500)

                        # Якщо виїхала панель — клікаємо по кнопці розгортання або по контакту
                        expand_btn = page.locator('button[aria-label*="xpand"], a[href*="/messages"]').first
                        if await expand_btn.count() > 0:
                            try:
                                await expand_btn.click(force=True)
                                await page.wait_for_timeout(2500)
                            except Exception:
                                pass

                        drawer_item = page.locator(f'div[data-e2e="dm-new-conversation-item"]:has-text("{username}"), div:has-text("{username}")').first
                        if await drawer_item.count() > 0:
                            try:
                                await drawer_item.click(force=True)
                                await page.wait_for_timeout(2500)
                            except Exception:
                                pass

                    # Закриваємо pop-up сповіщення якщо є
                    close_selectors = [
                        'button[aria-label="Close"]',
                        'button:has-text("✕")',
                        'button[data-e2e="toast-close"]',
                        'button:has-text("Not now")',
                        'button:has-text("Не зараз")',
                        'button:has-text("Пізніше")',
                        'button:has-text("Later")'
                    ]
                    for sel in close_selectors:
                        btns = page.locator(sel)
                        for _ in range(await btns.count()):
                            try:
                                await btns.first.click(timeout=1000)
                            except Exception:
                                break

                    # 3. Шукаємо поле вводу (TikTok DM chat input)
                    chat_input = page.locator(
                        'div.public-DraftEditor-content[contenteditable="true"], '
                        '[data-e2e="chat-input"] [contenteditable="true"], '
                        '[contenteditable="true"][role="textbox"], '
                        '[contenteditable="true"], '
                        'textarea, '
                        'div[data-e2e="chat-room"] [contenteditable="true"]'
                    )

                    try:
                        await chat_input.first.wait_for(state="visible", timeout=12000)
                    except Exception:
                        pass

                    if await chat_input.count() == 0:
                        # Спробуємо активувати вікно чату кліком по тілу діалогу
                        chat_box = page.locator('div[class*="DivChatBox"], div[data-e2e="chat-room"]').first
                        if await chat_box.count() > 0:
                            try:
                                await chat_box.click(force=True)
                                await page.wait_for_timeout(1000)
                            except Exception:
                                pass
                            chat_input = page.locator(
                                'div.public-DraftEditor-content[contenteditable="true"], '
                                '[data-e2e="chat-input"] [contenteditable="true"], '
                                '[contenteditable="true"][role="textbox"], '
                                '[contenteditable="true"], '
                                'textarea'
                            )

                    if await chat_input.count() == 0:
                        # Перевіряємо чи повідомлення вже випадково не було надіслано раніше
                        chat_items = page.locator('div[data-e2e="dm-new-chat-item"]')
                        if await chat_items.count() > 0:
                            last_item = chat_items.last
                            last_text = (await last_item.inner_text() or "").strip()
                            if any(k in last_text for k in ["Доброго ранку", "сонечко", "❤️", "🥰", "вогник"]):
                                logger.info(f"В чаті з @{username} вже є надіслане повідомлення. Вважаємо доставленим.")
                                return True, "Повідомлення вже було надіслано в чат раніше"

                        try:
                            await page.screenshot(path=str(DATA_DIR / "tiktok_chat_debug.png"))
                        except Exception:
                            pass
                        return False, "⚠️ Чат відкрився, але поле вводу тексту не знайдено"

                    input_field = chat_input.first
                    await input_field.click(force=True)
                    await page.wait_for_timeout(500)

                    # Вводимо повідомлення у Draft.js через keyboard.type
                    try:
                        await page.keyboard.type(message_text, delay=25)
                    except Exception:
                        await input_field.fill(message_text)
                    await page.wait_for_timeout(800)

                    # Натискаємо Enter для відправки
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(3000)

                    try:
                        await context.storage_state(path=str(state_file))
                    except Exception:
                        pass

                    logger.info(f"✅ Повідомлення успішно відправлено у TikTok для @{username}!")
                    return True, "✅ Успішно надіслано через браузер TikTok"

                finally:
                    await browser.close()
        except Exception as e:
            err = security_guard.sanitize_error(str(e))
            logger.error(f"Помилка Playwright при відправці TikTok DM: {err}")
            return False, f"Помилка браузера Playwright: {err}"

    async def send_tiktok_direct_message(self, username: str, message_text: str) -> Tuple[bool, Optional[str]]:
        """
        Відправляє Direct Message у TikTok з акаунта вогників.
        Включає перевірку сесії, Playwright-автоматизацію та Telegram сповіщення.
        """
        clean_user = username.strip().lstrip("@")
        clean_text = sanitize_typography(message_text)
        session_id = self.get_streaks_session_id()

        # 1. Перевірка наявності збереженої сесії або Demo/Dry-Run
        state_file = DATA_DIR / "tiktok_state.json"
        has_session = state_file.exists() or bool(session_id and not session_id.startswith("your_") and not session_id.startswith("mock_"))

        if DRY_RUN_MODE or not has_session:
            logger.info(f"🧪 [DRY-RUN / ОЧІКУВАННЯ КЛЮЧІВ] TikTok DM -> @{clean_user}: '{clean_text}'")
            return True, "Демо-режим: повідомлення сформовано успішно (очікує збереженої сесії або TIKTOK_STREAKS_SESSION_ID)"

        # 2. Безпека: перевірка US/NY проксі (не блокуємо якщо STRICT_PROXY_CHECK вимкнено)
        is_safe, safety_msg = proxy_manager.verify_platform_safety("tiktok")
        if not is_safe:
            if STRICT_PROXY_CHECK:
                logger.warning(f"Захист від блокування TikTok: {safety_msg}")
                self._notify_admin_telegram(
                    f"⛔️ <b>TikTok Вогник заблоковано захистом: @{clean_user}</b>\n"
                    f"Причина: {safety_msg}\n"
                    f"💬 Повідомлення: <code>{clean_text}</code>"
                )
                return False, safety_msg
            else:
                logger.warning(f"Попередження проксі для TikTok: {safety_msg}. Продовжуємо відправку.")

        # 3. Реальна відправка через Playwright Chromium
        logger.info(f"Спроба автоматичної відправки TikTok вогника до @{clean_user} через Playwright...")
        success, err = await self._send_via_playwright(clean_user, clean_text, session_id)

        if success:
            logger.info(f"TikTok вогник успішно доставлено до @{clean_user}")
            self._notify_admin_telegram(
                f"🔥 <b>TikTok Вогник доставлено!</b>\n"
                f"👤 Контакт: <b>@{clean_user}</b>\n"
                f"💬 Повідомлення: <i>«{clean_text}»</i>"
            )
            return True, None
        else:
            logger.warning(f"Не вдалося доставити вогник автоматично до @{clean_user}: {err}")
            self._notify_admin_telegram(
                f"🚨 <b>УВАГА! TikTok Вогник під загрозою: @{clean_user}</b>\n\n"
                f"⚠️ Причина авто-відправки: {err}\n"
                f"👉 <a href='https://www.tiktok.com/@{clean_user}'>Відкрити чат @{clean_user} у TikTok</a>\n\n"
                f"💬 <b>Текст повідомлення (натисніть щоб скопіювати):</b>\n"
                f"<code>{clean_text}</code>"
            )
            return False, err

    async def run_streaks_dispatch(self, force_all: bool = False, friends_only: bool = False) -> Dict[str, Any]:
        """
        Головний цикл щоденної відправки вогників:
        - Знаходить акаунт дівчини та надсилає їй теплі повідомлення з сердечками (❤️).
        - Знаходить усіх друзів із вогниками та надсилає їм вогник (🔥) з погодою в Чернівцях.
        - Дотримується рандомізованого інтервалу (3-7 сек) між відправками для захисту від підозр.
        """
        targets = get_streak_targets(active_only=True)
        if not targets:
            # Якщо список порожній, але дівчина задана в конфігу
            self._ensure_girlfriend_initialized()
            targets = get_streak_targets(active_only=True)

        if friends_only:
            targets = [t for t in targets if not t.get("is_girlfriend")]

        if not targets:
            return {
                "success": False,
                "message": "Список контактів для вогників порожній. Додайте нікнейми через меню бота або .env!",
                "sent_count": 0,
                "details": []
            }

        sent_count = 0
        failed_count = 0
        details = []

        today_date = datetime.now().strftime("%Y-%m-%d")
        tracker_file = DATA_DIR / "streak_daily_tracker.json"
        daily_sent = {}
        if tracker_file.exists():
            try:
                daily_sent = json.loads(tracker_file.read_text(encoding="utf-8"))
            except Exception:
                daily_sent = {}
        if not isinstance(daily_sent, dict):
            daily_sent = {}
        sent_today_users = set(daily_sent.get(today_date, []))

        logger.info(f"Запуск розсилки TikTok вогників для {len(targets)} контактів...")

        for idx, target in enumerate(targets):
            user = target["username"]
            clean_user = user.strip().lstrip("@").lower()
            is_gf = bool(target["is_girlfriend"])
            custom_msg = target.get("custom_message")
            last_sent_at = str(target.get("last_sent_at") or "")

            # Для дівчини автоматичні вогники та повідомлення повністю вимкнено за вимогою користувача!
            # Її повідомлення лише пересилаються в Telegram, а бот їй нічого не пише сам.
            if is_gf:
                logger.info(f"⏭️ Пропускаємо акаунт дівчини @{user}: автоматична відправка вимкнена. Повідомлення тільки пересилаються в Telegram.")
                continue

            # Захист від повторної відправки в той самий день (anti-duplicate guard)
            if not force_all and (today_date in last_sent_at or clean_user in sent_today_users):
                logger.info(f"⏭️ Вогник для @{user} вже відправлено сьогодні. Пропускаємо повторну відправку.")
                details.append({
                    "username": user,
                    "is_girlfriend": is_gf,
                    "message": "Вже відправлено сьогодні",
                    "status": "already_sent_today",
                    "error": None
                })
                sent_count += 1
                continue

            # 1. Генерація правильного повідомлення (для друзів: з реальною погодою в Чернівцях)
            msg_text = custom_msg or self.generate_friend_streak_message()

            # 2. Рандомізована затримка між повідомленнями (Humanized Jitter)
            if idx > 0:
                jitter = random.uniform(3.0, 6.5)
                await asyncio.sleep(jitter)

            # 3. Відправка повідомлення
            success, err = await self.send_tiktok_direct_message(user, msg_text)
            status_str = "sent" if success and not err else ("dry_run" if success and err and "Демо" in err else "failed")

            # 4. Логування в БД
            save_streak_log(
                target_username=user,
                is_girlfriend=is_gf,
                message_text=msg_text,
                status=status_str,
                error=err
            )

            if success:
                update_streak_target_sent(user)
                sent_count += 1
                sent_today_users.add(clean_user)
                daily_sent[today_date] = list(sent_today_users)
                try:
                    tracker_file.write_text(json.dumps(daily_sent, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
            else:
                failed_count += 1

            details.append({
                "username": user,
                "is_girlfriend": is_gf,
                "message": msg_text,
                "status": status_str,
                "error": err
            })

        return {
            "success": sent_count > 0 or len(targets) > 0,
            "total_targets": len(targets),
            "sent_count": sent_count,
            "failed_count": failed_count,
            "details": details,
            "executed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def check_streak_decay_warnings(self, threshold_hours: float = 20.0) -> List[Dict[str, Any]]:
        """
        Перевіряє контакти, у яких вогник під загрозою згасання (минуло > 20 годин).
        """
        from core.database import get_expiring_streaks
        return get_expiring_streaks(threshold_hours)

    def preview_sample_messages(self) -> Dict[str, str]:
        """Показує приклад повідомлень, які будуть надіслані сьогодні"""
        return {
            "girlfriend": self.generate_girlfriend_heart_message(),
            "friend": self.generate_friend_streak_message()
        }

    async def check_and_react_to_shared_videos(self) -> List[Dict[str, Any]]:
        """
        Перевіряє чати з друзями та коханою у TikTok:
        - Якщо хтось надіслав/поділився TikTok відео (a[href*="/video/"]):
        - Перевіряє, що це саме вхідне відео від співрозмовника (а не надіслане нами).
        - Перевіряє, чи ми вже не реагували на це відео (по базі SQLite).
        - Завантажує відео та аналізує його через Gemini AI (ураховуючи дівчина чи бро).
        - Відправляє автентичну згенеровану реакцію прямо в чат TikTok!
        - Надсилає сповіщення зі звітом адміністратору в Telegram.
        """
        try:
            from playwright.async_api import async_playwright
            from services.tiktok_reactions import tiktok_reactions_service
            from core.database import get_recent_tiktok_reactions
        except ImportError as e:
            logger.error(f"Не вдалося імпортувати компоненти для реакцій: {e}")
            return []

        targets = get_streak_targets(active_only=True)
        if not targets:
            self._ensure_girlfriend_initialized()
            targets = get_streak_targets(active_only=True)

        if not targets:
            return []

        # Відомі попередні реакції, щоб не коментувати повторно одне й те саме відео
        existing_reactions = get_recent_tiktok_reactions(limit=200)
        responded_urls = {r.get("video_url") for r in existing_reactions if r.get("video_url")}

        gf_tracker_file = DATA_DIR / "tiktok_forwarded_gf_messages.json"
        forwarded_gf_keys = set()
        if gf_tracker_file.exists():
            try:
                forwarded_gf_keys = set(json.loads(gf_tracker_file.read_text(encoding="utf-8")))
            except Exception:
                forwarded_gf_keys = set()

        configured_proxy = proxy_manager.get_playwright_proxy()
        proxy_configs = [configured_proxy, None] if configured_proxy else [None]
        processed = []

        for p_cfg in proxy_configs:
            try:
                async with async_playwright() as p:
                    launch_args = [
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-software-rasterizer",
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check"
                    ]
                    browser = await p.chromium.launch(
                        headless=True,
                        proxy=p_cfg,
                        args=launch_args
                    )
                    try:
                        state_file = DATA_DIR / "tiktok_state.json"
                        cookies_file = DATA_DIR / "tiktok_cookies.json"
                        session_id = self.get_streaks_session_id()

                        context_kwargs = {
                            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                            "viewport": {"width": 1280, "height": 800},
                            "locale": "uk-UA"
                        }
                        if state_file.exists():
                            context_kwargs["storage_state"] = str(state_file)

                        context = await browser.new_context(**context_kwargs)

                        if cookies_file.exists():
                            try:
                                with open(cookies_file, "r", encoding="utf-8") as cf:
                                    raw_cookies = json.load(cf)
                                    if isinstance(raw_cookies, list):
                                        await context.add_cookies(raw_cookies)
                            except Exception:
                                pass
                        elif not state_file.exists() and session_id:
                            await context.add_cookies([
                                {"name": "sessionid", "value": session_id, "domain": ".tiktok.com", "path": "/", "secure": True, "httpOnly": True},
                                {"name": "sessionid_ss", "value": session_id, "domain": ".tiktok.com", "path": "/", "secure": True, "httpOnly": True}
                            ])

                        page = await context.new_page()

                        logger.info("Відкриваємо TikTok Messages для перевірки надісланих відео...")
                        try:
                            await page.goto("https://www.tiktok.com/messages", timeout=40000, wait_until="domcontentloaded")
                        except Exception:
                            await page.goto("https://www.tiktok.com/messages", timeout=40000)
                        await page.wait_for_timeout(4000)

                        KNOWN_DISPLAY_NAMES = {
                            "jungajak8123": ["Бо Бо Рис", "jungajak8123"],
                            "lady_valeri1": ["Lady_Valeri", "lady_valeri", "lady_valeriiiii", "Кохана"],
                            "davidka223": ["davidkaaa", "davidka223", "Давід"],
                            "lesko.new": ["Лесько", "lesko.new", "lesko"],
                            "crypton_freedom": ["chicken gunner", "crypton_freedom", "crypton"],
                            "13podpivasnik37": ["ПОЛЯРНИЙ МИШКА", "13podpivasnik37", "мишка"]
                        }
    
                        for target in targets:
                            user = target["username"].lower()
                            is_gf = bool(target.get("is_girlfriend"))
                            nick = target.get("nickname") or user
    
                            aliases = KNOWN_DISPLAY_NAMES.get(user, [user])
                            if nick and nick not in aliases:
                                aliases.append(nick)
    
                            chat_target = None
                            for alias in aliases:
                                row = page.locator(f'div[data-e2e="dm-new-conversation-item"]:has-text("{alias}")')
                                if await row.count() > 0:
                                    chat_target = row.first
                                    break
                                loc = page.locator(f'text="{alias}", [href*="/{alias}"]')
                                if await loc.count() > 0:
                                    chat_target = loc.first
                                    break
    
                            if not chat_target:
                                continue
    
                            await chat_target.click(force=True)
                            await page.wait_for_timeout(2500)
    
                            # Перевіряємо повідомлення ТІЛЬКИ у вікні активного діалогу (div[class*="DivChatBox"]), а не в лівій колонці нотифікацій
                            chat_box = page.locator('div[class*="DivChatBox"], div[data-e2e="chat-room"]')
                            if await chat_box.count() == 0:
                                continue

                            chat_items = chat_box.locator('div[data-e2e="dm-new-chat-item"]')
                            item_count = await chat_items.count()
                            if item_count == 0:
                                continue

                            # ==========================================
                            # 1. СПЕЦІАЛЬНА ОБРОБКА ДЛЯ ДІВЧИНИ (LADY_VALERI)
                            # ==========================================
                            if is_gf:
                                # Для коханої: пересилаємо ВСІ нові вхідні повідомлення та відео прямо в Telegram!
                                # БОТ КАТЕГОРИЧНО НІЧОГО НЕ НАДСИЛАЄ ЇЙ У ВІДПОВІДЬ!
                                start_idx = max(0, item_count - 8)
                                for idx_msg in range(start_idx, item_count):
                                    m_elem = chat_items.nth(idx_msg)
                                    msg_info = await m_elem.evaluate(
                                        """el => {
                                            const text = el.innerText || '';
                                            const hasMyAvatar = !!el.querySelector('a[href*="/@flame.ai"]') || !!el.querySelector('a[href*="/@bohdan"]');
                                            const hasYouReplied = text.includes("You replied");
                                            const textContainer = el.querySelector('div[class*="DivTextContainer"]');
                                            const isCyanBg = textContainer && window.getComputedStyle(textContainer).backgroundColor.includes("162, 201");
                                            const isSelf = !!el.querySelector('[data-e2e*="self"], [class*="Self"], [class*="Right"]');

                                            if (hasMyAvatar || hasYouReplied || isCyanBg || isSelf) {
                                                return { isIncoming: false };
                                            }

                                            const directLink = el.querySelector('a[href*="/video/"]');
                                            const sharedVideo = el.querySelector('[data-e2e="dm-new-shared-video"]');
                                            const moreBtn = el.querySelector('[data-e2e="dm-new-more-btn"]');
                                            const msgId = moreBtn ? moreBtn.id : null;
                                            const videoUrl = directLink ? directLink.href : null;

                                            return {
                                                isIncoming: true,
                                                hasVideo: !!(directLink || sharedVideo),
                                                directUrl: videoUrl,
                                                msgId: msgId,
                                                text: text.trim(),
                                                isSharedCard: !!sharedVideo
                                            };
                                        }"""
                                    )

                                    if not msg_info or not msg_info.get("isIncoming"):
                                        continue

                                    v_url = msg_info.get("directUrl")
                                    raw_txt = (msg_info.get("text") or "").strip()
                                    mid = msg_info.get("msgId") or ""

                                    if msg_info.get("hasVideo") and not v_url and msg_info.get("isSharedCard"):
                                        shared_el = m_elem.locator('[data-e2e="dm-new-shared-video"]').first
                                        if await shared_el.count() > 0:
                                            try:
                                                await shared_el.click()
                                                await page.wait_for_timeout(2000)
                                                if "/video/" in page.url:
                                                    v_url = page.url
                                                    await page.go_back()
                                                    await page.wait_for_timeout(1500)
                                            except Exception:
                                                pass

                                    key_content = v_url or raw_txt[:80]
                                    if not key_content:
                                        continue
                                    msg_key = f"{user}:{mid}:{key_content}"

                                    if msg_key in forwarded_gf_keys:
                                        continue

                                    if msg_info.get("hasVideo") and v_url:
                                        logger.info(f"💌 Пересилаємо нове TikTok відео від дівчини (@{user}) в Telegram...")
                                        self._notify_admin_telegram(
                                            f"🎬 <b>Кохана (@{user}) надіслала TikTok відео:</b>\n\n"
                                            f"🔗 <a href='{v_url}'>Дивитись відео в TikTok</a>\n\n"
                                            f"💬 <i>(Бот нічого їй не надсилає - переглянь та дай відповідь сам)</i>"
                                        )
                                        forwarded_gf_keys.add(msg_key)
                                        processed.append({
                                            "username": user,
                                            "is_girlfriend": True,
                                            "video_url": v_url,
                                            "type": "video_forwarded"
                                        })
                                    elif raw_txt:
                                        lines = [l for l in raw_txt.splitlines() if not l.startswith("Shared a video") and not l.startswith("Replied")]
                                        clean_txt = "\n".join(lines).strip()
                                        if clean_txt:
                                            logger.info(f"💌 Пересилаємо текстове повідомлення від дівчини (@{user}) в Telegram...")
                                            self._notify_admin_telegram(
                                                f"💌 <b>Нове повідомлення від Коханої (@{user}) у TikTok:</b>\n\n"
                                                f"«{clean_txt}»\n\n"
                                                f"💬 <i>(Бот нічого їй не надсилає - напиши відповідь сам)</i>"
                                            )
                                            forwarded_gf_keys.add(msg_key)
                                            processed.append({
                                                "username": user,
                                                "is_girlfriend": True,
                                                "text": clean_txt,
                                                "type": "text_forwarded"
                                            })

                                try:
                                    gf_tracker_file.write_text(json.dumps(list(forwarded_gf_keys)[-500:], ensure_ascii=False, indent=2), encoding="utf-8")
                                except Exception:
                                    pass
                                continue

                            # ==========================================
                            # 2. ОБРОБКА ДЛЯ ДРУЗІВ (КЄНТІВ)
                            # ==========================================
                            # Аналізуємо СТРОГО останнє повідомлення у діалозі (не реагуємо на старі повідомлення та власні відповіді)
                            last_msg = chat_items.last
                            msg_analysis = await last_msg.evaluate(
                                """el => {
                                    const text = el.innerText || '';
                                    // 1. Перевірка чи повідомлення надіслано нами (Богданом)
                                    const hasMyAvatar = !!el.querySelector('a[href*="/@flame.ai"]') || !!el.querySelector('a[href*="/@bohdan"]');
                                    const hasYouReplied = text.includes("You replied");
                                    const textContainer = el.querySelector('div[class*="DivTextContainer"]');
                                    const isCyanBg = textContainer && window.getComputedStyle(textContainer).backgroundColor.includes("162, 201");
                                    const isSelf = !!el.querySelector('[data-e2e*="self"], [class*="Self"], [class*="Right"]');

                                    if (hasMyAvatar || hasYouReplied || isCyanBg || isSelf) {
                                        return { isIncoming: false, hasVideo: false, reason: "outgoing" };
                                    }

                                    // 2. Перевірка чи це відео
                                    const directLink = el.querySelector('a[href*="/video/"]');
                                    const sharedVideo = el.querySelector('[data-e2e="dm-new-shared-video"]');

                                    if (!directLink && !sharedVideo) {
                                        return { isIncoming: true, hasVideo: false, reason: "not_a_video" };
                                    }

                                    const moreBtn = el.querySelector('[data-e2e="dm-new-more-btn"]');
                                    const msgId = moreBtn ? moreBtn.id : null;
                                    let videoUrl = directLink ? directLink.href : null;

                                    return {
                                        isIncoming: true,
                                        hasVideo: true,
                                        directUrl: videoUrl,
                                        msgId: msgId,
                                        isSharedCard: !!sharedVideo
                                    };
                                }"""
                            )

                            if not msg_analysis.get("isIncoming"):
                                logger.debug(f"Останнє повідомлення у чаті @{user} надіслано нами. Реакція не потрібна.")
                                continue

                            if not msg_analysis.get("hasVideo"):
                                logger.debug(f"Останнє повідомлення від @{user} не є відео ({msg_analysis.get('reason')}). Реакція не потрібна.")
                                continue

                            full_url = msg_analysis.get("directUrl")
                            if not full_url and msg_analysis.get("isSharedCard"):
                                # Якщо це картка відео без прямого лінка - натискаємо на неї щоб отримати точний URL
                                shared_elem = last_msg.locator('[data-e2e="dm-new-shared-video"]').first
                                if await shared_elem.count() > 0:
                                    try:
                                        await shared_elem.click()
                                        await page.wait_for_timeout(2000)
                                        if "/video/" in page.url:
                                            full_url = page.url
                                            await page.go_back()
                                            await page.wait_for_timeout(1500)
                                    except Exception as nav_e:
                                        logger.debug(f"Не вдалося відкрити картку відео: {nav_e}")

                            if not full_url:
                                msg_id = msg_analysis.get("msgId")
                                if msg_id:
                                    full_url = f"https://www.tiktok.com/msg/{msg_id}"

                            if not full_url or full_url in responded_urls:
                                continue
                            logger.info(f"Знайдено нове надіслане TikTok відео від друга @{user}: {full_url}")
    
                            # Генеруємо автентичну реакцію через Gemini AI для кента
                            reaction_res = tiktok_reactions_service.process_tiktok_link(
                                url=full_url,
                                is_girlfriend=False
                            )
                            reaction_text = reaction_res.get("reaction") or "одааа, чисто сігма мув 😎"
    
                            # Знаходимо поле вводу чату та надсилаємо реакцію
                            chat_input = page.locator(
                                'div.public-DraftEditor-content[contenteditable="true"], '
                                '[data-e2e="chat-input"] [contenteditable="true"], '
                                'div[contenteditable="true"][role="textbox"], '
                                'div[contenteditable="true"]'
                            )
                            if await chat_input.count() > 0:
                                inp = chat_input.first
                                await inp.click(force=True)
                                await page.wait_for_timeout(400)
                                try:
                                    await page.keyboard.type(reaction_text, delay=25)
                                except Exception:
                                    await inp.fill(reaction_text)
                                await page.wait_for_timeout(600)
                                await page.keyboard.press("Enter")
                                await page.wait_for_timeout(2500)
    
                                responded_urls.add(full_url)
                                logger.info(f"✅ Реакцію Gemini успішно надіслано другу @{user}: «{reaction_text}»")
    
                                # Сповіщення адміну в Telegram
                                self._notify_admin_telegram(
                                    f"🎬 <b>Відреагував на TikTok відео друга (@{user}) через Gemini!</b>\n\n"
                                    f"🔗 Відео: <a href='{full_url}'>Дивитись відео</a>\n"
                                    f"💬 Реакція: <i>«{reaction_text}»</i>"
                                )
    
                                processed.append({
                                    "username": user,
                                    "is_girlfriend": False,
                                    "video_url": full_url,
                                    "reaction": reaction_text
                                })
    
                        # Оновлюємо та зберігаємо стан сесії
                        try:
                            await context.storage_state(path=str(DATA_DIR / "tiktok_state.json"))
                        except Exception:
                            pass
                    finally:
                        await browser.close()
                    break
            except Exception as e:
                if p_cfg is not None and any(w in str(e).lower() for w in ["tunnel", "proxy", "connection", "err_"]):
                    logger.warning(f"Проксі не підійшов для перевірки відео ({e}). Перемикаємо на пряме з'єднання...")
                    continue
                logger.error(f"Помилка при перевірці надісланих відео: {e}", exc_info=True)
                break

        return processed


# Глобальний екземпляр сервісу
tiktok_streak_service = TikTokStreakService()
automation_two = tiktok_streak_service
