from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from typing import List, Optional
from core.content_type import ContentType, FORMAT_SUPPORTED_PLATFORMS

def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Постійна клавіатура з великими кнопками внизу екрана (завжди видима)"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚀 Пост на ВСІ платформи (YT+IG+TT+TG)")],
            [KeyboardButton(text="🔥 TikTok Вогники"), KeyboardButton(text="📊 Перегляди / Статистика")],
            [KeyboardButton(text="🤖 Головне меню"), KeyboardButton(text="🌐 Перевірити Проксі")]
        ],
        resize_keyboard=True,
        persistent=True
    )

PLATFORM_EMOJIS = {
    "youtube": "🔴 Shorts",
    "instagram": "🟣 Instagram",
    "tiktok": "⚫️ TikTok",
    "facebook": "🔵 Facebook",
    "snapchat": "🟡 Snapchat",
    "twitter": "𝕏 Twitter",
    "threads": "🧵 Threads",
    "pinterest": "📌 Pinterest",
    "bluesky": "🦋 Bluesky",
    "telegram": "💬 TG Канал"
}


def get_publish_keyboard(post_id: int, content_type: ContentType, has_issues: bool = False) -> InlineKeyboardMarkup:
    """Генерує клавіатуру публікації залежно від формату контенту та наявності проблем"""
    supported = FORMAT_SUPPORTED_PLATFORMS.get(content_type, [])
    buttons = []

    # Головна кнопка (з підтвердженням якщо виявлено проблему)
    if has_issues:
        buttons.append([
            InlineKeyboardButton(
                text="⚠️ Так, залити як є (у всі сумісні)",
                callback_data=f"pub_compat:{post_id}"
            )
        ])
        if content_type == ContentType.VIDEO:
            buttons.append([
                InlineKeyboardButton(
                    text="🛠 Оптимізувати (1080x1920 / H.264)",
                    callback_data=f"opt_fix:{post_id}"
                )
            ])
    else:
        buttons.append([
            InlineKeyboardButton(
                text=f"🚀 Опублікувати у всі сумісні ({len(supported)} платформ)",
                callback_data=f"pub_compat:{post_id}"
            )
        ])

    # Якщо це відео - додаємо швидку кнопку для Рівня 1 (Top 5)
    if content_type == ContentType.VIDEO:
        top5_text = "🔥 Рівень 1 (як є: TT, IG, YT, FB, Snap)" if has_issues else "🔥 Рівень 1 (Top 5: TT, IG, YT, FB, Snap)"
        buttons.append([
            InlineKeyboardButton(
                text=top5_text,
                callback_data=f"pub_tier1:{post_id}"
            )
        ])

    # Кнопки для кожної підтримуваної платформи рядами по 3
    platform_rows = []
    current_row = []
    for p in supported:
        name = PLATFORM_EMOJIS.get(p, p.capitalize())
        current_row.append(InlineKeyboardButton(text=name, callback_data=f"pub_p:{post_id}:{p}"))
        if len(current_row) == 3:
            platform_rows.append(current_row)
            current_row = []
    if current_row:
        platform_rows.append(current_row)

    buttons.extend(platform_rows)

    # Опція скорочення тексту під ліміти символів
    buttons.append([
        InlineKeyboardButton(
            text="✂️ Скоротити тексти (X / Threads / Bluesky)",
            callback_data=f"cond_menu:{post_id}"
        )
    ])

    # Дії: Перегенерація та скасування
    buttons.append([
        InlineKeyboardButton(text="🔄 Перегенерувати", callback_data=f"regen:{post_id}"),
        InlineKeyboardButton(text="❌ Скасувати", callback_data=f"cancel:{post_id}")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_condense_keyboard(post_id: int) -> InlineKeyboardMarkup:
    """Клавіатура вибору платформи для адаптивного скорочення тексту через Gemini"""
    buttons = [
        [
            InlineKeyboardButton(text="𝕏 X (до 240 симв)", callback_data=f"cond_p:{post_id}:twitter:240"),
            InlineKeyboardButton(text="🧵 Threads (до 400 симв)", callback_data=f"cond_p:{post_id}:threads:400")
        ],
        [
            InlineKeyboardButton(text="🦋 Bluesky (до 250 симв)", callback_data=f"cond_p:{post_id}:bluesky:250"),
            InlineKeyboardButton(text="🔴 Shorts назва (до 100 симв)", callback_data=f"cond_p:{post_id}:youtube:100")
        ],
        [
            InlineKeyboardButton(text="✨ Скоротити все разом (AI Auto)", callback_data=f"cond_all:{post_id}")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад до публікації", callback_data=f"back_pub:{post_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Головне меню"""
    buttons = [
        [
            InlineKeyboardButton(
                text="🔥 TikTok Вогники & Дівчина (Автоматизація #2)",
                callback_data="menu_streaks"
            )
        ],
        [
            InlineKeyboardButton(
                text="🤖 Кібер Рижий (Groq 120B & Пам'ять)",
                callback_data="menu_cyber_rizhyi"
            ),
            InlineKeyboardButton(
                text="🎬 Реакція на TikTok (Стиль Боді)",
                callback_data="menu_tiktok_react"
            )
        ],
        [
            InlineKeyboardButton(
                text="🚀 Пост на ВСІ платформи (YT+IG+TT+TG)",
                callback_data="menu_crosspost"
            )
        ],
        [
            InlineKeyboardButton(
                text="📊 Перегляди останнього відео / поста",
                callback_data="menu_stats"
            )
        ],
        [
            InlineKeyboardButton(
                text="🌐 Перевірити US/NY Проксі",
                callback_data="menu_proxy"
            ),
            InlineKeyboardButton(
                text="🛡 Безпека та Аудит",
                callback_data="menu_security"
            )
        ],
        [
            InlineKeyboardButton(
                text="🗽 Гайд: Безкоштовний US/NY IP",
                callback_data="menu_free_proxy"
            ),
            InlineKeyboardButton(
                text="⚙️ Промпт Gemini",
                callback_data="menu_prompt"
            )
        ],
        [
            InlineKeyboardButton(
                text="📜 Останні публікації",
                callback_data="menu_history"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_publish_result_keyboard(post_id: int, has_failures: bool = False) -> InlineKeyboardMarkup:
    """Клавіатура після публікації з можливістю дозаливу на невдалих мережах"""
    buttons = []
    if has_failures:
        buttons.append([
            InlineKeyboardButton(text="🔄 Повторити публікацію на невдалих мережах", callback_data=f"retry_failed:{post_id}")
        ])
    buttons.append([
        InlineKeyboardButton(text="📊 Детальна аналітика поста", callback_data=f"post_analytics:{post_id}"),
        InlineKeyboardButton(text="◀️ Головне меню", callback_data="menu_back")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_streak_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню керування Автоматизацією #2 (TikTok Вогники)"""
    buttons = [
        [
            InlineKeyboardButton(text="🚀 Відправити всім вогники зараз", callback_data="streak_run_now")
        ],
        [
            InlineKeyboardButton(text="⚠️ Перевірити термінові вогники", callback_data="streak_decay_check")
        ],
        [
            InlineKeyboardButton(text="👸 Акаунт дівчини (Сердечка ❤️)", callback_data="streak_set_gf"),
            InlineKeyboardButton(text="💖 Тест повідомлення для неї", callback_data="streak_preview_gf")
        ],
        [
            InlineKeyboardButton(text="⚡️ Відповісти на скинуті TikTok відео (Gemini)", callback_data="streak_check_incoming_videos"),
            InlineKeyboardButton(text="🎬 Реакція по лінку", callback_data="streak_tiktok_react")
        ],
        [
            InlineKeyboardButton(text="👥 Список контактів", callback_data="streak_list_targets"),
            InlineKeyboardButton(text="➕ Додати контакт", callback_data="streak_add_target")
        ],
        [
            InlineKeyboardButton(text="📜 Журнал відправок", callback_data="streak_logs"),
            InlineKeyboardButton(text="⏰ Час розкладу", callback_data="streak_schedule")
        ],
        [
            InlineKeyboardButton(text="🔑 Окремий акаунт для вогників (SessionID)", callback_data="streak_set_session")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад до головного меню", callback_data="menu_back")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_cyber_rizhyi_keyboard() -> InlineKeyboardMarkup:
    """Меню керування ботом 'Кібер Рижий'"""
    buttons = [
        [
            InlineKeyboardButton(text="💬 Тест репліки Рижого", callback_data="rizhyi_test_reply"),
            InlineKeyboardButton(text="🧠 Що Рижий пам'ятає", callback_data="rizhyi_memory_check")
        ],
        [
            InlineKeyboardButton(text="📸 Тест реакції на фото", callback_data="rizhyi_test_photo"),
            InlineKeyboardButton(text="⚡️ Інфо про модель Groq", callback_data="rizhyi_model_info")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад до головного меню", callback_data="menu_back")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_streak_targets_management_keyboard(targets: List[dict]) -> InlineKeyboardMarkup:
    """Клавіатура списку контактів із кнопками видалення"""
    buttons = []
    for t in targets:
        user = t["username"]
        is_gf = bool(t["is_girlfriend"])
        icon = "❤️ 👸" if is_gf else "🔥"
        name = t.get("nickname") or user
        btn_text = f"{icon} @{user} ({name})"
        buttons.append([
            InlineKeyboardButton(text=btn_text, callback_data=f"target_info:{user}"),
            InlineKeyboardButton(text="❌", callback_data=f"target_del:{user}")
        ])
    buttons.append([
        InlineKeyboardButton(text="➕ Додати контакт", callback_data="streak_add_target"),
        InlineKeyboardButton(text="◀️ До меню вогників", callback_data="menu_streaks")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_prompt_management_keyboard() -> InlineKeyboardMarkup:
    """Керування промптом Gemini та вибір SEO-режимів під пошукові запити"""
    buttons = [
        [
            InlineKeyboardButton(text="🔍 SEO: Пошук + Вірусність", callback_data="preset_seo:seo_viral"),
            InlineKeyboardButton(text="📚 SEO: Гайди (How-To)", callback_data="preset_seo:seo_howto")
        ],
        [
            InlineKeyboardButton(text="🏆 SEO: ТОП-добірки", callback_data="preset_seo:seo_top"),
            InlineKeyboardButton(text="💼 SEO: Комерційний / B2B", callback_data="preset_seo:seo_commercial")
        ],
        [
            InlineKeyboardButton(text="✏️ Задати власний промпт", callback_data="prompt_change"),
            InlineKeyboardButton(text="🔄 Скинути до базового", callback_data="prompt_reset")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад до меню", callback_data="menu_back")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
