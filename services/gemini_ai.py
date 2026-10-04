import os
import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from PIL import Image
from config import GEMINI_API_KEY, GEMINI_API_KEYS, GEMINI_MODEL
from core.database import get_setting
from core.content_type import ContentType

logger = logging.getLogger(__name__)


# ==========================================
# 🔍 БІБЛІОТЕКА SEO-ПРОМПТІВ ДЛЯ ОПИСІВ (2026)
# ==========================================
SEO_PROMPT_PRESETS: Dict[str, Dict[str, str]] = {
    "seo_viral": {
        "title": "🔍 Пошук + Вірусність (Рекомендований)",
        "desc": "Оптимізація під пошуковий рядок TikTok/IG та вірусні рекомендації FYP/Reels",
        "prompt": (
            "Проаналізуй контент та оптимізуй опис під пошукові запити (Social SEO 2026) для TikTok Search, Instagram Explore, YouTube Search, Pinterest та Google. "
            "1. Визнач головний пошуковий запит (Primary Search Keyword), який користувачі вбивають у пошуковий рядок на цю тему. "
            "2. Органічно інтегруй цей точний пошуковий запит у перші 1-2 рядки опису для закріплення у пошуковому блоці 'Search: [запит]'. "
            "3. Додай 3-5 LSI-ключових слів та синонімів у тіло тексту без переспаму. "
            "4. Поєднай пошуковий намір (Search Intent) із потужним гачком (Hook) та закликом до дії (CTA). "
            "5. Підбери релевантні нішеві SEO-хештеги (пошукові кластери)."
        )
    },
    "seo_howto": {
        "title": "📚 Гайди та Інструкції (How-To SEO)",
        "desc": "Для навчальних відео, туторіалів та порад ('Як зробити...', 'Покроковий гайд...')",
        "prompt": (
            "Оптимізуй опис під високонамірні навчальні пошукові запити ('Як зробити...', 'Покроковий гайд...', 'Інструкція'). "
            "1. Заголовок і перший рядок мають точно відповідати формулюванню проблеми, яку шукає користувач у пошуку. "
            "2. Опиши конкретні кроки розв'язання проблеми з використанням ключових технічних термінів та слів-тригерів. "
            "3. Включи пошукові запити довгого хвоста (Long-tail keywords). "
            "4. Заклик до дії: зберегти у закладки для подальшого перегляду."
        )
    },
    "seo_top": {
        "title": "🏆 ТОП-добірки та Рейтинги (Top List SEO)",
        "desc": "Для списків, сервісів та підбірок ('ТОП-5...', 'Найкращі інструменти...')",
        "prompt": (
            "Оптимізуй опис під пошукові запити рейтингових добірок ('ТОП-5 сервісів...', 'Найкращі інструменти...', 'Добірка...'). "
            "1. Чіткий перелік з ключовими назвами, які люди вводять у пошуку. "
            "2. Перше речення містить точну фразу пошуку ('Шукаєш найкращі інструменти для...? Ось перевірений ТОП:'). "
            "3. Включи порівняльні ключові слова для вибору. "
            "4. Заклик прокоментувати свій улюблений варіант для підняття engagement."
        )
    },
    "seo_commercial": {
        "title": "💼 Комерційний / Продажі (B2B & E-commerce)",
        "desc": "Для товарів, послуг та бізнес-пропозицій ('Де купити...', 'Ціна...', 'Огляд')",
        "prompt": (
            "Оптимізуй опис під комерційні пошукові запити покупців ('Де купити...', 'Ціна...', 'Огляд продукту...', 'Відгуки...'). "
            "1. Включи точну назву продукту/послуги, сферу застосування та ключові переваги. "
            "2. Оптимізуй під запити з наміром покупки (Transactional Search Intent). "
            "3. Зрозумілий заклик до дії (CTA) для замовлення або переходу за посиланням."
        )
    }
}


def sanitize_typography(text: Optional[str]) -> str:
    """
    Критичне правило типографіки:
    Замінює всі довгі (—) та середні (–) тире, горизонтальні риски на стандартний дефіс (-).
    """
    if not text:
        return ""
    cleaned = str(text)
    for dash in ["—", "–", "―", "‒", "−"]:
        cleaned = cleaned.replace(dash, "-")
    return cleaned


def truncate_at_word_boundary(text: str, max_chars: int, suffix: str = "...") -> str:
    """
    Безпечне скорочення тексту по межах слів без обрізання слів навпіл.
    Гарантує що len(result) <= max_chars.
    """
    if not text:
        return ""
    text = sanitize_typography(text).strip()
    if len(text) <= max_chars:
        return text

    budget = max_chars - len(suffix)
    if budget <= 0:
        return text[:max_chars]

    sub = text[:budget]
    last_space = sub.rfind(" ")
    if last_space > int(budget * 0.5):
        return sub[:last_space].rstrip(",. !?") + suffix
    return sub.rstrip(",. !?") + suffix


class GeminiService:
    def __init__(self):
        self.api_keys = GEMINI_API_KEYS if GEMINI_API_KEYS else ([GEMINI_API_KEY] if GEMINI_API_KEY else [])
        self.api_key = self.api_keys[0] if self.api_keys else GEMINI_API_KEY
        self.model_name = GEMINI_MODEL
        self._key_index = 0
        self._clients: List[Any] = []
        self.is_new_sdk = True
        self._init_clients()

    def _init_clients(self):
        self._clients = []
        try:
            from google import genai
            from google.genai import types
            for key in self.api_keys:
                if key and not key.startswith("AIzaSyYour"):
                    try:
                        c = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=60000))
                        self._clients.append(c)
                    except Exception as e:
                        logger.error(f"Помилка створення Gemini клієнта: {e}")
            if self._clients:
                self.is_new_sdk = True
                logger.info(f"Успішно підключено {len(self._clients)} Gemini клієнтів для ротації.")
            else:
                raise RuntimeError("Немає доступних modern Gemini клієнтів")
        except Exception as e:
            logger.warning(f"google.genai не ініціалізовано: {e}. Спроба legacy google.generativeai.")
            try:
                import google.generativeai as legacy_genai
                if self.api_key:
                    legacy_genai.configure(api_key=self.api_key)
                    self.legacy_model = legacy_genai.GenerativeModel(self.model_name)
                    self.is_new_sdk = False
            except Exception as e2:
                logger.error(f"Помилка ініціалізації Gemini: {e2}")

    @property
    def client(self):
        if not self._clients:
            return None
        return self._clients[self._key_index % len(self._clients)]

    def _rotate_key(self):
        if self._clients:
            self._key_index = (self._key_index + 1) % len(self._clients)
            logger.info(f"🔄 Ротація Gemini ключа: переключено на слот #{self._key_index + 1}/{len(self._clients)}")

    def generate_content(
        self,
        contents: Any,
        preferred_model: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        client_override: Optional[Any] = None
    ) -> Optional[Any]:
        """
        Універсальна відмовостійка генерація з ротацією ключів та каскадом моделей:
        1. Спробувати preferred_model (за замовчуванням gemini-3.5-flash).
        2. Якщо 504 DEADLINE_EXCEEDED, 503 UNAVAILABLE чи 404/403 —
           автоматично пробувати каскад: gemini-3.8-flash -> gemini-3.5-flash-lite -> gemini-3.1-flash-lite.
        3. Якщо 429 RESOURCE_EXHAUSTED — ротувати ключ і повторити.
        4. Якщо передано client_override (для завантажених файлів) — використовувати цей клієнт,
           щоб уникнути помилки 403 PERMISSION_DENIED між різними API ключами.
        """
        target_model = preferred_model or self.model_name
        models_cascade = [target_model]
        for alt in ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]:
            if alt not in models_cascade:
                models_cascade.append(alt)

        if not self._clients and hasattr(self, "legacy_model"):
            try:
                c_list = contents if isinstance(contents, list) else [contents]
                kwargs = {}
                if config:
                    kwargs["generation_config"] = config
                return self.legacy_model.generate_content(c_list, **kwargs)
            except Exception as e:
                logger.warning(f"Legacy Gemini помилка: {e}")
                return None

        if not self._clients:
            return None

        # Якщо передано клієнт, який володіє завантаженим файлом (щоб не зловити 403 між ключами)
        if client_override:
            for m in models_cascade:
                try:
                    kwargs = {}
                    if config:
                        kwargs["config"] = config
                    resp = client_override.models.generate_content(model=m, contents=contents, **kwargs)
                    if resp and (getattr(resp, "text", None) or getattr(resp, "candidates", None)):
                        return resp
                except Exception as e:
                    err_str = str(e)
                    logger.warning(f"Gemini client_override ({m}) помилка: {err_str[:100]}")
                    if "403" in err_str or "404" in err_str:
                        continue
                    continue
            return None

        max_key_attempts = len(self._clients)
        for m in models_cascade:
            for _ in range(max_key_attempts):
                c = self.client
                if not c:
                    break
                try:
                    kwargs = {}
                    if config:
                        kwargs["config"] = config
                    resp = c.models.generate_content(model=m, contents=contents, **kwargs)
                    if resp and (getattr(resp, "text", None) or getattr(resp, "candidates", None)):
                        return resp
                except Exception as e:
                    err_str = str(e)
                    logger.warning(f"Gemini ({m}, ключ #{self._key_index + 1}) помилка: {err_str[:100]}")
                    if "429" in err_str or "exhausted" in err_str.lower():
                        self._rotate_key()
                        continue
                    elif "504" in err_str or "503" in err_str or "deadline" in err_str.lower() or "unavailable" in err_str.lower() or "404" in err_str:
                        break
                    else:
                        self._rotate_key()
                        break
        return None

    def generate_metadata(
        self,
        content_type: ContentType,
        media_paths: Optional[List[str]] = None,
        raw_text: Optional[str] = None,
        prompt_override: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Універсальна генерація контенту з розрахунком точних лімітів та Social SEO (2026):
        - Оптимізація під пошукові запити (TikTok Search, Instagram Search, YouTube Search, Pinterest, Google)
        - X (Twitter): 100-240 симв (ліміт 280)
        - Threads: 150-400 симв (ліміт 500)
        - Facebook: 300-800 симв (ліміт 63k)
        - Bluesky: 150-250 симв (ліміт 300)
        - Shorts / Snapchat / Pinterest: заголовок до 100 симв
        - Instagram / TikTok: опис до 2200 симв, до 5 хештегів
        - СТРОГО: тільки дефіс '-', ніяких довгих '—' або '–'!
        """
        prompt = prompt_override or get_setting("ai_prompt")

        if not self.api_key or self.api_key.startswith("AIzaSyYour") or (not self.client and not hasattr(self, "legacy_model")):
            logger.warning("GEMINI_API_KEY не налаштовано або тестовий. Використовуємо демонстраційний генератор.")
            return self._generate_fallback(content_type, raw_text)

        system_instruction = f"""
Ти - провідний топ-експерт із Social Media SEO та пошукової оптимізації контенту (Search Query Optimization 2026).
Твоє ключове завдання - проаналізувати контент ({content_type.value}) та створити тексти, які:
1. Займають перші позиції у внутрішньому пошуку (TikTok Search, Instagram Search, YouTube Search, Pinterest Search, Google Search).
2. Забезпечують максимальний вірусний CTR та додиви (Watch Time) у рекомендаціях (FYP, Reels, Shorts).

🔥 СУВОРЕ ПРАВИЛО МОВИ (CRITICAL LANGUAGE RULE - 100% ENGLISH):
УВЕСЬ згенерований контент (youtube_title, caption, snapchat_title, twitter_post, threads_post, facebook_post, pinterest_title, pinterest_desc, bluesky_post, hashtags) ПОВИНЕН БУТИ ВИКЛЮЧНО АНГЛІЙСЬКОЮ МОВОЮ (NATURAL AMERICAN ENGLISH)!
Категорично заборонено використовувати українську чи інші мови у заголовках, текстах та хештегах. Навіть якщо відео, аудіо чи початковий текст українською - перекладай, адаптуй та генеруй вірусний англомовний контент для глобальної аудиторії США/Global!

ПРОМПТ КОРИСТУВАЧА ТА SEO-ВКАЗІВКИ:
{prompt}

{"ДОДАТКОВИЙ ТЕКСТ / КЛЮЧОВІ СЛОВА КОРИСТУВАЧА: " + raw_text if raw_text else ""}

ПРАВИЛА ПОШУКОВОЇ ОПТИМІЗАЦІЇ (SOCIAL SEO 2026):
1. ГОЛОВНИЙ ПОШУКОВИЙ ЗАПИТ (Primary Search Query):
   Визнач, яку саме фразу люди вбивають у рядок пошуку на цю тему (наприклад, 'how to automate...', 'best ai tools for...', 'how to build...').
2. ВХОДЖЕННЯ В ПЕРШІ РЯДКИ (Search Bar Match):
   Перші 1-2 речення опису (до 75-100 символів) та заголовки ПОВИННІ містити точний англійський пошуковий запит. TikTok та Instagram використовують саме перші рядки для генерації пошукової підказки у верхньому рядку ('Search: [запит]').
3. LSI-КЛЮЧОВІ СЛОВА ТА СИНОНІМИ:
   Органічно інтегруй 3-5 семантично пов'язаних англійських термінів у тіло тексту. НІЯКОГО переспаму (Keyword Stuffing) - текст має читатися захоплююче, природно і легко!
4. ПОШУКОВИЙ НАМІР (Search Intent) + HOOK:
   Поєднай розв'язання болю/запиту користувача із сильним вірусним хуком та CTA.
5. SEO-ХЕШТЕГИ:
   Використовуй 3-5 цільових англійських хештегів (наприклад, #ai #automation #tech #productivity #chatgpt), а не спам-теги.

КРИТИЧНІ ПРАВИЛА ТИПОГРАФІКИ:
1. СТРОГО ЗАБОРОНЕНО використовувати довге тире '—' або середнє тире '–'!
2. Використовуй ВИКЛЮЧНО звичайний дефіс '-'! Це обов'язково для всіх полів.

ТОЧНІ РОЗРАХУНКИ ТА ЛІМІТИ ДОВЖИНИ (2026):
1. "youtube_title": СТРОГО до 100 символів! Перші 50-60 симв - головний пошуковий запит + чіпкий хук + 3 хештеги (#shorts #viral...).
2. "caption": SEO-опис для TikTok, Instagram Reels / Posts та Telegram. СТРОГО до 2200 символів! Структура: Search Match Hook у першому рядку, корисне тіло з LSI-ключами, CTA, в кінці РІВНО 3-5 релевантних пошукових хештегів.
3. "snapchat_title": СТРОГО до 100 символів! Динамічний пошуковий хук для Gen Z Spotlight.
4. "twitter_post": ОПТИМАЛЬНО 100-240 символів (жорсткий ліміт 280). Лаконічний твіт з головним пошуковим ключем та 1-2 тегами.
5. "threads_post": ОПТИМАЛЬНО 150-400 символів (жорсткий ліміт 500). Живий пост для Threads з пошуковою фразою в першому реченні.
6. "facebook_post": ОПТИМАЛЬНО 300-800 символів (розгорнутий SEO-пост з розкриттям теми).
7. "pinterest_title": СТРОГО до 100 символів! 100% пошуковий заголовок (Search Query) під візуальний пошук.
8. "pinterest_desc": ОПТИМАЛЬНО 200-450 символів (жорсткий ліміт 500). Пошуковий SEO-опис з високою концентрацією цільових ключових слів.
9. "bluesky_post": ОПТИМАЛЬНО 150-250 символів (жорсткий ліміт 300). Лаконічний пост з ключовими словами.
10. "hashtags": Масив із 3-5 цільових пошукових хештегів.

Формат відповіді СТРОГО валідний JSON:
{{
  "youtube_title": "...",
  "caption": "...",
  "snapchat_title": "...",
  "twitter_post": "...",
  "threads_post": "...",
  "facebook_post": "...",
  "pinterest_title": "...",
  "pinterest_desc": "...",
  "bluesky_post": "...",
  "hashtags": ["#tag1", "#tag2", "#tag3"]
}}
"""

        uploaded_files = []
        uploading_client = None
        try:
            contents = [system_instruction]

            if media_paths:
                for p in media_paths:
                    if p.lower().endswith((".mp4", ".mov", ".mkv", ".avi")):
                        if getattr(self, "is_new_sdk", False) and self.client:
                            uploading_client = self.client
                            v_file = uploading_client.files.upload(file=p)
                            while v_file.state == "PROCESSING":
                                time.sleep(2)
                                v_file = uploading_client.files.get(name=v_file.name)
                            contents.append(v_file)
                            uploaded_files.append((uploading_client, v_file.name))
                        else:
                            import google.generativeai as legacy_genai
                            v_file = legacy_genai.upload_file(path=p)
                            while v_file.state.name == "PROCESSING":
                                time.sleep(2)
                                v_file = legacy_genai.get_file(v_file.name)
                            contents.append(v_file)
                    else:
                        try:
                            img = Image.open(p)
                            contents.append(img)
                        except Exception as ie:
                            logger.error(f"Помилка відкриття фото: {ie}")

            response = self.generate_content(
                contents=contents,
                config={"response_mime_type": "application/json"},
                client_override=uploading_client
            )
            if not response or not getattr(response, "text", None):
                raise RuntimeError("Gemini не повернув відповіді")
            text_resp = response.text.strip()

            if text_resp.startswith("```json"):
                text_resp = text_resp[7:]
            if text_resp.endswith("```"):
                text_resp = text_resp[:-3]

            data = json.loads(text_resp.strip())
            return self._normalize_metadata(data)

        except Exception as e:
            logger.error(f"Помилка Gemini: {e}")
            return self._generate_fallback(content_type, raw_text)
        finally:
            for c_obj, fn in uploaded_files:
                try:
                    c_obj.files.delete(name=fn)
                except Exception:
                    pass

    def condense_text(
        self,
        text: str,
        target_platform: str,
        max_chars: int,
        media_paths: Optional[List[str]] = None
    ) -> str:
        """
        Розумне скорочення/переписування завеликого тексту під ліміт символів платформи:
        Зберігає головний пошуковий запит (Search Keyword), гачок та CTA.
        Суворе дотримання правил: тільки '-', жодних довгих '—' або '–'.
        """
        clean_text = sanitize_typography(text).strip()
        if len(clean_text) <= max_chars:
            return clean_text

        if not self.api_key or self.api_key.startswith("AIzaSyYour") or (not self.client and not hasattr(self, "legacy_model")):
            return truncate_at_word_boundary(clean_text, max_chars)

        prompt = f"""
Ти - професійний Social Media SEO-копірайтер.
Скороти та адаптуй наступний текст СТРОГО до {max_chars} символів для платформи {target_platform}.

ВИМОГИ:
1. Збережи головний пошуковий запит (Primary Search Keyword) та сенс проблеми.
2. Збережи вірусний гачок (hook) та заклик до дії (CTA).
3. КРИТИЧНО: ТІЛЬКИ звичайний дефіс '-', НІКОЛИ не вживай довге тире '—' або середнє '–'!
4. Довжина тексту ПОВИННА бути <= {max_chars} символів (включно з пробілами та хештегами).
5. Поверни ВИКЛЮЧНО готовий скорочений текст. Без вступних слів, без лапок, без коментарів.

ВХІДНИЙ ТЕКСТ:
{clean_text}
"""
        try:
            resp = self.generate_content(contents=[prompt])
            if not resp or not getattr(resp, "text", None):
                raise RuntimeError("Gemini не повернув відповіді")
            res_text = resp.text.strip()

            res_text = sanitize_typography(res_text)
            if len(res_text) > max_chars:
                res_text = truncate_at_word_boundary(res_text, max_chars)
            return res_text
        except Exception as e:
            logger.error(f"Помилка скорочення через Gemini: {e}")
            return truncate_at_word_boundary(clean_text, max_chars)

    def condense_all_for_post(
        self,
        raw_text: str,
        media_paths: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """
        Пакетне інтелектуальне скорочення довгого опису під точні ліміти всіх мікроблогів та платформ:
        - X (Twitter): <= 240 симв
        - Threads: <= 400 симв
        - Bluesky: <= 250 симв
        - YouTube Shorts Title: <= 100 симв
        - Pinterest Description: <= 450 симв
        Збереження пошукового фокусу та ключових слів.
        """
        clean_text = sanitize_typography(raw_text).strip()
        if not self.api_key or self.api_key.startswith("AIzaSyYour") or (not self.client and not hasattr(self, "legacy_model")):
            return {
                "twitter_post": truncate_at_word_boundary(clean_text, 240),
                "threads_post": truncate_at_word_boundary(clean_text, 400),
                "bluesky_post": truncate_at_word_boundary(clean_text, 250),
                "youtube_title": truncate_at_word_boundary(clean_text, 100),
                "pinterest_desc": truncate_at_word_boundary(clean_text, 450)
            }

        prompt = f"""
Ти - професійний Social Media SEO-копірайтер.
Перед тобою опис контенту. Адаптуй та стисни його під точні ліміти кожної платформи, зберігаючи головний пошуковий запит та інтригу:
- twitter_post: СТРОГО до 240 символів (з головним ключовиком та 1-2 хештегами)
- threads_post: СТРОГО до 400 символів (з пошуковою темою в першому реченні)
- bluesky_post: СТРОГО до 250 символів
- youtube_title: СТРОГО до 100 символів (пошуковий запит + клікабельний хук)
- pinterest_desc: СТРОГО до 450 символів (SEO опис для розумного пошуку)

КРИТИЧНЕ ПРАВИЛО ТИПОГРАФІКИ:
Використовуй ТІЛЬКИ звичайний дефіс '-'. ЖОДНИХ довгих тире '—' чи середніх '–'!

ВХІДНИЙ ТЕКСТ:
{clean_text}

Формат відповіді СТРОГО валідний JSON:
{{
  "twitter_post": "...",
  "threads_post": "...",
  "bluesky_post": "...",
  "youtube_title": "...",
  "pinterest_desc": "..."
}}
"""
        try:
            resp = self.generate_content(
                contents=[prompt],
                config={"response_mime_type": "application/json"}
            )
            if not resp or not getattr(resp, "text", None):
                raise RuntimeError("Gemini не повернув відповіді")
            t_resp = resp.text.strip()

            if t_resp.startswith("```json"):
                t_resp = t_resp[7:]
            if t_resp.endswith("```"):
                t_resp = t_resp[:-3]

            d = json.loads(t_resp.strip())
            return {
                "twitter_post": truncate_at_word_boundary(sanitize_typography(d.get("twitter_post", "")), 240),
                "threads_post": truncate_at_word_boundary(sanitize_typography(d.get("threads_post", "")), 400),
                "bluesky_post": truncate_at_word_boundary(sanitize_typography(d.get("bluesky_post", "")), 250),
                "youtube_title": truncate_at_word_boundary(sanitize_typography(d.get("youtube_title", "")), 100),
                "pinterest_desc": truncate_at_word_boundary(sanitize_typography(d.get("pinterest_desc", "")), 450)
            }
        except Exception as e:
            logger.error(f"Помилка пакетного скорочення через Gemini: {e}")
            return {
                "twitter_post": truncate_at_word_boundary(clean_text, 240),
                "threads_post": truncate_at_word_boundary(clean_text, 400),
                "bluesky_post": truncate_at_word_boundary(clean_text, 250),
                "youtube_title": truncate_at_word_boundary(clean_text, 100),
                "pinterest_desc": truncate_at_word_boundary(clean_text, 450)
            }

    def _normalize_metadata(self, data: Dict[str, Any]) -> Dict[str, str]:
        yt_title = truncate_at_word_boundary(sanitize_typography(data.get("youtube_title", "")), 100)
        caption = truncate_at_word_boundary(sanitize_typography(data.get("caption", "")), 2200)
        snap_title = truncate_at_word_boundary(sanitize_typography(data.get("snapchat_title", "") or yt_title), 100)
        tw_post = truncate_at_word_boundary(sanitize_typography(data.get("twitter_post", "") or caption), 240)
        th_post = truncate_at_word_boundary(sanitize_typography(data.get("threads_post", "") or caption), 400)
        fb_post = truncate_at_word_boundary(sanitize_typography(data.get("facebook_post", "") or caption), 800)
        pin_title = truncate_at_word_boundary(sanitize_typography(data.get("pinterest_title", "") or yt_title), 100)
        pin_desc = truncate_at_word_boundary(sanitize_typography(data.get("pinterest_desc", "") or caption), 450)
        bsky_post = truncate_at_word_boundary(sanitize_typography(data.get("bluesky_post", "") or caption), 250)
        
        hashtags = data.get("hashtags", [])
        if isinstance(hashtags, list):
            tag_str = " ".join(sanitize_typography(str(t)) for t in hashtags)
        else:
            tag_str = sanitize_typography(str(hashtags))

        return {
            "youtube_title": yt_title,
            "youtube_desc": caption,
            "caption": caption,
            "ig_caption": caption,
            "tt_caption": caption,
            "fb_caption": fb_post,
            "snapchat_title": snap_title,
            "twitter_post": tw_post,
            "threads_post": th_post,
            "pinterest_title": pin_title,
            "pinterest_desc": pin_desc,
            "bluesky_post": bsky_post,
            "hashtags": tag_str
        }

    def _generate_fallback(self, content_type: ContentType, raw_text: Optional[str] = None) -> Dict[str, str]:
        """Генерує надійний локальний фолбек англійською, якщо Gemini API тимчасово недоступний"""
        base_text = sanitize_typography(raw_text).strip() if raw_text else ""
        if not base_text:
            if content_type == ContentType.VIDEO:
                base_text = "Building the future with AI and automated systems. Watch the full breakdown! ⚡️"
            elif content_type in (ContentType.CAROUSEL, ContentType.MIXED_CAROUSEL):
                base_text = "Key insights and top frameworks you need to know today 📸"
            elif content_type == ContentType.PHOTO:
                base_text = "Behind the scenes of modern building and scaling 🚀"
            else:
                base_text = "Quick thought on scaling systems and technology in 2026 💡"

        title = truncate_at_word_boundary(base_text.split("\n")[0], 70)
        default_tags = "#shorts #ai #automation #tech #viral #fyp"

        fallback_data = {
            "youtube_title": title + " #shorts",
            "caption": f"{base_text}\n\n{default_tags}",
            "snapchat_title": title,
            "twitter_post": truncate_at_word_boundary(base_text, 200) + " #tech #ai",
            "threads_post": truncate_at_word_boundary(base_text, 350) + " #automation",
            "facebook_post": f"{base_text}\n\n{default_tags}",
            "pinterest_title": title,
            "pinterest_desc": truncate_at_word_boundary(base_text, 400),
            "bluesky_post": truncate_at_word_boundary(base_text, 220),
            "hashtags": ["#shorts", "#ai", "#automation", "#tech", "#viral"]
        }
        return self._normalize_metadata(fallback_data)

    def analyze_video(self, video_path: str, prompt: str = "") -> Optional[str]:
        """
        Аналізує відеофайл або відео-кружечок за допомогою Gemini Multimodal (новий SDK).
        """
        if not video_path or not os.path.exists(video_path):
            return None
        if not self.client or not getattr(self, "is_new_sdk", False):
            return None

        uploaded = None
        try:
            uploaded = self.client.files.upload(file=video_path)
            # Чекаємо обробки відео якщо потрібно (стан ACTIVE)
            import time
            for _ in range(12):
                file_info = self.client.files.get(name=uploaded.name)
                state = getattr(file_info, "state", None)
                if not state or str(state).upper().endswith("ACTIVE"):
                    break
                elif state and "FAILED" in str(state).upper():
                    logger.warning("Gemini відео обробка не вдалася")
                    return None
                time.sleep(1.0)

            user_prompt = prompt or (
                "Уважно подивися це відео. Опиши коротко і точно (2-3 речення): "
                "що тут відбувається, хто або що в кадрі, яка дія, емоція, смішні чи абсурдні моменти. "
                "Тільки дефіс '-', без довгих тире."
            )
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[uploaded, user_prompt]
            )
            if response and response.text:
                return sanitize_typography(response.text.strip())
        except Exception as e:
            logger.warning(f"Помилка аналізу відео через Gemini: {e}")
        finally:
            if uploaded:
                try:
                    self.client.files.delete(name=uploaded.name)
                except Exception:
                    pass
        return None


gemini_service = GeminiService()

