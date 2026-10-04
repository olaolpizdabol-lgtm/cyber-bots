import os
import html
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import (
    BASE_DIR,
    is_user_allowed,
    DOWNLOADS_DIR,
    DEFAULT_AI_PROMPT
)
from core.content_type import ContentType, FORMAT_TITLES, FORMAT_SUPPORTED_PLATFORMS
from core.database import (
    get_setting,
    set_setting,
    get_post_by_id,
    get_recent_posts,
    get_last_published_post,
    update_post_metadata,
    get_streak_targets,
    get_girlfriend_target,
    set_girlfriend_target,
    add_streak_target,
    remove_streak_target,
    get_recent_streak_logs,
    get_streak_stats,
    get_cyber_rizhyi_chat_history,
    get_cyber_rizhyi_user_memory,
    get_recent_tiktok_reactions
)
from core.security_guard import security_guard
from services.gemini_ai import sanitize_typography, gemini_service, SEO_PROMPT_PRESETS
from services.automations.auto_poster import (
    auto_poster,
    TIER_1_PLATFORMS,
    PUBLISHERS
)
from services.automations.automation_2 import tiktok_streak_service
from services.cyber_rizhyi import cyber_rizhyi_service
from services.tiktok_reactions import tiktok_reactions_service
from services.proxy_manager import (
    proxy_manager,
    IP_DEPENDENT_PLATFORMS,
    PLATFORM_IP_DETAILS
)
from bot.keyboards import (
    get_publish_keyboard,
    get_condense_keyboard,
    get_main_menu_keyboard,
    get_main_reply_keyboard,
    get_prompt_management_keyboard,
    get_streak_menu_keyboard,
    get_streak_targets_management_keyboard,
    get_cyber_rizhyi_keyboard,
    get_publish_result_keyboard
)

logger = logging.getLogger(__name__)
router = Router()


class BotStates(StatesGroup):
    waiting_for_new_prompt = State()
    waiting_for_gf_username = State()
    waiting_for_new_streak_target = State()
    waiting_for_streak_schedule = State()
    waiting_for_streak_session = State()
    waiting_for_tiktok_reaction_url = State()
    waiting_for_rizhyi_test_input = State()
    waiting_for_rizhyi_photo_test = State()


# ---------------------------------------------------------
# КОМАНДИ /start, /help, /stats, /proxy, /prompt, /condense
# ---------------------------------------------------------

@router.message(CommandStart())
async def cmd_start(message: Message):
    if not is_user_allowed(message.from_user.id):
        logger.warning(f"Користувач {message.from_user.id} ({message.from_user.username}) спробував доступ!")
        await message.answer(
            f"⛔️ <b>Доступ обмежено.</b>\n"
            f"Ваш Telegram ID: <code>{message.from_user.id}</code>\n\n"
            f"Щоб користуватися ботом, додайте цей ID у змінну <code>ALLOWED_TELEGRAM_USER_IDS</code> у Railway або .env.",
            parse_mode="HTML"
        )
        return

    # Встановлюємо постійну клавіатуру з великими кнопками внизу екрана
    await message.answer(
        "📱 <b>Меню управління активовано!</b> Оберіть дію кнопками внизу або в повідомленні 👇",
        reply_markup=get_main_reply_keyboard(),
        parse_mode="HTML"
    )

    welcome_text = sanitize_typography(
        "👋 <b>Вітаю в хабі мультиплатформенного автозаливу!</b>\n\n"
        "⚡️ <b>Підтримується БУДЬ-ЯКИЙ формат контенту (2026):</b>\n"
        "• 🎬 <b>Вертикальне відео (9:16):</b> TikTok, Reels, Shorts, FB Reels, Snapchat, X, Threads, Pinterest, Bluesky, Telegram\n"
        "• 📸 <b>Одиночне фото:</b> Instagram, Facebook, X, Threads, Pinterest, Bluesky, Telegram\n"
        "• 📚 <b>Каруселі (Photo Mode):</b> Instagram (до 20), TikTok (до 35), Threads, Facebook, Pinterest, X, Bluesky\n"
        "• 📝 <b>Текстові пости:</b> X (Twitter), Threads, Bluesky, Facebook, Telegram\n\n"
        "✨ <b>Просто скиньте що завгодно у чат:</b> відео, фото, альбом або текст - "
        "Gemini AI миттєво згенерує адаптовані описи під точні ліміти кожної платформи!"
    )
    await message.answer(welcome_text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")


# ---------------------------------------------------------
# ОБРОБНИКИ ПОСТІЙНИХ КНОПОК НИЖНЬОЇ КЛАВІАТУРИ
# ---------------------------------------------------------

@router.message(F.text == "🚀 Пост на ВСІ платформи (YT+IG+TT+TG)")
async def reply_btn_crosspost(message: Message):
    if not is_user_allowed(message.from_user.id):
        return
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Надіслати відео у чат - я опублікую на всіх!", callback_data="crosspost_hint")],
        [InlineKeyboardButton(text="🔄 Взяти останнє відео з бази і запостити", callback_data="crosspost_last")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")]
    ])
    await message.answer(
        "🚀 <b>Крос-постинг короткого відео</b>\n\n"
        "Я запущу публікацію одночасно на:\n"
        "🔴 YouTube Shorts (Bohdan AI)\n"
        "🟣 Instagram Reels (@bohdan.gpt)\n"
        "⚫️ TikTok (@bohdan.gpt)\n"
        "💬 Telegram-канал (@bohdan_gpt)\n\n"
        "Обери варіант:",
        parse_mode="HTML",
        reply_markup=kb
    )


@router.message(F.text == "🔥 TikTok Вогники")
async def reply_btn_streaks(message: Message):
    if not is_user_allowed(message.from_user.id):
        return
    await show_streak_menu_message(message)


@router.message(F.text == "📊 Перегляди / Статистика")
async def reply_btn_stats(message: Message):
    if not is_user_allowed(message.from_user.id):
        return
    await show_stats_message(message)


@router.message(F.text == "🌐 Перевірити Проксі")
async def reply_btn_proxy(message: Message):
    if not is_user_allowed(message.from_user.id):
        return
    await show_proxy_message(message)


@router.message(F.text == "🤖 Головне меню")
async def reply_btn_main_menu(message: Message):
    if not is_user_allowed(message.from_user.id):
        return
    await message.answer("🤖 <b>Головне меню:</b>", reply_markup=get_main_menu_keyboard(), parse_mode="HTML")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_user_allowed(message.from_user.id):
        return
    await show_stats_message(message)


@router.message(Command("proxy"))
async def cmd_proxy(message: Message):
    if not is_user_allowed(message.from_user.id):
        return
    await show_proxy_message(message)


@router.message(Command("prompt"))
async def cmd_prompt(message: Message):
    if not is_user_allowed(message.from_user.id):
        return
    await show_prompt_message(message)


@router.message(Command("condense"))
async def cmd_condense(message: Message):
    """
    Команда для швидкого скорочення тексту публікації:
    /condense - пакетно скоротити для всіх мікроблогів (X, Threads, Bluesky)
    /condense 200 - скоротити твіт для X до 200 символів
    """
    if not is_user_allowed(message.from_user.id):
        return

    recent = get_recent_posts(1)
    if not recent:
        await message.answer("ℹ️ Немає створених публікацій для скорочення.")
        return

    post_id = recent[0]["id"]
    args = message.text.split()[1:]

    if args and args[0].isdigit():
        max_chars = int(args[0])
        status = await message.answer(f"✂️ <b>Gemini AI скорочує текст для X до {max_chars} символів...</b>", parse_mode="HTML")
        updated_post = auto_poster.condense_post_texts(post_id, target_platform="twitter", max_chars=max_chars)
    else:
        status = await message.answer(f"✂️ <b>Gemini AI пакетно оптимізує тексти для X, Threads, Bluesky...</b>", parse_mode="HTML")
        updated_post = auto_poster.condense_post_texts(post_id)

    await status.delete()
    await send_post_preview_from_dict(message, updated_post)


# ---------------------------------------------------------
# 1. ОБРОБКА КАРУСЕЛЕЙ (АЛЬБОМІВ МЕДІА З ТЕЛЕФОНУ)
# ---------------------------------------------------------

@router.message(F.media_group_id)
async def handle_media_group(message: Message, bot: Bot, album: Optional[List[Message]] = None):
    if not is_user_allowed(message.from_user.id):
        return

    messages = album or [message]
    status_msg = await message.answer(f"⏳ <b>Отримано карусель ({len(messages)} файлів)!</b> Завантажуємо та обробляємо...")

    try:
        downloaded_paths = []
        has_video = False

        for idx, msg in enumerate(messages):
            file_id = None
            ext = ".jpg"
            if msg.photo:
                file_id = msg.photo[-1].file_id
                ext = ".jpg"
            elif msg.video:
                file_id = msg.video.file_id
                ext = ".mp4"
                has_video = True
            elif msg.document:
                file_id = msg.document.file_id
                ext = Path(msg.document.file_name or "file.jpg").suffix or ".jpg"

            if file_id:
                f_info = await bot.get_file(file_id)
                loc_path = DOWNLOADS_DIR / f"carousel_{msg.from_user.id}_{msg.message_id}_{idx}{ext}"
                await bot.download_file(f_info.file_path, destination=loc_path)
                downloaded_paths.append(str(loc_path))

        c_type = ContentType.MIXED_CAROUSEL if has_video else ContentType.CAROUSEL
        await status_msg.edit_text("🧠 <b>Gemini 2.5 аналізує карусель</b> та створює описи для всіх соцмереж...")

        data = auto_poster.process_incoming_content(
            content_type=c_type,
            media_paths=downloaded_paths
        )
        await send_prepared_preview(message, status_msg, data)

    except Exception as e:
        logger.error(f"Помилка каруселі: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ <b>Помилка:</b> <code>{html.escape(security_guard.sanitize_error(str(e)))}</code>", parse_mode="HTML")


# ---------------------------------------------------------
# 2. ОБРОБКА ВІДЕО (ВЕРТИКАЛЬНИХ РОЛИКІВ)
# ---------------------------------------------------------

@router.message(F.video | (F.document & F.document.mime_type.startswith("video/")))
async def handle_video_upload(message: Message, bot: Bot):
    if not is_user_allowed(message.from_user.id):
        return

    status_msg = await message.answer("⏳ <b>Відео отримано!</b> Завантажуємо та готуємо до аналізу...")

    try:
        video_obj = message.video or message.document
        file_size = getattr(video_obj, "file_size", 0) or 0
        is_local_server = getattr(getattr(bot, "session", None), "api", None) and getattr(bot.session.api, "is_local", False)
        if file_size > 20 * 1024 * 1024 and not is_local_server:
            size_mb = file_size / (1024 * 1024)
            await status_msg.edit_text(
                f"⚠️ <b>Відео завелике ({size_mb:.1f} МБ)!</b>\n\n"
                f"Офіційний ліміт Telegram Bot API на скачування ботом — <b>строго 20 МБ</b>.\n\n"
                f"💡 <b>Як надіслати:</b>\n"
                f"1. <b>Надішліть як звичайне «Відео», а не як «Файл/Документ»:</b>\n"
                f"   При виборі як медіа/відео Telegram сам оптимізує ролик до ~8–12 МБ зі збереженням якості!\n"
                f"2. Або стисніть/експортуйте відео з бітрейтом до 20 МБ.\n"
                f"3. Або натисніть <b>«🔄 Взяти останнє відео з бази і запостити»</b>, щоб протестувати публікацію прямо зараз!",
                parse_mode="HTML"
            )
            return

        file_id = video_obj.file_id
        file_info = await bot.get_file(file_id)

        file_ext = Path(file_info.file_path).suffix or ".mp4"
        local_filename = f"vid_{message.from_user.id}_{message.message_id}{file_ext}"
        local_path = DOWNLOADS_DIR / local_filename

        await bot.download_file(file_info.file_path, destination=local_path)
        await status_msg.edit_text("🧠 <b>Gemini 3.5 аналізує відео</b> під стандарти всіх соцмереж...")

        data = auto_poster.process_incoming_video(str(local_path))
        await send_prepared_preview(message, status_msg, data)

    except Exception as e:
        logger.error(f"Помилка обробки відео: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ <b>Помилка:</b> <code>{html.escape(security_guard.sanitize_error(str(e)))}</code>", parse_mode="HTML")


# ---------------------------------------------------------
# 3. ОБРОБКА ОДИНОЧНОГО ФОТО
# ---------------------------------------------------------

@router.message(F.photo | (F.document & F.document.mime_type.startswith("image/")))
async def handle_single_photo(message: Message, bot: Bot):
    # 1. Якщо це повідомлення в групі - Кібер Рижий аналізує через Gemini та відповідає!
    if message.chat.type in ("group", "supergroup"):
        try:
            photo_obj = message.photo[-1] if message.photo else message.document
            file_id = photo_obj.file_id
            file_info = await bot.get_file(file_id)
            file_ext = Path(file_info.file_path).suffix or ".jpg"
            local_path = DOWNLOADS_DIR / f"group_photo_{message.from_user.id}_{message.message_id}{file_ext}"
            await bot.download_file(file_info.file_path, destination=local_path)

            caption = message.caption or ""
            reply_text = cyber_rizhyi_service.generate_reply(
                chat_id=message.chat.id,
                chat_type=message.chat.type,
                user_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                message_text=caption,
                has_photo=True,
                photo_path=str(local_path)
            )
            await message.reply(reply_text)
            return
        except Exception as e:
            logger.error(f"Помилка аналізу фото Кібер Рижим у групі: {e}")
            return

    # 2. Якщо в особистому чаті підпис містить /rizhyi або згадку про Рижого - він аналізує через Gemini та відповідає!
    caption_low = (message.caption or "").lower()
    if "/rizhyi" in caption_low or "рижий" in caption_low or "саня" in caption_low:
        status_msg = await message.answer("👀 <b>Рижий роздивляється фото через Gemini...</b>", parse_mode="HTML")
        try:
            photo_obj = message.photo[-1] if message.photo else message.document
            file_id = photo_obj.file_id
            file_info = await bot.get_file(file_id)
            file_ext = Path(file_info.file_path).suffix or ".jpg"
            local_path = DOWNLOADS_DIR / f"priv_photo_{message.from_user.id}_{message.message_id}{file_ext}"
            await bot.download_file(file_info.file_path, destination=local_path)

            reply_text = cyber_rizhyi_service.generate_reply(
                chat_id=message.chat.id,
                chat_type=message.chat.type,
                user_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                message_text=message.caption or "",
                has_photo=True,
                photo_path=str(local_path)
            )
            await status_msg.edit_text(f"🤖 <b>Рижий:</b> {html.escape(reply_text)}", parse_mode="HTML")
            return
        except Exception as e:
            logger.error(f"Помилка аналізу фото в приваті: {e}")
            await status_msg.edit_text("🤖 <b>Рижий:</b> шо це за херня", parse_mode="HTML")
            return

    # 3. Якщо це особистий чат без звернення до Рижого - перевірка доступу та потік публікації
    if not is_user_allowed(message.from_user.id):
        return

    status_msg = await message.answer("⏳ <b>Фото отримано!</b> Завантажуємо та адаптуємо пропорції...")

    try:
        photo_obj = message.photo[-1] if message.photo else message.document
        file_id = photo_obj.file_id
        file_info = await bot.get_file(file_id)

        file_ext = Path(file_info.file_path).suffix or ".jpg"
        local_path = DOWNLOADS_DIR / f"photo_{message.from_user.id}_{message.message_id}{file_ext}"

        await bot.download_file(file_info.file_path, destination=local_path)
        await status_msg.edit_text("🧠 <b>Gemini 3.5 створює вірусні описи під фото...</b>")

        data = auto_poster.process_incoming_content(
            content_type=ContentType.PHOTO,
            media_paths=[str(local_path)]
        )
        await send_prepared_preview(message, status_msg, data)

    except Exception as e:
        logger.error(f"Помилка фото: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ <b>Помилка:</b> <code>{html.escape(security_guard.sanitize_error(str(e)))}</code>", parse_mode="HTML")


# ---------------------------------------------------------
# 3.1. ОБРОБКА ГОЛОСОВИХ ПОВІДОМЛЕНЬ (Groq Whisper & Кібер Рижий)
# ---------------------------------------------------------

@router.message(F.voice | F.audio)
async def handle_voice_message(message: Message, bot: Bot):
    """
    Обробка голосових повідомлень через Groq Whisper та Кібер Рижого.
    Якщо голосове надіслано в групу або приватно Рижому - бот транскрибує та відповідає!
    """
    is_group = message.chat.type in ("group", "supergroup")
    voice_obj = message.voice or message.audio
    if not voice_obj:
        return

    try:
        file_info = await bot.get_file(voice_obj.file_id)
        local_path = DOWNLOADS_DIR / f"voice_{message.from_user.id}_{message.message_id}.ogg"
        await bot.download_file(file_info.file_path, destination=local_path)

        reply_text = cyber_rizhyi_service.generate_reply(
            chat_id=message.chat.id,
            chat_type=message.chat.type,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            message_text="",
            has_photo=False,
            has_voice=True,
            voice_path=str(local_path)
        )
        if is_group or not is_user_allowed(message.from_user.id):
            await message.reply(reply_text)
        else:
            await message.reply(f"🤖 <b>Рижий:</b> {html.escape(reply_text)}", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Помилка обробки голосового повідомлення: {e}")
        if is_group:
            await message.reply("ти шо войси шлеш? розпиши текстом або го в кс")


# ---------------------------------------------------------
# 4. ОБРОБКА ТЕКСТОВИХ ПОВІДОМЛЕНЬ
# ---------------------------------------------------------

@router.message(F.text & ~F.text.startswith("/"))
async def handle_text_post(message: Message):
    text_content = message.text.strip()

    # 1. Перевірка: чи це посилання на TikTok?
    if tiktok_reactions_service.is_tiktok_url(text_content):
        # Якщо надіслали TikTok посилання (у групі чи в приваті) - реагуємо у стилі Боді!
        url = tiktok_reactions_service.extract_tiktok_url(text_content)
        status_msg = await message.reply("🎬 <b>Завантажуємо TikTok та генеруємо реакцію у стилі Боді...</b>", parse_mode="HTML")
        try:
            res = tiktok_reactions_service.process_tiktok_link(url)
            author_str = f"@{res['uploader']}" if res.get("uploader") else "TikTok"
            title_str = f"<i>«{html.escape(res['title'][:60])}»</i>\n\n" if res.get("title") else ""

            await status_msg.edit_text(
                f"🎬 <b>Реакція Боді на TikTok ({author_str}):</b>\n"
                f"{title_str}"
                f"💬 <b>{html.escape(res['reaction'])}</b>",
                parse_mode="HTML"
            )
            return
        except Exception as e:
            logger.error(f"Помилка генерації реакції на TikTok: {e}")
            await status_msg.edit_text(f"💬 <b>{html.escape(tiktok_reactions_service.generate_reaction())}</b>", parse_mode="HTML")
            return

    # 2. Якщо повідомлення у групі - відповідає "Кібер Рижий" на базі Groq 120B та пам'яті!
    if message.chat.type in ("group", "supergroup"):
        try:
            reply_text = cyber_rizhyi_service.generate_reply(
                chat_id=message.chat.id,
                chat_type=message.chat.type,
                user_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                message_text=text_content,
                has_photo=False
            )
            await message.reply(reply_text)
            return
        except Exception as e:
            logger.error(f"Помилка Кібер Рижого у групі: {e}")
            return

    # 2.5. Перевірка: чи надіслано посилання на відео (Google Drive, Dropbox, direct MP4)
    from services.video_downloader import is_video_url, download_video_from_url
    if is_video_url(text_content):
        if not is_user_allowed(message.from_user.id):
            return
        status_msg = await message.answer("🌐 <b>Виявлено посилання на відео!</b> Завантажуємо на сервер (без лімітів Telegram)...", parse_mode="HTML")
        downloaded = download_video_from_url(text_content)
        if downloaded:
            await status_msg.edit_text("🧠 <b>Відео завантажено!</b> FFmpeg стискає, Gemini 3.5 створює опис...", parse_mode="HTML")
            try:
                data = auto_poster.process_incoming_video(downloaded)
                await send_prepared_preview(message, status_msg, data)
                return
            except Exception as e:
                logger.error(f"Помилка обробки відео за посиланням: {e}")
                await status_msg.edit_text(f"❌ <b>Помилка:</b> {html.escape(str(e))}", parse_mode="HTML")
                return
        else:
            await status_msg.edit_text("⚠️ Не вдалося завантажити відео за цим посиланням. Переконайтеся, що посилання публічно доступне (наприклад, доступ 'Усі, хто має посилання' в Google Drive).", parse_mode="HTML")
            return

    # 3. Особистий чат власника - потік підготовки текстового посту до публікації
    if not is_user_allowed(message.from_user.id):
        return

    status_msg = await message.answer("🧠 <b>Gemini 3.5 оптимізує текст</b> під стандарти Twitter, Threads, Bluesky та Facebook...")

    try:
        data = auto_poster.process_incoming_content(
            content_type=ContentType.TEXT,
            raw_text=message.text
        )
        await send_prepared_preview(message, status_msg, data)
    except Exception as e:
        logger.error(f"Помилка текстового поста: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ <b>Помилка:</b> <code>{html.escape(security_guard.sanitize_error(str(e)))}</code>", parse_mode="HTML")


# ---------------------------------------------------------
# ВІДОБРАЖЕННЯ ПРЕВ'Ю ПЕРЕД ПУБЛІКАЦІЄЮ (З ПІДРАХУНКОМ СИМВОЛІВ)
# ---------------------------------------------------------

def build_preview_text(post_id: int, c_type: ContentType, data: dict) -> str:
    format_title = FORMAT_TITLES.get(c_type, "Контент")
    compat = data.get("compatible_platforms", FORMAT_SUPPORTED_PLATFORMS.get(c_type, []))

    yt_title = sanitize_typography(data.get("youtube_title") or data.get("yt_title") or "")
    caption = sanitize_typography(data.get("ig_caption") or data.get("caption") or "")
    tw_post = sanitize_typography(data.get("twitter_post") or data.get("tw_post") or "")
    th_post = sanitize_typography(data.get("threads_post") or "")
    bsky_post = sanitize_typography(data.get("bluesky_post") or "")
    hashtags = sanitize_typography(data.get("hashtags") or "")

    caption_preview = caption[:200] + ("..." if len(caption) > 200 else "")

    text = (
        f"✨ <b>Контент підготовлено до публікації! (ID: #{post_id})</b>\n\n"
        f"📌 <b>Формат:</b> {format_title}\n"
        f"🌐 <b>Сумісних платформ:</b> {len(compat)}\n\n"
    )

    if c_type == ContentType.VIDEO:
        text += f"🔴 <b>Shorts:</b> <code>{html.escape(yt_title)}</code> [{len(yt_title)}/100 симв]\n\n"
        text += f"🟣 <b>Reels / TikTok / FB:</b> [{len(caption)}/2200 симв]\n<i>{html.escape(caption_preview)}</i>\n\n"
        if tw_post:
            text += f"𝕏 <b>X:</b> [{len(tw_post)}/240 симв] <code>{html.escape(tw_post[:100])}...</code>\n"
        if th_post:
            text += f"🧵 <b>Threads:</b> [{len(th_post)}/400 симв] <code>{html.escape(th_post[:100])}...</code>\n"
        if bsky_post:
            text += f"🦋 <b>Bluesky:</b> [{len(bsky_post)}/250 симв] <code>{html.escape(bsky_post[:100])}...</code>\n\n"
    elif c_type in (ContentType.PHOTO, ContentType.CAROUSEL, ContentType.MIXED_CAROUSEL):
        text += f"📸 <b>Опис для Instagram, TikTok, Threads, FB:</b> [{len(caption)} симв]\n<i>{html.escape(caption_preview)}</i>\n\n"
        if tw_post:
            text += f"𝕏 <b>X (Twitter):</b> [{len(tw_post)}/240 симв] <code>{html.escape(tw_post[:100])}...</code>\n"
        if bsky_post:
            text += f"🦋 <b>Bluesky:</b> [{len(bsky_post)}/250 симв] <code>{html.escape(bsky_post[:100])}...</code>\n\n"
    elif c_type == ContentType.TEXT:
        text += f"𝕏 <b>X (Twitter):</b> [{len(tw_post)}/240 симв]\n<code>{html.escape(tw_post)}</code>\n\n"
        text += f"🧵 <b>Threads:</b> [{len(th_post)}/400 симв]\n<code>{html.escape(th_post)}</code>\n\n"
        text += f"🦋 <b>Bluesky:</b> [{len(bsky_post)}/250 симв]\n<code>{html.escape(bsky_post)}</code>\n\n"

    if hashtags:
        text += f"🏷 <b>Хештеги:</b> {html.escape(hashtags)}\n"

    text += "🛡 <b>Захист:</b> Метадані очищено, унікальний хеш, US/NY IP для чутливих мереж, дефіси '-' (без довгих тире).\n\n"
    text += "👇 <b>Оберіть спосіб публікації або скоротіть текст:</b>"
    return text


async def send_prepared_preview(message: Message, status_msg: Message, data: dict):
    post_id = data["post_id"]
    c_type = data["content_type"]
    text = build_preview_text(post_id, c_type, data)

    await status_msg.delete()
    await message.answer(
        text,
        reply_markup=get_publish_keyboard(post_id, c_type),
        parse_mode="HTML"
    )


async def send_post_preview_from_dict(message: Message, post: dict):
    post_id = post["id"]
    try:
        c_type = ContentType(post.get("content_type", "video"))
    except Exception:
        c_type = ContentType.VIDEO

    text = build_preview_text(post_id, c_type, post)
    await message.answer(
        text,
        reply_markup=get_publish_keyboard(post_id, c_type),
        parse_mode="HTML"
    )


# ---------------------------------------------------------
# CALLBACKS: СКОРОЧЕННЯ ТЕКСТІВ (CONDENSATION)
# ---------------------------------------------------------

@router.callback_query(F.data.startswith("cond_menu:"))
async def callback_condense_menu(call: CallbackQuery):
    post_id = int(call.data.split(":")[1])
    text = (
        f"✂️ <b>Інтелектуальне скорочення тексту для публікації #{post_id}</b>\n\n"
        "Gemini AI стисне довгий опис під точні ліміти обраної платформи, зберігаючи головний зміст, гачок (hook) та заклик до дії.\n"
        "Правило типографіки: ТІЛЬКИ дефіс '-', жодних довгих тире '—'."
    )
    await call.message.edit_text(text, reply_markup=get_condense_keyboard(post_id), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("cond_p:"))
async def callback_condense_single(call: CallbackQuery):
    parts = call.data.split(":")
    post_id = int(parts[1])
    platform = parts[2]
    max_chars = int(parts[3])

    await call.answer("⏳ Gemini скорочує текст...", show_alert=False)
    updated_post = auto_poster.condense_post_texts(post_id, target_platform=platform, max_chars=max_chars)

    try:
        c_type = ContentType(updated_post.get("content_type", "video"))
    except Exception:
        c_type = ContentType.VIDEO

    new_text = build_preview_text(post_id, c_type, updated_post)
    await call.message.edit_text(new_text, reply_markup=get_publish_keyboard(post_id, c_type), parse_mode="HTML")


@router.callback_query(F.data.startswith("cond_all:"))
async def callback_condense_all(call: CallbackQuery):
    post_id = int(call.data.split(":")[1])
    await call.answer("⏳ Gemini пакетно скорочує тексти...", show_alert=False)
    updated_post = auto_poster.condense_post_texts(post_id)

    try:
        c_type = ContentType(updated_post.get("content_type", "video"))
    except Exception:
        c_type = ContentType.VIDEO

    new_text = build_preview_text(post_id, c_type, updated_post)
    await call.message.edit_text(new_text, reply_markup=get_publish_keyboard(post_id, c_type), parse_mode="HTML")


@router.callback_query(F.data.startswith("back_pub:"))
async def callback_back_to_publish(call: CallbackQuery):
    post_id = int(call.data.split(":")[1])
    post = get_post_by_id(post_id)
    if not post:
        await call.answer("Пост не знайдено", show_alert=True)
        return

    try:
        c_type = ContentType(post.get("content_type", "video"))
    except Exception:
        c_type = ContentType.VIDEO

    text = build_preview_text(post_id, c_type, post)
    await call.message.edit_text(text, reply_markup=get_publish_keyboard(post_id, c_type), parse_mode="HTML")
    await call.answer()


# ---------------------------------------------------------
# CALLBACKS: ПУБЛІКАЦІЯ
# ---------------------------------------------------------

@router.callback_query(F.data.startswith("pub_compat:"))
async def callback_publish_compat(call: CallbackQuery):
    post_id = int(call.data.split(":")[1])
    await call.message.edit_reply_markup(reply_markup=None)
    status_msg = await call.message.answer(f"🚀 <b>Публікація #{post_id} у всі сумісні платформи розпочалась...</b>")

    results = auto_poster.publish_post(post_id)
    await format_and_send_publish_results(status_msg, post_id, results)
    await call.answer()


@router.callback_query(F.data.startswith("pub_tier1:"))
async def callback_publish_tier1(call: CallbackQuery):
    post_id = int(call.data.split(":")[1])
    await call.message.edit_reply_markup(reply_markup=None)
    status_msg = await call.message.answer(f"🔥 <b>Публікація #{post_id} у Рівень 1 (Top 5: TT, IG, YT, FB, Snap)...</b>")

    results = auto_poster.publish_post(post_id, TIER_1_PLATFORMS)
    await format_and_send_publish_results(status_msg, post_id, results)
    await call.answer()


@router.callback_query(F.data.startswith("pub_p:"))
async def callback_publish_single(call: CallbackQuery):
    parts = call.data.split(":")
    post_id = int(parts[1])
    platform = parts[2]

    pub = PUBLISHERS.get(platform)
    plat_name = pub.platform_name if pub else platform
    status_msg = await call.message.answer(f"⏳ Публікуємо в <b>{plat_name}</b>...")

    results = auto_poster.publish_post(post_id, [platform])
    res = results.get(platform)
    if res and res.success:
        link = f"<a href='{res.url}'>Переглянути</a>" if res.url else "Опубліковано"
        await status_msg.edit_text(f"✅ <b>{plat_name}:</b> Успішно! {link}", parse_mode="HTML", disable_web_page_preview=True)
    else:
        err = res.error if res else "Помилка"
        await status_msg.edit_text(f"❌ <b>{plat_name}:</b> <code>{html.escape(security_guard.sanitize_error(str(err)))}</code>", parse_mode="HTML")
    await call.answer()


async def format_and_send_publish_results(msg: Message, post_id: int, results: dict):
    icons = {
        "tiktok": "⚫️", "instagram": "🟣", "youtube": "🔴",
        "facebook": "🔵", "snapchat": "🟡", "twitter": "𝕏",
        "threads": "🧵", "pinterest": "📌", "bluesky": "🦋",
        "telegram": "💬"
    }
    has_failures = any(not res.success for res in results.values()) if results else False
    text = f"🏁 <b>Звіт публікації контенту #{post_id}:</b>\n\n"
    for plat, res in results.items():
        icon = icons.get(plat, "🌐")
        if res.success:
            link = f"<a href='{res.url}'>Переглянути</a>" if res.url else "OK"
            text += f"{icon} <b>{res.platform}:</b> ✅ Успішно! {link}\n"
        else:
            text += f"{icon} <b>{res.platform}:</b> ❌ <code>{html.escape(security_guard.sanitize_error(str(res.error)))}</code>\n"

    await msg.edit_text(
        text,
        reply_markup=get_publish_result_keyboard(post_id, has_failures=has_failures),
        parse_mode="HTML",
        disable_web_page_preview=True
    )


@router.callback_query(F.data.startswith("retry_failed:"))
async def callback_retry_failed(call: CallbackQuery):
    post_id = int(call.data.split(":")[1])
    status_msg = await call.message.answer(f"🔄 <b>Повторна публікація поста #{post_id} на непройдених мережах...</b>", parse_mode="HTML")
    res_dict = auto_poster.retry_failed_platforms(post_id)
    results = res_dict.get("results", {})
    if not results:
        await status_msg.edit_text(f"ℹ️ {res_dict.get('message', 'Усі платформи вже опубліковані!')}")
    else:
        await format_and_send_publish_results(status_msg, post_id, results)
    await call.answer()


@router.callback_query(F.data.startswith("post_analytics:"))
async def callback_post_analytics(call: CallbackQuery):
    post_id = int(call.data.split(":")[1])
    summary = auto_poster.get_post_analytics_summary(post_id)
    if "error" in summary:
        await call.answer(summary["error"], show_alert=True)
        return

    text = (
        f"📊 <b>Аналітика публікації #{post_id}:</b>\n\n"
        f"👁 <b>Сумарні перегляди:</b> {summary['total_views']:,}\n"
        f"❤️ <b>Сумарні лайки:</b> {summary['total_likes']:,}\n"
        f"💬 <b>Коментарі:</b> {summary['total_comments']:,}\n"
        f"🏆 <b>Топ-мережа:</b> {summary['top_platform']}\n\n"
        "<b>По мережах:</b>\n"
    )
    for p_key, stat in summary["platforms"].items():
        if not stat.error:
            text += f"• <b>{stat.platform}:</b> 👁 {stat.views} | ❤️ {stat.likes}\n"
        else:
            text += f"• <b>{stat.platform}:</b> ⚠️ <i>{html.escape(stat.error[:40])}</i>\n"

    await call.message.answer(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("regen:"))
async def callback_regenerate(call: CallbackQuery):
    post_id = int(call.data.split(":")[1])
    post = get_post_by_id(post_id)
    if not post:
        await call.answer("Пост не знайдено", show_alert=True)
        return

    await call.message.answer("🔄 <b>Gemini AI генерує новий варіант тексту...</b>")
    c_type_str = post.get("content_type", "video")
    try:
        c_type = ContentType(c_type_str)
    except Exception:
        c_type = ContentType.VIDEO

    media_paths = post.get("media_paths_list") or ([post["clean_video_path"]] if post.get("clean_video_path") else None)
    new_data = gemini_service.generate_metadata(content_type=c_type, media_paths=media_paths)
    update_post_metadata(post_id, new_data)

    updated = get_post_by_id(post_id) or new_data
    new_text = build_preview_text(post_id, c_type, updated)

    await call.message.answer(
        new_text,
        reply_markup=get_publish_keyboard(post_id, c_type),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("cancel:"))
async def callback_cancel(call: CallbackQuery):
    await call.message.edit_text("❌ Публікацію скасовано.")
    await call.answer()


# ---------------------------------------------------------
# CALLBACKS: КРОС-ПОСТИНГ НА ВСІ ПЛАТФОРМИ
# ---------------------------------------------------------

@router.callback_query(F.data == "menu_crosspost")
async def callback_crosspost_menu(call: CallbackQuery):
    """Показує меню крос-постингу з вибором: надіслати відео або взяти останній з бази"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📤 Надіслати відео у чат - я опублікую на всіх!",
                callback_data="crosspost_hint"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 Взяти останнє відео з бази і запостити",
                callback_data="crosspost_last"
            )
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back")
        ]
    ])
    await call.message.edit_text(
        "🚀 <b>Крос-постинг короткого відео</b>\n\n"
        "Я запущу публікацію одночасно на:\n"
        "🔴 YouTube Shorts (Bohdan AI)\n"
        "🟣 Instagram Reels (@bohdan.gpt)\n"
        "⚫️ TikTok (@bohdan.gpt)\n"
        "💬 Telegram-канал (@bohdan_gpt)\n\n"
        "Обери варіант:",
        parse_mode="HTML",
        reply_markup=kb
    )
    await call.answer()


@router.callback_query(F.data == "crosspost_hint")
async def callback_crosspost_hint(call: CallbackQuery):
    await call.message.answer(
        "📤 <b>Надішли відео у цей чат прямо зараз!</b>\n\n"
        "Як тільки отримаю відео — автоматично опублікую його на "
        "YouTube Shorts, Instagram Reels, TikTok та Telegram-канал.\n\n"
        "🔴 YouTube буде <b>unlisted</b> (доступ за посиланням).\n"
        "Якщо хочеш публічно — після публікації можна змінити у Studio.",
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data == "crosspost_last")
async def callback_crosspost_last(call: CallbackQuery):
    """Бере останнє відео з бази і публікує на всіх платформах"""
    import asyncio
    from services.publishers.youtube import youtube_publisher
    from services.publishers.instagram import instagram_publisher
    from services.publishers.tiktok import tiktok_publisher
    from services.publishers.telegram_channel import telegram_channel_publisher
    from core.content_type import ContentType
    from core.security_guard import security_guard
    from core.database import get_last_published_post
    import time, random

    status_msg = await call.message.answer(
        "⏳ <b>Запускаю крос-постинг...</b>\n"
        "🔴 YouTube Shorts...\n"
        "🟣 Instagram Reels...\n"
        "⚫️ TikTok...\n"
        "💬 Telegram-канал...",
        parse_mode="HTML"
    )
    await call.answer()

    post = get_last_published_post()

    # get_last_published_post може повернути пост з порожнім файлом
    # якщо відеофайл не існує — шукаємо останній пост з будь-яким файлом
    import os
    from core.database import get_recent_posts
    if not post or not post.get("clean_video_path") or not os.path.exists(post.get("clean_video_path", "")):
        recent = get_recent_posts(limit=10)
        post = next(
            (p for p in recent if p.get("clean_video_path") and os.path.exists(p["clean_video_path"])),
            None
        )
    if not post:
        await status_msg.edit_text("❌ Немає збереженого відео в базі. Спочатку надішли відео у чат!")
        return

    video_path = post.get("clean_video_path")
    if not video_path or not __import__("os").path.exists(video_path):
        await status_msg.edit_text(
            f"❌ Файл відео не знайдено: <code>{video_path}</code>\n"
            "Надішли нове відео у чат!",
            parse_mode="HTML"
        )
        return

    caption = post.get("ig_caption") or post.get("yt_desc") or "#shorts #ai #automation"
    title = post.get("yt_title") or "AI Content #shorts"
    metadata = {
        "youtube_title": title[:95],
        "youtube_desc": caption,
        "ig_caption": caption,
        "tt_caption": caption,
    }

    results = []

    # 1. YouTube Shorts
    try:
        service = youtube_publisher._get_authenticated_service()
        if service:
            from googleapiclient.http import MediaFileUpload
            body = {
                "snippet": {"title": title[:95], "description": caption, "tags": ["shorts", "ai"], "categoryId": "22"},
                "status": {"privacyStatus": "unlisted", "selfDeclaredMadeForKids": False}
            }
            media_upload = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
            resp = service.videos().insert(part="snippet,status", body=body, media_body=media_upload).execute()
            vid_id = resp.get("id")
            results.append(("🔴 YouTube Shorts", True, f"https://youtube.com/shorts/{vid_id}"))
        else:
            results.append(("🔴 YouTube Shorts", False, "Не авторизовано"))
    except Exception as e:
        results.append(("🔴 YouTube Shorts", False, security_guard.sanitize_error(str(e))))

    await asyncio.sleep(random.uniform(2.5, 4.0))

    # 2. Instagram Reels
    try:
        ig_client = instagram_publisher._get_client()
        if ig_client:
            media = ig_client.clip_upload(path=video_path, caption=caption)
            code = getattr(media, "code", str(media.pk))
            results.append(("🟣 Instagram Reels", True, f"https://instagram.com/p/{code}"))
        else:
            results.append(("🟣 Instagram Reels", False, "Не авторизовано"))
    except Exception as e:
        results.append(("🟣 Instagram Reels", False, security_guard.sanitize_error(str(e))))

    await asyncio.sleep(random.uniform(2.5, 4.0))

    # 3. TikTok
    try:
        tt_res = tiktok_publisher.publish(ContentType.VIDEO, [video_path], metadata)
        results.append(("⚫️ TikTok", tt_res.success, tt_res.url or tt_res.error))
    except Exception as e:
        results.append(("⚫️ TikTok", False, security_guard.sanitize_error(str(e))))

    await asyncio.sleep(random.uniform(2.5, 4.0))

    # 4. Telegram Channel
    try:
        tg_res = telegram_channel_publisher.publish(ContentType.VIDEO, [video_path], metadata)
        results.append(("💬 Telegram-канал", tg_res.success, tg_res.url or tg_res.error))
    except Exception as e:
        results.append(("💬 Telegram-канал", False, security_guard.sanitize_error(str(e))))

    # Формуємо звіт
    lines = ["📊 <b>Результати крос-постингу:</b>\n"]
    for platform, ok, info in results:
        if ok:
            lines.append(f"✅ {platform}\n   <a href='{info}'>Відкрити</a>")
        else:
            lines.append(f"❌ {platform}\n   <i>{html.escape(str(info or ''))}</i>")

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Головне меню", callback_data="menu_back")
    ]])
    await status_msg.edit_text("\n\n".join(lines), parse_mode="HTML", reply_markup=kb)


# ---------------------------------------------------------
# CALLBACKS: СТАТИСТИКА, ПРОКСІ, БЕЗПЕКА, ГАЙД ТА ПРОМПТ
# ---------------------------------------------------------

@router.callback_query(F.data == "menu_stats")
async def callback_stats(call: CallbackQuery):
    await show_stats_message(call.message)
    await call.answer()


async def show_stats_message(target_msg: Message):
    stats = auto_poster.get_latest_video_stats()
    if "error" in stats:
        await target_msg.answer(f"ℹ️ {html.escape(stats['error'])}")
        return

    platforms = stats.get("platforms", {})
    text = (
        f"📊 <b>Сумарна аналітика останньої публікації:</b>\n"
        f"📌 <i>{html.escape(stats['title'])}</i>\n"
        f"🕒 Опубліковано: {stats['created_at']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
    )

    icons = {
        "youtube": "🔴", "instagram": "🟣", "tiktok": "⚫️",
        "facebook": "🔵", "snapchat": "🟡", "twitter": "𝕏",
        "threads": "🧵", "pinterest": "📌", "bluesky": "🦋",
        "telegram": "💬"
    }

    total_views = 0
    total_likes = 0

    for plat_key, st in platforms.items():
        icon = icons.get(plat_key, "🌐")
        if st.error:
            text += f"{icon} <b>{st.platform}:</b> <code>{html.escape(security_guard.sanitize_error(str(st.error)))}</code>\n"
        else:
            text += f"{icon} <b>{st.platform}:</b> 👁 <b>{st.views:,}</b> | ❤️ {st.likes:,} | 💬 {st.comments}\n"
            total_views += st.views
            total_likes += st.likes

    text += f"━━━━━━━━━━━━━━━━━━━━━━\n🔥 <b>ВСЬОГО ОХОПЛЕННЯ: {total_views:,}</b> переглядів | ❤️ <b>{total_likes:,}</b>"
    await target_msg.answer(text, parse_mode="HTML")


@router.callback_query(F.data == "menu_security")
async def callback_security(call: CallbackQuery):
    audit = security_guard.audit_security(BASE_DIR)
    check = proxy_manager.check_proxy_health()

    text = (
        "🛡 <b>Комплексний безпековий аудит системи (Anti-Leak & Anti-Shadowban):</b>\n\n"
        "🔒 <b>1. Захист облікових даних (Local Only):</b>\n"
    )
    for p in audit["passed"]:
        text += f"• ✅ {html.escape(p)}\n"
    for iss in audit["issues"]:
        text += f"• ⚠️ {html.escape(iss)}\n"

    text += (
        "\n🗽 <b>2. Мережевий захист та IP:</b>\n"
        f"• Вихідний вузол: <code>{check['ip']}</code> ({check['city']}, {check['country']})\n"
        f"• DNS-Leak Prevention: <code>socks5h://</code> активовано\n"
        f"• IP-залежні мережі: <code>{', '.join(IP_DEPENDENT_PLATFORMS)}</code>\n\n"
        "🧬 <b>3. Захист від тіньового бану (Anti-Detection):</b>\n"
        "• Очищення EXIF, XMP, GPS та метаданих контейнера FFmpeg: <b>АКТИВНО</b>\n"
        "• Генерація унікального SHA-256 хешу (Micro-Audio/Gamma Jitter): <b>АКТИВНО</b>\n"
        "• Рандомізований часовий Jitter (2-5 сек) між платформами: <b>АКТИВНО</b>\n"
        "• Сувора типографіка: <b>ТІЛЬКИ дефіс '-' (без довгих тире)</b>\n\n"
        f"<b>Вердикт:</b> {html.escape(audit['summary'])}"
    )
    await call.message.answer(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "menu_proxy")
async def callback_proxy(call: CallbackQuery):
    await show_proxy_message(call.message)
    await call.answer()


async def show_proxy_message(target_msg: Message):
    check = proxy_manager.check_proxy_health()
    status_icon = "🟢" if check["ok"] else "🔴"
    text = (
        f"{status_icon} <b>Статус US/NY Проксі:</b>\n\n"
        f"🌐 <b>IP-адреса:</b> <code>{check['ip']}</code>\n"
        f"🇺🇸 <b>Країна:</b> {check['country']}\n"
        f"🗽 <b>Місто / Штат:</b> {check['city']}, {check['region']}\n"
        f"🏢 <b>Провайдер / ISP:</b> {check['isp']}\n\n"
        f"💬 <b>Вердикт:</b> {check['message']}\n\n"
        f"📌 <i>TikTok, Reels, FB Reels, Threads та Snapchat Spotlight автоматично маршрутизуються через цей IP.</i>"
    )
    await target_msg.answer(text, parse_mode="HTML")


@router.callback_query(F.data == "menu_free_proxy")
async def callback_free_proxy(call: CallbackQuery):
    guide_text = proxy_manager.get_free_proxy_guide()
    await call.message.answer(guide_text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "menu_prompt")
async def callback_prompt(call: CallbackQuery):
    await show_prompt_message(call.message)
    await call.answer()


async def show_prompt_message(target_msg: Message):
    current_prompt = get_setting("ai_prompt", DEFAULT_AI_PROMPT)
    # Перевіряємо чи поточний промпт збігається з якимось пресетом
    active_preset_name = "Власний користувацький"
    for p_key, p_val in SEO_PROMPT_PRESETS.items():
        if p_val["prompt"].strip() == current_prompt.strip():
            active_preset_name = p_val["title"]
            break
        elif current_prompt.strip() == DEFAULT_AI_PROMPT.strip() and p_key == "seo_viral":
            active_preset_name = p_val["title"]
            break

    text = (
        f"⚙️ <b>Промпт для Gemini AI (Social SEO 2026):</b>\n\n"
        f"🎯 <b>Поточний режим:</b> {html.escape(active_preset_name)}\n\n"
        f"<b>Активний текст промпту:</b>\n"
        f"<code>{html.escape(current_prompt)}</code>\n\n"
        "💡 <i>Оберіть готовий SEO-режим під пошукові запити нижче або задайте власний промпт:</i>"
    )
    await target_msg.answer(text, reply_markup=get_prompt_management_keyboard(), parse_mode="HTML")


@router.callback_query(F.data.startswith("preset_seo:"))
async def callback_preset_seo(call: CallbackQuery):
    preset_key = call.data.split(":")[1]
    preset_info = SEO_PROMPT_PRESETS.get(preset_key)
    if not preset_info:
        await call.answer("Пресет не знайдено", show_alert=True)
        return

    new_prompt = sanitize_typography(preset_info["prompt"])
    set_setting("ai_prompt", new_prompt)

    text = (
        f"✅ <b>Активовано SEO-режим:</b>\n"
        f"<b>{html.escape(preset_info['title'])}</b>\n\n"
        f"ℹ️ <i>{html.escape(preset_info['desc'])}</i>\n\n"
        f"<b>Текст промпту:</b>\n<code>{html.escape(new_prompt)}</code>\n\n"
        "🚀 Усі наступні публікації оптимізуватимуться під цей пошуковий алгоритм!"
    )
    await call.message.edit_text(text, reply_markup=get_prompt_management_keyboard(), parse_mode="HTML")
    await call.answer("SEO-режим збережено!")


@router.callback_query(F.data == "prompt_reset")
async def callback_prompt_reset(call: CallbackQuery):
    set_setting("ai_prompt", DEFAULT_AI_PROMPT)
    await call.message.edit_text(
        f"✅ Промпт скинуто до базового пошукового SEO:\n\n<code>{html.escape(DEFAULT_AI_PROMPT)}</code>",
        reply_markup=get_prompt_management_keyboard(),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data == "prompt_change")
async def callback_prompt_change(call: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_new_prompt)
    await call.message.answer("✏️ Надішліть новий текст промпту у наступному повідомленні:")
    await call.answer()


@router.message(BotStates.waiting_for_new_prompt)
async def process_new_prompt(message: Message, state: FSMContext):
    new_prompt = sanitize_typography(message.text.strip())
    if new_prompt:
        set_setting("ai_prompt", new_prompt)
        await message.answer(
            f"✅ <b>Новий промпт успішно збережено!</b>\n\n<code>{html.escape(new_prompt)}</code>",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML"
        )
    await state.clear()


@router.callback_query(F.data == "menu_history")
async def callback_history(call: CallbackQuery):
    posts = get_recent_posts(limit=5)
    if not posts:
        await call.message.answer("📜 Історія публікацій порожня.")
        await call.answer()
        return

    text = "📜 <b>Останні публікації:</b>\n\n"
    for p in posts:
        title = sanitize_typography((p.get("yt_title") or p.get("snap_title") or p.get("tw_post") or "Публікація")[:40])
        status = p.get("status", "draft")
        date = p.get("created_at", "")
        c_type = p.get("content_type", "video")
        text += f"• <b>#{p['id']}</b> ({c_type}) | {date} | <code>{status}</code>\n  <i>{html.escape(title)}...</i>\n\n"

    await call.message.answer(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "menu_back")
async def callback_back(call: CallbackQuery):
    await call.message.answer("Головне меню:", reply_markup=get_main_menu_keyboard())
    await call.answer()


# ---------------------------------------------------------
# АВТОМАТИЗАЦІЯ #2: TIKTOK ВОГНИКИ ТА СЕРДЕЧКА ДЛЯ ДІВЧИНИ
# ---------------------------------------------------------

@router.message(Command("streaks"))
async def cmd_streaks(message: Message):
    if not is_user_allowed(message.from_user.id):
        return
    await show_streaks_dashboard(message)


@router.callback_query(F.data == "menu_streaks")
async def callback_streaks_menu(call: CallbackQuery):
    await show_streaks_dashboard(call.message)
    await call.answer()


async def show_streaks_dashboard(target_msg: Message):
    stats = get_streak_stats()
    gf = get_girlfriend_target()
    schedule_time = get_setting("tiktok_streak_schedule_time", "10:00")
    is_streaks_sess_active = tiktok_streak_service.is_streaks_session_configured()
    streaks_sess_badge = "🟢 <i>Окрема сесія підключена</i>" if is_streaks_sess_active else "🧪 <i>Демо-режим (очікує SessionID)</i>"

    gf_text = f"<b>@{html.escape(gf['username'])}</b> ({html.escape(gf.get('nickname') or 'Кохана')}) ❤️" if gf else "❌ <i>Не встановлено (натисніть кнопку нижче)</i>"

    text = (
        "🔥 <b>Автоматизація #2: TikTok Вогники & Дівчина (Streaks)</b>\n\n"
        f"👸 <b>Акаунт коханої:</b> {gf_text}\n"
        f"👥 <b>Контактів для вогників:</b> {stats['total_targets']} чол.\n"
        f"💌 <b>Надіслано сьогодні:</b> {stats['sent_today']}\n"
        f"🔥 <b>Максимальна серія:</b> {stats['max_streak']} днів\n"
        f"⏰ <b>Розклад відправки:</b> щодня о <code>{schedule_time}</code>\n"
        f"🔑 <b>Канал вогників (Особистий):</b> {streaks_sess_badge}\n"
        f"🎬 <b>Канал заливу відео:</b> <i>повністю окремий акаунт</i>\n\n"
        "<b>Як це працює:</b>\n"
        "• 💖 <b>Для дівчини:</b> Gemini ШІ щодня генерує унікальні романтичні повідомлення з сердечками (❤️, 🥰, 💖) та компліментами!\n"
        "• 🔥 <b>Для інших контактів:</b> надсилаються дружні нагадування з вогником для збереження серії.\n"
        "• ⚡️ <b>Відповіді на відео:</b> Gemini аналізує скинуті вам TikTok відео та автоматично надсилає влучні реакції!\n"
        "• 🛡 <b>Безпека:</b> US/NY IP + людський jitter (3-7 сек) між відправками."
    )
    await target_msg.answer(text, reply_markup=get_streak_menu_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "streak_run_now")
async def callback_streak_run_now(call: CallbackQuery):
    await call.answer("🚀 Запуск щоденної відправки вогників...", show_alert=False)
    status_msg = await call.message.answer("⏳ <b>Відправляємо вогники у TikTok...</b> Зачекайте декілька секунд...")

    res = await tiktok_streak_service.run_streaks_dispatch()

    if not res.get("details"):
        await status_msg.edit_text(
            f"ℹ️ {html.escape(res.get('message', 'Список контактів порожній.'))}",
            reply_markup=get_streak_menu_keyboard(),
            parse_mode="HTML"
        )
        return

    text = (
        f"🏁 <b>Звіт відправки вогників ({res['executed_at']}):</b>\n\n"
        f"👥 Всього контактів: {res['total_targets']}\n"
        f"✅ Успішно опрацьовано: {res['sent_count']}\n\n"
        "<b>Деталі відправок:</b>\n"
    )

    for item in res["details"]:
        icon = "❤️ 👸" if item["is_girlfriend"] else "🔥"
        msg_preview = html.escape(item["message"][:60])
        status_badge = "✅" if item["status"] in ("sent", "dry_run") else "❌"
        text += f"{icon} <b>@{html.escape(item['username'])}</b> {status_badge}\n  <i>\"{msg_preview}...\"</i>\n"
        if item.get("error") and "Демо" in item["error"]:
            text += f"  🧪 <code>{html.escape(item['error'])}</code>\n"

    await status_msg.edit_text(text, reply_markup=get_streak_menu_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "streak_preview_gf")
async def callback_streak_preview_gf(call: CallbackQuery):
    gf = get_girlfriend_target()
    gf_name = gf["username"] if gf else "кохана"
    preview_msg = tiktok_streak_service.generate_girlfriend_heart_message()

    text = (
        f"💖 <b>Приклад повідомлення для дівчини (@{html.escape(gf_name)}):</b>\n\n"
        f"<i>«{html.escape(preview_msg)}»</i>\n\n"
        "ШІ формує щодня новий варіант із різноманітними сердечками, щоб повідомлення ніколи не повторювалися!"
    )
    await call.message.answer(text, reply_markup=get_streak_menu_keyboard(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "streak_decay_check")
async def callback_streak_decay_check(call: CallbackQuery):
    expiring = tiktok_streak_service.check_streak_decay_warnings(threshold_hours=20.0)
    if not expiring:
        await call.message.answer(
            "🟢 <b>Усі вогники в безпеці!</b>\nУсі ваші контакти активні, і сьогоднішня серія збережена.",
            reply_markup=get_streak_menu_keyboard(),
            parse_mode="HTML"
        )
        await call.answer()
        return

    text = "⚠️ <b>Увага! Термінові вогники під загрозою згасання:</b>\n\n"
    for item in expiring:
        icon = "❤️ 👸" if item.get("is_girlfriend") else "🔥"
        name = item.get("nickname") or item["username"]
        elapsed = item.get("hours_elapsed", 0)
        text += f"{icon} <b>@{html.escape(item['username'])}</b> ({html.escape(name)}): "
        if elapsed >= 900:
            text += "<i>сьогодні ще не відправляли!</i> 🔴\n"
        else:
            text += f"<i>минуло {elapsed} год!</i> ⚠️\n"

    text += "\n💡 Натисніть <b>'🚀 Відправити всім вогники зараз'</b>, щоб врятувати серії!"
    await call.message.answer(text, reply_markup=get_streak_menu_keyboard(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "streak_check_incoming_videos")
async def callback_streak_check_incoming_videos(call: CallbackQuery):
    await call.answer("🔍 Перевіряємо вхідні відео...", show_alert=False)
    status_msg = await call.message.answer(
        "⏳ <b>Перевіряємо чати TikTok на надіслані відео через Gemini...</b>\n"
        "Завантажуємо та аналізуємо контент у Playwright..."
    )
    try:
        results = await tiktok_streak_service.check_and_react_to_shared_videos()
        if not results:
            await status_msg.edit_text(
                "👌 <b>Усі надіслані відео вже мають відповіді!</b>\n"
                "Нових непрокоментованих TikTok відео від контактів наразі немає.",
                reply_markup=get_streak_menu_keyboard(),
                parse_mode="HTML"
            )
            return

        text = (
            f"🎬 <b>Успішно відреаговано на {len(results)} відео через Gemini!</b>\n\n"
        )
        for r in results:
            tag = "❤️ 👸 Кохана" if r.get("is_girlfriend") else "🔥 Друг"
            user = html.escape(r.get("username", "користувач"))
            reaction = html.escape(r.get("reaction", ""))
            v_url = r.get("video_url", "")
            text += (
                f"{tag}: <b>@{user}</b>\n"
                f"🔗 <a href='{v_url}'>Відео</a>\n"
                f"💬 Реакція: <i>«{reaction}»</i>\n\n"
            )
        await status_msg.edit_text(text, reply_markup=get_streak_menu_keyboard(), parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Помилка callback_streak_check_incoming_videos: {e}")
        await status_msg.edit_text(
            f"⚠️ <b>Помилка під час перевірки відео:</b> <code>{html.escape(str(e))}</code>",
            reply_markup=get_streak_menu_keyboard(),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "streak_set_gf")
async def callback_streak_set_gf(call: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_gf_username)
    await call.message.answer(
        "👸 <b>Введіть TikTok нікнейм вашої дівчини</b> (без @ або з @):\n\n"
        "<i>Наприклад:</i> <code>olenka_love</code>\n"
        "Бот автоматично закріпить її акаунт для надсилання милих сердечок та теплих побажань щодня ❤️",
        parse_mode="HTML"
    )
    await call.answer()


@router.message(BotStates.waiting_for_gf_username)
async def process_gf_username(message: Message, state: FSMContext):
    raw_user = message.text.strip().lstrip("@")
    if raw_user:
        set_girlfriend_target(raw_user, "Кохана")
        sample = tiktok_streak_service.generate_girlfriend_heart_message()
        await message.answer(
            f"✅ <b>Акаунт дівчини успішно збережено: @{html.escape(raw_user)}!</b> ❤️\n\n"
            f"💌 <b>Приклад сердечок, які вона отримає:</b>\n<i>«{html.escape(sample)}»</i>\n\n"
            "Щодня бот автоматично надсилатиме їй унікальні романтичні повідомлення!",
            reply_markup=get_streak_menu_keyboard(),
            parse_mode="HTML"
        )
    await state.clear()


@router.callback_query(F.data == "streak_list_targets")
async def callback_streak_list_targets(call: CallbackQuery):
    targets = get_streak_targets(active_only=False)
    if not targets:
        await call.message.answer(
            "📋 Список контактів для вогників порожній.\nНатисніть '➕ Додати контакт', щоб внести друзів або дівчину!",
            reply_markup=get_streak_menu_keyboard()
        )
        await call.answer()
        return

    text = "👥 <b>Керування контактами для вогників (TikTok Streaks):</b>\nНатисніть ❌ біля контакту, щоб видалити його:\n"
    await call.message.edit_text(text, reply_markup=get_streak_targets_management_keyboard(targets), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("target_del:"))
async def callback_target_del(call: CallbackQuery):
    username = call.data.split(":")[1]
    remove_streak_target(username)
    await call.answer(f"@{username} видалено зі списку")
    targets = get_streak_targets(active_only=False)
    if targets:
        await call.message.edit_reply_markup(reply_markup=get_streak_targets_management_keyboard(targets))
    else:
        await call.message.edit_text("📋 Список контактів порожній.", reply_markup=get_streak_menu_keyboard())


@router.callback_query(F.data == "streak_add_target")
async def callback_streak_add_target(call: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_new_streak_target)
    await call.message.answer(
        "➕ <b>Надішліть нікнейм друга у TikTok</b> для підтримки вогника:\n\n"
        "<i>Формат:</i> <code>username</code> або <code>username (Ім'я друга)</code>\n"
        "<i>Наприклад:</i> <code>vlad_it (Влад)</code>",
        parse_mode="HTML"
    )
    await call.answer()


@router.message(BotStates.waiting_for_new_streak_target)
async def process_new_streak_target(message: Message, state: FSMContext):
    text = message.text.strip()
    parts = text.split(maxsplit=1)
    username = parts[0].lstrip("@")
    nickname = parts[1].strip("()") if len(parts) > 1 else username

    if username:
        add_streak_target(username, nickname=nickname, is_girlfriend=False)
        await message.answer(
            f"✅ <b>Контакт @{html.escape(username)} успішно додано до списку вогників!</b> 🔥\n"
            f"Тепер він щодня отримуватиме вогник для збереження серії.",
            reply_markup=get_streak_menu_keyboard(),
            parse_mode="HTML"
        )
    await state.clear()


@router.callback_query(F.data == "streak_schedule")
async def callback_streak_schedule(call: CallbackQuery, state: FSMContext):
    current = get_setting("tiktok_streak_schedule_time", "10:00")
    await state.set_state(BotStates.waiting_for_streak_schedule)
    await call.message.answer(
        f"⏰ <b>Налаштування щоденного часу відправки:</b>\n\n"
        f"Поточний час: <code>{current}</code>\n"
        "Введіть новий час у форматі <code>ГГ:ХХ</code> (наприклад: <code>10:00</code> або <code>09:30</code>):",
        parse_mode="HTML"
    )
    await call.answer()


@router.message(BotStates.waiting_for_streak_schedule)
async def process_streak_schedule(message: Message, state: FSMContext):
    t_str = message.text.strip()
    # Валідація часу
    try:
        datetime.strptime(t_str, "%H:%M")
        set_setting("tiktok_streak_schedule_time", t_str)
        await message.answer(
            f"✅ <b>Час розкладу оновлено!</b>\nЩоденна відправка відбуватиметься о <code>{t_str}</code>.",
            reply_markup=get_streak_menu_keyboard(),
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer(
            "⚠️ Невірний формат часу. Введіть, будь ласка, у форматі <code>10:00</code>.",
            reply_markup=get_streak_menu_keyboard(),
            parse_mode="HTML"
        )
    await state.clear()


@router.callback_query(F.data == "streak_logs")
async def callback_streak_logs(call: CallbackQuery):
    logs = get_recent_streak_logs(limit=10)
    if not logs:
        await call.message.answer("📜 Журнал відправок вогників порожній.", reply_markup=get_streak_menu_keyboard())
        await call.answer()
        return

    text = "📜 <b>Останні відправки вогників:</b>\n\n"
    for item in logs:
        icon = "❤️ 👸" if item["is_girlfriend"] else "🔥"
        status_ico = "✅" if item["status"] in ("sent", "dry_run") else "❌"
        msg = html.escape(item["message_text"][:50])
        time_str = item["sent_at"][:16]
        text += f"{icon} <b>@{html.escape(item['target_username'])}</b> {status_ico} ({time_str})\n  <i>\"{msg}...\"</i>\n\n"

    await call.message.answer(text, reply_markup=get_streak_menu_keyboard(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "streak_set_session")
async def callback_streak_set_session(call: CallbackQuery, state: FSMContext):
    curr = tiktok_streak_service.get_streaks_session_id()
    status_text = "🟢 <b>Підключено</b> (окрема сесія активна)" if tiktok_streak_service.is_streaks_session_configured() else "🧪 <b>Демо-режим</b> (ще не встановлено)"
    masked_sess = (curr[:6] + "..." + curr[-4:]) if len(curr) > 10 else "не налаштовано"

    await state.set_state(BotStates.waiting_for_streak_session)
    await call.message.answer(
        f"🔑 <b>Окремий TikTok акаунт для вогників (SessionID)</b>\n\n"
        f"Поточний статус: {status_text}\n"
        f"Поточна сесія: <code>{masked_sess}</code>\n\n"
        "💡 <i>Цей акаунт використовується ВИКЛЮЧНО для щоденних вогників з друзями та сердечок дівчині. "
        "Він повністю ізольований від каналу, на який заливаються відео!</i>\n\n"
        "Щоб оновити сесію, надішліть значення кукі <code>sessionid</code> вашого особистого TikTok акаунта "
        "(або вкажіть <code>TIKTOK_STREAKS_SESSION_ID</code> у файлі <code>.env</code>).\n\n"
        "<i>Надішліть sessionid у відповідь або напишіть /cancel для скасування:</i>",
        parse_mode="HTML"
    )
    await call.answer()


@router.message(BotStates.waiting_for_streak_session)
async def process_streak_session_id(message: Message, state: FSMContext):
    sess_text = message.text.strip()
    if sess_text.startswith("/"):
        await state.clear()
        await message.answer("❌ Скасовано.", reply_markup=get_streak_menu_keyboard())
        return

    set_setting("tiktok_streaks_session_id", sess_text)
    masked = (sess_text[:6] + "..." + sess_text[-4:]) if len(sess_text) > 10 else "збережено"
    await message.answer(
        f"✅ <b>Окремий акаунт для вогників успішно налаштовано!</b> 🔥\n"
        f"SessionID: <code>{masked}</code>\n\n"
        "Тепер щоденна розсилка вогників та сердечок надсилатиметься з вашого особистого профілю, "
        "а відео публікуватимуться на ваш окремий контентний канал!",
        reply_markup=get_streak_menu_keyboard(),
        parse_mode="HTML"
    )
    await state.clear()


# ---------------------------------------------------------
# БОТ "КІБЕР РИЖИЙ" ТА РЕАКЦІЇ НА TIKTOK (КОМАНДИ & UI)
# ---------------------------------------------------------

@router.message(Command("rizhyi"))
async def cmd_rizhyi(message: Message):
    """Пряме звернення до Кібер Рижого через команду /rizhyi [повідомлення]"""
    args = message.text.replace("/rizhyi", "").strip()
    if not args:
        args = "дарова"

    reply = cyber_rizhyi_service.generate_reply(
        chat_id=message.chat.id,
        chat_type=message.chat.type,
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        message_text=args,
        has_photo=False
    )
    await message.reply(reply)


@router.message(Command("tiktok_react"))
async def cmd_tiktok_react(message: Message, state: FSMContext):
    """Команда для генерації реакції у стилі Боді на будь-який TikTok"""
    args = message.text.replace("/tiktok_react", "").strip()
    if not args:
        await state.set_state(BotStates.waiting_for_tiktok_reaction_url)
        await message.answer("🎬 <b>Надішліть посилання на TikTok відео</b>, і я згенерую фірмову реакцію у стилі Боді:", parse_mode="HTML")
        return

    status_msg = await message.answer("⏳ <b>Завантажуємо та аналізуємо через Gemini...</b>")
    try:
        res = tiktok_reactions_service.process_tiktok_link(args)
        await status_msg.edit_text(
            f"🎬 <b>Реакція Боді на TikTok:</b>\n\n"
            f"💬 <b>{html.escape(res['reaction'])}</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Помилка cmd_tiktok_react: {e}")
        await status_msg.edit_text(f"💬 <b>{html.escape(tiktok_reactions_service.generate_reaction())}</b>", parse_mode="HTML")


@router.message(Command("check_videos"))
async def cmd_check_videos(message: Message):
    """Команда швидкої перевірки та реагування на надіслані TikTok відео через Gemini"""
    if not is_user_allowed(message.from_user.id):
        return
    status_msg = await message.answer(
        "⏳ <b>Перевіряємо чати TikTok на надіслані відео через Gemini...</b>\n"
        "Завантажуємо та аналізуємо контент у Playwright..."
    )
    try:
        results = await tiktok_streak_service.check_and_react_to_shared_videos()
        if not results:
            await status_msg.edit_text(
                "👌 <b>Усі надіслані відео вже мають відповіді!</b>\n"
                "Нових непрокоментованих TikTok відео від контактів наразі немає.",
                reply_markup=get_streak_menu_keyboard(),
                parse_mode="HTML"
            )
            return

        text = (
            f"🎬 <b>Успішно відреаговано на {len(results)} відео через Gemini!</b>\n\n"
        )
        for r in results:
            tag = "❤️ 👸 Кохана" if r.get("is_girlfriend") else "🔥 Друг"
            user = html.escape(r.get("username", "користувач"))
            reaction = html.escape(r.get("reaction", ""))
            v_url = r.get("video_url", "")
            text += (
                f"{tag}: <b>@{user}</b>\n"
                f"🔗 <a href='{v_url}'>Відео</a>\n"
                f"💬 Реакція: <i>«{reaction}»</i>\n\n"
            )
        await status_msg.edit_text(text, reply_markup=get_streak_menu_keyboard(), parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Помилка cmd_check_videos: {e}")
        await status_msg.edit_text(
            f"⚠️ <b>Помилка під час перевірки відео:</b> <code>{html.escape(str(e))}</code>",
            reply_markup=get_streak_menu_keyboard(),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "menu_cyber_rizhyi")
async def callback_cyber_rizhyi(call: CallbackQuery):
    """Дашборд бота 'Кібер Рижий'"""
    mem = get_cyber_rizhyi_user_memory(call.from_user.id)
    history = get_cyber_rizhyi_chat_history(call.message.chat.id, limit=5)
    model_name = cyber_rizhyi_service.model

    text = (
        "🤖 <b>Бот «Кібер Рижий» (Groq 120B & Пам'ять)</b>\n\n"
        "Цифрова копія справжнього Сані (Рижого), навчена на понад <b>2 600 реальних репліках</b> із чату!\n\n"
        f"⚡️ <b>Рушій:</b> Groq API (<code>{html.escape(model_name)}</code>)\n"
        "👁 <b>Vision:</b> Мультимодальний аналіз фото через Gemini AI\n"
        "🧠 <b>Пам'ять:</b> SQLite довгострокові спогади та контекст чатів\n"
        "👥 <b>Робота в групі:</b> Відповідає на всі повідомлення та фото у групових чатах\n\n"
        "<b>Як користуватися:</b>\n"
        "• Додайте бота у будь-яку групу - він почне жити там і коментувати все як Рижий!\n"
        "• Або напишіть <code>/rizhyi [повідомлення]</code>\n"
        "• Якщо скинути фото у групу - Рижий його розгледить і видасть базу!"
    )
    await call.message.answer(text, reply_markup=get_cyber_rizhyi_keyboard(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.in_(["menu_tiktok_react", "streak_tiktok_react"]))
async def callback_menu_tiktok_react(call: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_tiktok_reaction_url)
    await call.message.answer(
        "🎬 <b>Надішліть посилання на TikTok відео:</b>\n"
        "(Бот завантажить його через yt-dlp, прожене через Gemini та згенерує реакцію у стилі Боді з експорту чатів):",
        parse_mode="HTML"
    )
    await call.answer()


@router.message(BotStates.waiting_for_tiktok_reaction_url)
async def process_tiktok_reaction_url(message: Message, state: FSMContext):
    url = tiktok_reactions_service.extract_tiktok_url(message.text) or message.text.strip()
    status_msg = await message.answer("⏳ <b>Завантажуємо TikTok та генеруємо реакцію у стилі Боді...</b>")
    try:
        res = tiktok_reactions_service.process_tiktok_link(url)
        author_str = f"@{res['uploader']}" if res.get("uploader") else "TikTok"
        await status_msg.edit_text(
            f"🎬 <b>Реакція Боді на TikTok ({author_str}):</b>\n\n"
            f"💬 <b>{html.escape(res['reaction'])}</b>",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Помилка process_tiktok_reaction_url: {e}")
        await status_msg.edit_text(
            f"💬 <b>{html.escape(tiktok_reactions_service.generate_reaction())}</b>",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML"
        )
    await state.clear()


@router.callback_query(F.data == "rizhyi_test_reply")
async def callback_rizhyi_test_reply(call: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_rizhyi_test_input)
    await call.message.answer("💬 <b>Напиши щось Рижому у наступному повідомленні</b> (перевіримо як він відповість):", parse_mode="HTML")
    await call.answer()


@router.message(BotStates.waiting_for_rizhyi_test_input)
async def process_rizhyi_test_input(message: Message, state: FSMContext):
    reply = cyber_rizhyi_service.generate_reply(
        chat_id=message.chat.id,
        chat_type=message.chat.type,
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        message_text=message.text,
        has_photo=False
    )
    await message.reply(f"🤖 <b>Рижий:</b> {html.escape(reply)}", parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "rizhyi_memory_check")
async def callback_rizhyi_memory_check(call: CallbackQuery):
    mem = get_cyber_rizhyi_user_memory(call.from_user.id)
    name = call.from_user.first_name or call.from_user.username or "Кент"
    if not mem:
        text = f"🧠 <b>Пам'ять про тебе ({html.escape(name)}):</b>\n\nРижий ще збирає факти про тебе під час спілкування. Поспілкуйся з ним, розкажи своє ім'я або в що граєш!"
    else:
        text = f"🧠 <b>Що Рижий пам'ятає про тебе ({html.escape(name)}):</b>\n\n"
        for k, v in mem.items():
            text += f"• <b>{html.escape(k)}:</b> {html.escape(v)}\n"

    await call.message.answer(text, reply_markup=get_cyber_rizhyi_keyboard(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "rizhyi_test_photo")
async def callback_rizhyi_test_photo(call: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_rizhyi_photo_test)
    await call.message.answer("📸 <b>Надішли будь-яке фото або мем</b>, і Рижий зреагує на нього через Gemini Vision:", parse_mode="HTML")
    await call.answer()


@router.message(BotStates.waiting_for_rizhyi_photo_test, F.photo)
async def process_rizhyi_photo_test(message: Message, bot: Bot, state: FSMContext):
    status_msg = await message.answer("👀 <b>Рижий роздивляється фото через Gemini...</b>")
    try:
        photo_obj = message.photo[-1]
        file_info = await bot.get_file(photo_obj.file_id)
        local_path = DOWNLOADS_DIR / f"test_rizhyi_{message.from_user.id}.jpg"
        await bot.download_file(file_info.file_path, destination=local_path)

        reply = cyber_rizhyi_service.generate_reply(
            chat_id=message.chat.id,
            chat_type=message.chat.type,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            message_text=message.caption or "",
            has_photo=True,
            photo_path=str(local_path)
        )
        await status_msg.edit_text(f"🤖 <b>Рижий:</b> {html.escape(reply)}", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Помилка тесту фото Рижого: {e}")
        await status_msg.edit_text("🤖 <b>Рижий:</b> шо це за херня")
    await state.clear()


@router.callback_query(F.data == "rizhyi_model_info")
async def callback_rizhyi_model_info(call: CallbackQuery):
    groq_ready = bool(cyber_rizhyi_service.api_key and not cyber_rizhyi_service.api_key.startswith("gsk_your_"))
    gemini_ready = bool(gemini_service.api_key and not gemini_service.api_key.startswith("AIzaSyYour"))
    status_groq = "✅ Підключено" if groq_ready else "⏳ Очікує ключ у .env (працює розумний Demo-архів)"
    status_gemini = "✅ Мультимодальний Vision активний" if gemini_ready else "⏳ Демо Vision"

    text = (
        "⚡️ <b>Конфігурація моделі та рушіїв Кібер Рижого:</b>\n\n"
        f"• <b>Groq Model:</b> <code>{html.escape(cyber_rizhyi_service.model)}</code>\n"
        f"• <b>Groq API:</b> {status_groq}\n"
        f"• <b>Gemini Vision (Фото):</b> {status_gemini}\n"
        "• <b>Швидкість генерації:</b> до 500 токенів/сек на Groq LPU\n"
        "• <b>База реплік:</b> 2 623 реальних повідомлень Сані з 10 файлів чату\n"
        "• <b>Типографіка:</b> строго дефіс '-' (нуль довгих тире)"
    )
    await call.message.answer(text, reply_markup=get_cyber_rizhyi_keyboard(), parse_mode="HTML")
    await call.answer()

