import logging
import urllib.parse
from typing import Dict, Any, Optional, Tuple, List
import requests
from config import US_NY_PROXY_URL, STRICT_PROXY_CHECK

logger = logging.getLogger(__name__)

# Платформи, критично залежні від IP для охоплення США та захисту від тіньового бану:
# - TikTok: Алгоритм жорстко прив'язує країну пушу до IP, ASN та SIM. Невідповідний або dirty-датацентр IP дає 0 переглядів (shadowban).
# - Instagram (Reels): Meta перевіряє геолокацію та раптові зміни IP, викликає чекпоінти та песимізує Reels.
# - Facebook: Спільний антифрод-рушій Meta.
# - Snapchat Spotlight: Виплати та покази в Spotlight доступні тільки для цільових гео (США).
# - Threads: Пов'язаний з Meta trust-score акаунтом.
IP_DEPENDENT_PLATFORMS: List[str] = ["tiktok", "instagram", "facebook", "snapchat", "threads"]

# Платформи, яким проксі НЕ потрібен (або протипоказаний):
# - YouTube Shorts: Google OAuth2. Ротаційні або публічні проксі викликають підозрілі входи і скидання refresh_token!
# - Bluesky: Децентралізований відкритий AT Protocol.
# - Telegram: Офіційний Bot API.
# - Pinterest / X (Twitter): Офіційні API-ключі без жорсткої геолокаційної дискримінації.
DIRECT_PLATFORMS: List[str] = ["youtube", "bluesky", "telegram", "pinterest", "twitter"]

PLATFORM_IP_DETAILS: Dict[str, Dict[str, str]] = {
    "tiktok": {
        "requirement": "US (New York) Residential / Clean ISP IP",
        "risk": "При завантаженні без US IP відео показуються тільки в регіоні заливу (Україна/Європа) замість аудиторії США. Публічні проксі призводять до вічного 0 переглядів (тіньовий бан).",
        "category": "Критично залежний"
    },
    "instagram": {
        "requirement": "US (New York) Static / Clean IP",
        "risk": "Meta anti-fraud фіксує зміну геолокації та кидає акаунт на SMS/Email checkpoint, або песимізує охоплення Reels у рекомендаціях США.",
        "category": "Критично залежний"
    },
    "facebook": {
        "requirement": "US (New York) IP",
        "risk": "Спільний з Instagram алгоритм оцінки ризику сесії та акаунту.",
        "category": "Критично залежний"
    },
    "snapchat": {
        "requirement": "US IP",
        "risk": "Spotlight алгоритм відсікає не-US відео від американської стрічки рекомендацій.",
        "category": "Критично залежний"
    },
    "threads": {
        "requirement": "US IP",
        "risk": "Успадковує Meta trust-score безпосередньо з Instagram.",
        "category": "Критично залежний"
    },
    "youtube": {
        "requirement": "Direct / Незмінний IP",
        "risk": "Google OAuth2 токени скидаються при зміні IP через проксі (помилка 'Suspicious activity'). Заливати ТІЛЬКИ напряму!",
        "category": "Пряме підключення"
    },
    "bluesky": {
        "requirement": "Direct / Open AT Protocol",
        "risk": "Відкритий протокол без гео-обмежень.",
        "category": "Пряме підключення"
    },
    "twitter": {
        "requirement": "Direct / API v2",
        "risk": "Офіційний API без гео-блокувань.",
        "category": "Пряме підключення"
    },
    "pinterest": {
        "requirement": "Direct",
        "risk": "API/Сесія без суворої гео-прив'язки.",
        "category": "Пряме підключення"
    },
    "telegram": {
        "requirement": "Direct Bot API",
        "risk": "Офіційний Telegram API працює напряму на серверах MTProto.",
        "category": "Пряме підключення"
    }
}


class ProxyManager:
    def __init__(self):
        self.proxy_url = US_NY_PROXY_URL
        self.strict_check = STRICT_PROXY_CHECK

    def is_platform_ip_dependent(self, platform: str) -> bool:
        """Перевіряє, чи потрібен обов'язковий US проксі для платформи"""
        return platform.lower() in IP_DEPENDENT_PLATFORMS

    def get_requests_proxies(self) -> Optional[Dict[str, str]]:
        """
        Повертає словник проксі для бібліотеки requests.
        Для SOCKS5 автоматично нормалізує до socks5h://, щоб запобігти DNS-витоку (DNS leak),
        завдяки чому DNS запити резолвляться безпосередньо на стороні New York проксі.
        """
        if not self.proxy_url:
            return None

        url = self.proxy_url
        if url.startswith("socks5://"):
            url = url.replace("socks5://", "socks5h://", 1)

        return {
            "http": url,
            "https": url
        }

    def get_playwright_proxy(self) -> Optional[Dict[str, str]]:
        if not self.proxy_url:
            return None
        parsed = urllib.parse.urlparse(self.proxy_url)
        # Chromium не підтримує аутентифікацію для SOCKS5 (Browser does not support socks5 proxy authentication).
        # Якщо вказано логін/пароль для socks5/socks5h, перемикаємо схему на http (Webshare та більшість проксі підтримують обидва протоколи на тому ж порту).
        if parsed.username and parsed.scheme.startswith("socks"):
            scheme = "http"
        else:
            scheme = parsed.scheme.replace("socks5h", "socks5")

        proxy_config = {
            "server": f"{scheme}://{parsed.hostname}:{parsed.port}"
        }
        if parsed.username:
            proxy_config["username"] = urllib.parse.unquote(parsed.username)
        if parsed.password:
            proxy_config["password"] = urllib.parse.unquote(parsed.password)
        return proxy_config

    def check_proxy_health(self) -> Dict[str, Any]:
        """
        Перевіряє реальну вихідну IP-адресу, країну та місто через проксі.
        Переконується що це дійсно США (New York).
        """
        if not self.proxy_url:
            return {
                "ok": False,
                "ip": "Direct Server IP",
                "country": "Unknown",
                "city": "Unknown",
                "region": "Unknown",
                "isp": "Unknown",
                "is_us": False,
                "is_ny": False,
                "message": "⚠️ Проксі не налаштовано! (US_NY_PROXY_URL пустий)"
            }

        proxies = self.get_requests_proxies()
        try:
            resp = requests.get(
                "http://ip-api.com/json?fields=status,message,country,countryCode,region,regionName,city,isp,query",
                proxies=proxies,
                timeout=12
            )
            data = resp.json()
            if data.get("status") == "success":
                ip = data.get("query", "")
                country_code = data.get("countryCode", "")
                country = data.get("country", "")
                region_name = data.get("regionName", "")
                region_code = data.get("region", "")
                city = data.get("city", "")
                isp = data.get("isp", "")

                is_us = country_code.upper() == "US"
                is_ny = "NEW YORK" in city.upper() or "NEW YORK" in region_name.upper() or region_code == "NY"

                status_ok = is_us and is_ny
                msg = "✅ US (New York) проксі активний та надійний!" if status_ok else (
                    f"⚠️ Проксі працює, але локація: {city}, {country} (бажано саме New York, US)"
                )

                return {
                    "ok": is_us,
                    "ip": ip,
                    "country": country,
                    "city": city,
                    "region": region_name,
                    "isp": isp,
                    "is_us": is_us,
                    "is_ny": is_ny,
                    "message": msg
                }
            else:
                return {
                    "ok": False,
                    "ip": "Error",
                    "country": "",
                    "city": "",
                    "region": "",
                    "isp": "",
                    "is_us": False,
                    "is_ny": False,
                    "message": f"❌ Помилка перевірки проксі: {data.get('message')}"
                }
        except Exception as e:
            logger.error(f"Помилка підключення до проксі: {e}")
            return {
                "ok": False,
                "ip": "Offline",
                "country": "",
                "city": "",
                "region": "",
                "isp": "",
                "is_us": False,
                "is_ny": False,
                "message": f"❌ Не вдалося підключитися до проксі: {str(e)}"
            }

    def verify_platform_safety(self, platform: str) -> Tuple[bool, str]:
        """
        Pre-flight перевірка безпеки перед публікацією:
        - Для IP-залежних мереж (TikTok, Instagram, Facebook, Snapchat, Threads) перевіряє стан проксі.
        - Якщо STRICT_PROXY_CHECK активний і проксі не надійний, блокує публікацію для захисту акаунту від бану.
        - Для прямих мереж (YouTube, Bluesky, Telegram) дозволяє пряме підключення.
        """
        plat = platform.lower()
        if not self.is_platform_ip_dependent(plat):
            return True, "✅ Пряме безпечне підключення через офіційний API."

        health = self.check_proxy_health()
        if not health["ok"]:
            if self.strict_check:
                return False, (
                    f"⛔️ ЗАХИСТ ВІД БАНУ: Для {platform.upper()} обов'язковий US проксі! "
                    f"Поточний статус: {health['message']}. Публікацію зупинено."
                )
            else:
                return True, f"⚠️ ПОПЕРЕДЖЕННЯ: {health['message']}. Охоплення в США може постраждати."

        if not health.get("is_ny"):
            return True, f"⚠️ US проксі активний ({health.get('city')}, {health.get('country')}). Рекомендується саме New York."

        return True, f"🛡 Безпечно: New York IP активний ({health.get('ip')}, ISP: {health.get('isp')})."

    @staticmethod
    def get_free_proxy_guide() -> str:
        """
        Інструкція з налаштування 100% безкоштовного New York IP без ризику витоку сесій
        """
        return """
🗽 <b>Як отримати 100% БЕЗКОШТОВНИЙ New York IP для TikTok та Instagram:</b>

1. <b>Варіант 1: Webshare.io (Найпростіший, 0 грн / назавжди)</b>
   • Зареєструйтесь на <code>https://www.webshare.io/</code> (без карти!)
   • Отримайте 10 безкоштовних приватних проксі (SOCKS5 / HTTP)
   • У фільтрах виберіть країну <b>United States</b>
   • Скопіюйте посилання: <code>socks5://username:password@ip:port</code>
   • Вставте в <code>.env</code> у рядок <code>US_NY_PROXY_URL</code>

2. <b>Варіант 2: Власний безкоштовний сервер у New York (Fly.io Free Tier)</b>
   • Fly.io дає 3 безкоштовні мікро-сервери назавжди.
   • Регіон <code>ewr</code> (Secaucus / Newark) знаходиться безпосередньо біля Нью-Йорка.
   • Запустіть 1-кліком власний приватний SOCKS5 проксі (інструкція в <code>scripts/setup_free_ny_proxy.md</code>).
   • <b>Перевага:</b> 100% чистий персональний IP, нуль шансів на блокування чи перехоплення даних.

3. <b>Варіант 3: Cloudflare WARP (Zero-Cost WireGuard)</b>
   • Безкоштовний офіційний клієнт Cloudflare WARP з точкою виходу в US East.
"""


proxy_manager = ProxyManager()
