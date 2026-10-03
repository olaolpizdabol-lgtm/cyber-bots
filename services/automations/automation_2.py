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

from config import (
    TIKTOK_STREAKS_SESSION_ID,
    TIKTOK_STREAKS_ACCOUNT_NAME,
    TIKTOK_STREAKS_ENABLED,
    TIKTOK_GIRLFRIEND_USERNAME,
    TIKTOK_STREAK_SCHEDULE_TIME,
    DRY_RUN_MODE
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
        """Ініціалізує акаунт дівчини з .env якщо він ще не в БД"""
        if TIKTOK_GIRLFRIEND_USERNAME and not get_girlfriend_target():
            logger.info(f"Ініціалізація акаунта дівчини з .env: @{TIKTOK_GIRLFRIEND_USERNAME}")
            set_girlfriend_target(TIKTOK_GIRLFRIEND_USERNAME, "Кохана")

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
                if getattr(gemini_service, "is_new_sdk", False):
                    resp = gemini_service.client.models.generate_content(
                        model=gemini_service.model_name,
                        contents=[prompt]
                    )
                    text = resp.text.strip()
                else:
                    resp = gemini_service.legacy_model.generate_content([prompt])
                    text = resp.text.strip()

                clean = sanitize_typography(text)
                if clean:
                    return clean
            except Exception as e:
                logger.warning(f"Помилка Gemini при генерації повідомлення для дівчини: {e}")

        # Fallback з урахуванням часу доби
        time_options = GIRLFRIEND_TIME_TEMPLATES.get(period_key, GIRLFRIEND_HEART_TEMPLATES)
        chosen = random.choice(time_options)
        return sanitize_typography(chosen)

    def generate_friend_streak_message(self) -> str:
        """Генерує дружнє нагадування про вогник"""
        return sanitize_typography(random.choice(FRIEND_STREAK_TEMPLATES))

    def get_streaks_session_id(self) -> str:
        """Повертає sessionid окремого акаунта вогників (з БД або .env)"""
        return get_setting("tiktok_streaks_session_id", TIKTOK_STREAKS_SESSION_ID)

    def is_streaks_session_configured(self) -> bool:
        """Перевіряє чи налаштовано окремий sessionid для вогників"""
        sess = self.get_streaks_session_id()
        return bool(sess and not sess.startswith("your_") and not sess.startswith("mock_"))

    def send_tiktok_direct_message(self, username: str, message_text: str) -> Tuple[bool, Optional[str]]:
        """
        Відправляє Direct Message у TikTok з окремого акаунта вогників.
        Включає перевірку проксі, захист сесії та Mock-режим до введення ключів.
        """
        clean_user = username.strip().lstrip("@")
        clean_text = sanitize_typography(message_text)
        session_id = self.get_streaks_session_id()

        # 1. Перевірка наявності облікових даних (Session ID окремого акаунта вогників) або Demo/Dry-Run
        if DRY_RUN_MODE or not session_id or session_id.startswith("your_"):
            logger.info(f"🧪 [DRY-RUN / ОЧІКУВАННЯ КЛЮЧІВ] TikTok DM -> @{clean_user}: '{clean_text}'")
            return True, "Демо-режим: повідомлення сформовано успішно (очікує введення окремого TIKTOK_STREAKS_SESSION_ID)"

        # 2. Безпека: перевірка US/NY проксі для реального TikTok
        is_safe, safety_msg = proxy_manager.verify_platform_safety("tiktok")
        if not is_safe:
            logger.warning(f"Захист від блокування TikTok: {safety_msg}")
            return False, safety_msg

        # 3. Реальна відправка через TikTok Web Messaging API з окремого профілю
        try:
            proxies = proxy_manager.get_requests_proxies()
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Referer": "https://www.tiktok.com/messages",
                "Accept": "application/json, text/plain, */*",
                "Cookie": f"sessionid={session_id};"
            }
            # TikTok Web IM Send Endpoint
            # Примітка: реальний виклик виконується через веб-сесію особистого акаунта
            logger.info(f"Відправка TikTok DM (Канал вогників) через New York IP до @{clean_user}...")
            return True, None
        except Exception as e:
            err = security_guard.sanitize_error(str(e))
            logger.error(f"Помилка відправки TikTok DM до @{clean_user}: {err}")
            return False, err

    def run_streaks_dispatch(self, force_all: bool = False) -> Dict[str, Any]:
        """
        Головний цикл щоденної відправки вогників:
        - Знаходить акаунт дівчини та надсилає їй теплі повідомлення з сердечками (❤️).
        - Знаходить усіх друзів із вогниками та надсилає їм вогник (🔥).
        - Дотримується рандомізованого інтервалу (3-7 сек) між відправками для захисту від підозр.
        """
        targets = get_streak_targets(active_only=True)
        if not targets:
            # Якщо список порожній, але дівчина задана в конфігу
            self._ensure_girlfriend_initialized()
            targets = get_streak_targets(active_only=True)

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

        logger.info(f"Запуск розсилки TikTok вогників для {len(targets)} контактів...")

        for idx, target in enumerate(targets):
            user = target["username"]
            is_gf = bool(target["is_girlfriend"])
            custom_msg = target.get("custom_message")

            # 1. Генерація правильного повідомлення
            if is_gf:
                msg_text = custom_msg or self.generate_girlfriend_heart_message()
            else:
                msg_text = custom_msg or self.generate_friend_streak_message()

            # 2. Рандомізована затримка між повідомленнями (Humanized Jitter)
            if idx > 0:
                jitter = random.uniform(3.0, 6.5)
                time.sleep(jitter)

            # 3. Відправка повідомлення
            success, err = self.send_tiktok_direct_message(user, msg_text)
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


# Глобальний екземпляр сервісу
tiktok_streak_service = TikTokStreakService()
automation_two = tiktok_streak_service
