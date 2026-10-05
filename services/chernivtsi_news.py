"""
🌆 Сервіс цікавих та позитивних новин Чернівців
Отримує актуальні новини з перевірених джерел (Google News, molbuk.ua),
фільтрує сумні та військові теми та генерує живі повідомлення для друзів.
"""
import os
import json
import logging
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional
from config import DATA_DIR
from services.weather_service import get_current_weather
from services.gemini_ai import gemini_service, sanitize_typography

logger = logging.getLogger("chernivtsi_news")

FORBIDDEN_KEYWORDS = [
    "загинув", "загинули", "помер", "померли", "похорон", "прощання", "війн",
    "збір", "зсу", "дрон", "втрат", "ракет", "обстріл", "шахед", "поране",
    "траур", "вбито", "вбивств", "труп", "кримінал", "вибух", "суд", "вирок",
    "засудили", "шахрай", "крадіж", "пограбува", "травмувал"
]

SENT_NEWS_FILE = DATA_DIR / "chernivtsi_sent_news.json"


def fetch_chernivtsi_headlines(limit: int = 25) -> List[Dict[str, str]]:
    """Отримує свіжі заголовки новин з Чернівців через RSS"""
    headlines = []
    
    # 1. Google News RSS Чернівці
    try:
        url = "https://news.google.com/rss/search?q=%D0%A7%D0%B5%D1%80%D0%BD%D1%96%D0%B2%D1%86%D1%96&hl=uk&gl=UA&ceid=UA:uk"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            root = ET.fromstring(resp.read())
            for item in root.findall(".//item"):
                title = item.find("title")
                link = item.find("link")
                if title is not None and title.text:
                    t_text = title.text.strip()
                    l_text = link.text.strip() if link is not None and link.text else ""
                    headlines.append({"title": t_text, "link": l_text})
    except Exception as e:
        logger.warning(f"Не вдалося отримати Google News для Чернівців: {e}")

    # 2. Molodiy Bukovynets RSS
    try:
        url_molbuk = "https://molbuk.ua/rss.xml"
        req = urllib.request.Request(url_molbuk, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            root = ET.fromstring(resp.read())
            for item in root.findall(".//item"):
                title = item.find("title")
                link = item.find("link")
                if title is not None and title.text:
                    t_text = title.text.strip()
                    l_text = link.text.strip() if link is not None and link.text else ""
                    headlines.append({"title": t_text, "link": l_text})
    except Exception as e:
        logger.warning(f"Не вдалося отримати molbuk.ua RSS: {e}")

    # Фільтруємо за забороненими сумними словами
    filtered = []
    seen = set()
    for h in headlines:
        raw_lower = h["title"].lower()
        if any(fk in raw_lower for fk in FORBIDDEN_KEYWORDS):
            continue
        if raw_lower not in seen:
            seen.add(raw_lower)
            filtered.append(h)

    return filtered[:limit]


def get_sent_news_titles() -> List[str]:
    """Повертає список вже відправлених новин, щоб не повторюватись"""
    if SENT_NEWS_FILE.exists():
        try:
            return json.loads(SENT_NEWS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def mark_news_as_sent(title: str):
    """Зберігає новину як відправлену"""
    sent = get_sent_news_titles()
    sent.append(title)
    try:
        SENT_NEWS_FILE.write_text(json.dumps(sent[-200:], ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def generate_friend_news_and_weather_message() -> str:
    """
    Генерує живе щоденне повідомлення для друга в TikTok:
    - Реальна погода в Чернівцях
    - Цікава, позитивна або нейтральна свіжа міська новина (без сумних тем, війни та зборів)
    - Дружній вайб у стилі Боді з емодзі вогника 🔥
    """
    weather = get_current_weather("Chernivtsi")
    weather_summary = weather.get("summary", "+18°C, тепло 🌤")
    loc_name = weather.get("city", "Чернівцях")

    candidates = fetch_chernivtsi_headlines(limit=25)
    sent_already = set(get_sent_news_titles())
    fresh_candidates = [c for c in candidates if c["title"] not in sent_already]
    if not fresh_candidates:
        fresh_candidates = candidates

    candidates_text = "\n".join([f"- {c['title']}" for c in fresh_candidates[:12]])

    if gemini_service.api_key and not gemini_service.api_key.startswith("AIzaSyYour") and gemini_service.client and candidates_text:
        prompt = f"""
Ти - Бодя, молодий хлопець з Чернівців. Напиши коротке (2-3 речення) повідомлення кенту/другу в TikTok для щоденного вогника (streak).

ДАНІ:
1. Погода в Чернівцях зараз: {weather_summary}
2. Свіжі заголовки новин з Чернівців:
{candidates_text}

КРИТИЧНО ВАЖЛИВІ ПРАВИЛА:
1. ОБОВ'ЯЗКОВО обери ОДНУ цікаву, позитивну, нейтральну або курйозну міську новину (подія в місті, свято, підсвітка будівель, цікавинки природи чи транспорту, життя міста).
2. СУВОРО ЗАБОРОНЕНО: війна, похорони, загиблі, ДТП з жертвами, збори коштів на армію, кримінал, трагедії! Тільки позитив, міське життя чи нейтральний цікавий факт.
3. Згадай реальну погоду в Чернівцях ({weather_summary}).
4. СТИЛЬ: дружній, живий, розмовний вайб ("бро", "йоу", "чуєш", "тримай вогник").
5. Обов'язково емодзі вогника 🔥.
6. СТРОГО: тільки дефіс '-', жодних довгих тире.
7. Поверни ТІЛЬКИ готовий текст повідомлення без лапок і вступних слів.
"""
        try:
            resp = gemini_service.generate_content([prompt])
            if resp and getattr(resp, "text", None):
                clean_text = sanitize_typography(resp.text.strip())
                if clean_text:
                    if fresh_candidates:
                        mark_news_as_sent(fresh_candidates[0]["title"])
                    return clean_text
        except Exception as e:
            logger.warning(f"Gemini генерація новин не вдалася: {e}")

    # Фолбек якщо ШІ тимчасово недоступний
    fallback_news = fresh_candidates[0]["title"] if fresh_candidates else "місто живе своїм ритмом та готує нові круті локації"
    if fresh_candidates:
        mark_news_as_sent(fresh_candidates[0]["title"])
    return sanitize_typography(
        f"🔥 Вогник тримаємо! Погода в {loc_name} зараз: {weather_summary}. "
        f"До речі, з міських новин: {fallback_news}. Гарного дня, бро! ✌️"
    )
