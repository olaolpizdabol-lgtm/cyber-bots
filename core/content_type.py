from enum import Enum
from typing import List, Dict, Any, Tuple


class ContentType(str, Enum):
    VIDEO = "video"                   # Вертикальне коротке відео (9:16)
    PHOTO = "photo"                   # Одиночне фото / зображення
    CAROUSEL = "carousel"             # Карусель тільки фото (Photo Mode / Слайди)
    MIXED_CAROUSEL = "mixed_carousel" # Карусель мікс: фото + короткі відео
    TEXT = "text"                     # Текстовий пост / думка / тред


# Детальні технічні ліміти та розрахунки під кожну платформу (2026)
PLATFORM_CONSTRAINTS: Dict[str, Dict[str, Any]] = {
    "tiktok": {
        "name": "TikTok",
        "supported_formats": [ContentType.VIDEO, ContentType.CAROUSEL],
        "max_slides": 35,             # Photo Mode до 35 фото з музикою
        "mixed_allowed": False,       # Photo Mode тільки для фото (без відео!)
        "max_video_sec": 600,         # до 10 хв
        "optimal_video_sec": (21, 90),
        "caption_limit": 2200,        # до 2200 симв опис
        "optimal_aspect": "9:16",
    },
    "instagram": {
        "name": "Instagram Reels & Feed",
        "supported_formats": [ContentType.VIDEO, ContentType.PHOTO, ContentType.CAROUSEL, ContentType.MIXED_CAROUSEL],
        "max_slides": 10,             # до 10 (API) / 20 (app)
        "mixed_allowed": True,        # Підтримує мікс фото + відео!
        "max_video_sec": 180,         # Reels до 3 хв (в app до 20)
        "optimal_video_sec": (30, 60),
        "caption_limit": 2200,
        "optimal_aspect_photo": "4:5", # 1080x1350 для стрічки
        "optimal_aspect_video": "9:16",
    },
    "youtube": {
        "name": "YouTube Shorts",
        "supported_formats": [ContentType.VIDEO],
        "max_slides": 0,
        "mixed_allowed": False,
        "max_video_sec": 180,         # Shorts до 3 хв
        "optimal_video_sec": (30, 60),
        "title_limit": 100,           # Назва до 100 симв з 3-5 хештегами
        "desc_limit": 2000,
        "optimal_aspect": "9:16",
    },
    "facebook": {
        "name": "Facebook Reels & Page",
        "supported_formats": [ContentType.VIDEO, ContentType.PHOTO, ContentType.CAROUSEL, ContentType.TEXT],
        "max_slides": 10,             # Карусель до 10 фото
        "mixed_allowed": False,
        "max_video_sec": 600,
        "optimal_video_sec": (30, 90),
        "caption_limit": 63000,
        "optimal_text_len": (300, 800), # Оптимально для тексту 300-800 симв
        "optimal_aspect_photo": "1:1",
        "optimal_aspect_video": "9:16",
    },
    "snapchat": {
        "name": "Snapchat Spotlight",
        "supported_formats": [ContentType.VIDEO],
        "max_slides": 0,
        "mixed_allowed": False,
        "max_video_sec": 180,
        "optimal_video_sec": (15, 30),
        "title_limit": 100,
        "optimal_aspect": "9:16",
    },
    "twitter": {
        "name": "X (Twitter)",
        "supported_formats": [ContentType.VIDEO, ContentType.PHOTO, ContentType.CAROUSEL, ContentType.TEXT],
        "max_slides": 4,              # СТРОГО до 4 зображень!
        "mixed_allowed": False,       # Не можна змішувати відео і фото в 1 твіті!
        "max_video_sec": 140,         # 2 хв 20 сек (free)
        "optimal_video_sec": (15, 60),
        "caption_limit": 280,
        "optimal_text_len": (100, 240), # Оптимальна довжина твіту 100-240 симв
        "optimal_aspect_photo": "16:9",
    },
    "threads": {
        "name": "Threads",
        "supported_formats": [ContentType.VIDEO, ContentType.PHOTO, ContentType.CAROUSEL, ContentType.MIXED_CAROUSEL, ContentType.TEXT],
        "max_slides": 10,             # до 10-20 слайдів
        "mixed_allowed": True,        # Підтримує мікс фото + відео!
        "max_video_sec": 300,         # до 5 хв
        "optimal_video_sec": (15, 60),
        "caption_limit": 500,
        "optimal_text_len": (150, 400), # Оптимально 150-400 симв
        "optimal_aspect_photo": "4:5",
        "optimal_aspect_video": "9:16",
    },
    "pinterest": {
        "name": "Pinterest",
        "supported_formats": [ContentType.VIDEO, ContentType.PHOTO, ContentType.CAROUSEL, ContentType.MIXED_CAROUSEL],
        "max_slides": 5,              # Idea Pins мульти-сторінки
        "mixed_allowed": True,
        "max_video_sec": 900,         # до 15 хв
        "optimal_video_sec": (15, 60),
        "title_limit": 100,
        "desc_limit": 500,
        "optimal_aspect_photo": "2:3", # 1000x1500 класика платформи!
        "optimal_aspect_video": "9:16",
    },
    "bluesky": {
        "name": "Bluesky",
        "supported_formats": [ContentType.VIDEO, ContentType.PHOTO, ContentType.CAROUSEL, ContentType.TEXT],
        "max_slides": 4,              # СТРОГО до 4 фото!
        "mixed_allowed": False,
        "max_video_sec": 120,
        "optimal_video_sec": (15, 60),
        "caption_limit": 300,
        "optimal_text_len": (150, 250), # Оптимально 150-250 симв
    },
    "telegram": {
        "name": "Telegram Channel",
        "supported_formats": [ContentType.VIDEO, ContentType.PHOTO, ContentType.CAROUSEL, ContentType.MIXED_CAROUSEL, ContentType.TEXT],
        "max_slides": 10,             # Альбом до 10 елементів
        "mixed_allowed": True,        # Підтримує мікс фото + відео!
        "caption_limit": 1024,
        "text_limit": 4096,
    }
}


def get_supported_platforms_for_format(content_type: ContentType) -> List[str]:
    """Повертає список платформ, що реально підтримують даний формат"""
    supported = []
    for plat_key, config in PLATFORM_CONSTRAINTS.items():
        if content_type in config.get("supported_formats", []):
            supported.append(plat_key)
    return supported


FORMAT_SUPPORTED_PLATFORMS = {
    ContentType.VIDEO: get_supported_platforms_for_format(ContentType.VIDEO),
    ContentType.PHOTO: get_supported_platforms_for_format(ContentType.PHOTO),
    ContentType.CAROUSEL: get_supported_platforms_for_format(ContentType.CAROUSEL),
    ContentType.MIXED_CAROUSEL: get_supported_platforms_for_format(ContentType.MIXED_CAROUSEL),
    ContentType.TEXT: get_supported_platforms_for_format(ContentType.TEXT)
}

FORMAT_TITLES = {
    ContentType.VIDEO: "🎬 Вертикальне відео (9:16)",
    ContentType.PHOTO: "📸 Одиночне фото / Зображення",
    ContentType.CAROUSEL: "📚 Фото-карусель (Photo Mode)",
    ContentType.MIXED_CAROUSEL: "🎞 Мікс-карусель (Фото + Відео)",
    ContentType.TEXT: "📝 Текстовий пост / Тред"
}
