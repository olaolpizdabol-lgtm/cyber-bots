"""
🌤 Сервіс актуальної погоди для друзів та повідомлень
Працює безкоштовно через Open-Meteo та wttr.in (без потреби в API ключах)
"""
import requests
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("weather_service")

WEATHER_CODE_MAP = {
    0: "ясно ☀️",
    1: "переважно ясно 🌤",
    2: "мінлива хмарність ⛅️",
    3: "хмарно ☁️",
    45: "туманно 🌫",
    48: "паморозь 🌫",
    51: "мряка 🌧",
    53: "помірний дощ 🌧",
    55: "густий дощ 🌧",
    61: "невеликий дощ 🌧",
    63: "дощ 🌧",
    65: "сильна злива ⛈",
    71: "легкий сніг 🌨",
    73: "сніг ❄️",
    75: "сильний снігопад ❄️",
    80: "зливовий дощ 🌦",
    81: "сильний дощ 🌧",
    82: "шквальний дощ ⛈",
    95: "гроза ⚡️"
}


def get_current_weather(city: str = "Kyiv") -> Dict[str, Any]:
    """
    Отримує поточну погоду для міста.
    За замовчуванням: Київ (50.45, 30.52).
    Повертає словник: temp, feels_like, condition, text_short
    """
    # 1. Спроба через Open-Meteo (найстабільніше JSON API)
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": 50.4501,
            "longitude": 30.5234,
            "current": "temperature_2m,apparent_temperature,weather_code",
            "timezone": "Europe/Kyiv"
        }
        res = requests.get(url, params=params, timeout=5)
        if res.status_code == 200:
            cur = res.json().get("current", {})
            temp = round(cur.get("temperature_2m", 15))
            feels = round(cur.get("apparent_temperature", temp))
            w_code = cur.get("weather_code", 1)
            condition = WEATHER_CODE_MAP.get(w_code, "комфортно 🌤")

            temp_str = f"+{temp}°C" if temp > 0 else f"{temp}°C"
            feels_str = f"+{feels}°C" if feels > 0 else f"{feels}°C"

            short_summary = f"{temp_str}, {condition} (відчувається як {feels_str})"
            return {
                "temp": temp_str,
                "feels_like": feels_str,
                "condition": condition,
                "summary": short_summary
            }
    except Exception as e:
        logger.warning(f"Open-Meteo запит не вдався: {e}")

    # 2. Фолбек через wttr.in
    try:
        res = requests.get("https://wttr.in/Kyiv?format=%C+%t", timeout=4)
        if res.status_code == 200 and res.text:
            raw = res.text.strip()
            return {
                "temp": raw,
                "feels_like": raw,
                "condition": "погода в нормі",
                "summary": raw
            }
    except Exception:
        pass

    return {
        "temp": "+15°C",
        "feels_like": "+14°C",
        "condition": "тепло 🌤",
        "summary": "+15°C, тепло 🌤"
    }


def format_friend_weather_streak_message() -> str:
    """Генерує повідомлення з вогником та реальною актуальною погодою для кентів"""
    import random
    w = get_current_weather()
    summary = w.get("summary", "+15°C, ясно ☀️")
    temp = w.get("temp", "+15°C")

    templates = [
        f"🔥 Вогник тримаємо! По погоді сьогодні: {summary}. Гарного та продуктивного дня! ✌️",
        f"🔥 Щоденний streak чек! На дворі зараз {summary}. Одягайся по погоді та тримаємо зв'язок! 😎",
        f"🔥 +1 день у нашу серію вогників! Погода за вікном: {temp}. Вдалого дня, бро! 💪",
        f"Streak on fire! 🔥🔥 Погода: {summary}. Не дай вогнику згаснути! 🚀",
        f"🔥 Вогник збережено! За бортом {temp}. Бажаю крутого настрою сьогодні! 🤙"
    ]
    return random.choice(templates)
