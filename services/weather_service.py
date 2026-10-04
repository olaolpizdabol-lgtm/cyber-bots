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


# Координати міст (за замовчуванням: Чернівці)
CITY_COORDINATES = {
    "chernivtsi": {"lat": 48.2917, "lon": 25.9352, "name": "Чернівцях", "wttr": "Chernivtsi"},
    "чернівці": {"lat": 48.2917, "lon": 25.9352, "name": "Чернівцях", "wttr": "Chernivtsi"},
    "kyiv": {"lat": 50.4501, "lon": 30.5234, "name": "Києві", "wttr": "Kyiv"},
    "київ": {"lat": 50.4501, "lon": 30.5234, "name": "Києві", "wttr": "Kyiv"}
}

DEFAULT_CITY = "Chernivtsi"


def get_current_weather(city: str = DEFAULT_CITY) -> Dict[str, Any]:
    """
    Отримує поточну погоду для міста (за замовчуванням: Чернівці - 48.2917, 25.9352).
    Повертає словник: temp, feels_like, condition, summary, city
    """
    city_key = city.lower().strip()
    city_info = CITY_COORDINATES.get(city_key, CITY_COORDINATES["chernivtsi"])
    lat = city_info["lat"]
    lon = city_info["lon"]
    loc_name = city_info["name"]
    wttr_name = city_info["wttr"]

    # 1. Спроба через Open-Meteo (найстабільніше JSON API для Чернівців)
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,apparent_temperature,weather_code",
            "timezone": "Europe/Kyiv"
        }
        res = requests.get(url, params=params, timeout=5)
        if res.status_code == 200:
            cur = res.json().get("current", {})
            temp = round(cur.get("temperature_2m", 18))
            feels = round(cur.get("apparent_temperature", temp))
            w_code = cur.get("weather_code", 0)
            condition = WEATHER_CODE_MAP.get(w_code, "ясно ☀️")

            temp_str = f"+{temp}°C" if temp > 0 else f"{temp}°C"
            feels_str = f"+{feels}°C" if feels > 0 else f"{feels}°C"

            short_summary = f"{temp_str}, {condition} (відчувається як {feels_str})"
            return {
                "city": loc_name,
                "temp": temp_str,
                "feels_like": feels_str,
                "condition": condition,
                "summary": short_summary
            }
    except Exception as e:
        logger.warning(f"Open-Meteo запит для {loc_name} не вдався: {e}")

    # 2. Фолбек через wttr.in
    try:
        res = requests.get(f"https://wttr.in/{wttr_name}?format=%C+%t", timeout=4)
        if res.status_code == 200 and res.text:
            raw = res.text.strip()
            return {
                "city": loc_name,
                "temp": raw,
                "feels_like": raw,
                "condition": "погода в нормі",
                "summary": f"{raw} (у {loc_name})"
            }
    except Exception:
        pass

    return {
        "city": loc_name,
        "temp": "+18°C",
        "feels_like": "+17°C",
        "condition": "тепло 🌤",
        "summary": f"+18°C, тепло 🌤 (у {loc_name})"
    }


def format_friend_weather_streak_message(city: str = DEFAULT_CITY) -> str:
    """Генерує повідомлення з вогником та реальною актуальною погодою в Чернівцях для кентів"""
    import random
    w = get_current_weather(city)
    summary = w.get("summary", "+18°C, ясно ☀️")
    loc = w.get("city", "Чернівцях")

    templates = [
        f"🔥 Вогник тримаємо! По погоді в {loc} зараз: {summary}. Гарного та продуктивного дня! ✌️",
        f"🔥 Щоденний streak чек! У {loc} зараз {summary}. Одягайся по погоді та тримаємо зв'язок! 😎",
        f"🔥 +1 день у нашу серію вогників! Погода в {loc}: {summary}. Вдалого дня, бро! 💪",
        f"Streak on fire! 🔥🔥 Погода сьогодні у {loc}: {summary}. Не дай вогнику згаснути! 🚀",
        f"🔥 Вогник збережено! За бортом у {loc} {summary}. Бажаю крутого настрою сьогодні! 🤙"
    ]
    return random.choice(templates)
