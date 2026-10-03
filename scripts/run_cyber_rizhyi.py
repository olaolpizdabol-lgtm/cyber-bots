"""
🤖 Автономний запуск бота "Кібер Рижий" (Cyber Rizhyi Standalone Runner)

Цей скрипт запускає окремого Telegram-бота «Кібер Рижий»:
1. Читає CYBER_RIZHYI_BOT_TOKEN з .env
2. Відповідає на кожне повідомлення у групах та особистих чатах (1-в-1 стиль Рижого на базі Groq 120B)
3. Аналізує надіслані фото через Gemini Vision
4. Транскрибує та коментує голосові повідомлення через Groq Whisper
5. Автоматично реагує на посилання TikTok у стилі Боді
6. Має довгострокову пам'ять (SQLite) та лор про Діджея Куріла Рулєта й Турікова
"""
import asyncio
import logging
import html
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, ReactionTypeEmoji
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage

from config import (
    CYBER_RIZHYI_BOT_TOKEN,
    TELEGRAM_BOT_TOKEN,
    CYBER_RIZHYI_ENABLED,
    CYBER_RIZHYI_RESPOND_ALL_GROUP_MSGS,
    DOWNLOADS_DIR
)
from services.cyber_rizhyi import cyber_rizhyi_service, clean_bot_reply
from services.cyber_turikov import cyber_turikov_service
from services.tiktok_reactions import tiktok_reactions_service
from core.database import (
    init_db,
    save_cyber_rizhyi_message,
    get_cyber_rizhyi_chat_history,
    get_cyber_rizhyi_user_memory,
    cleanup_cyber_rizhyi_expired_messages,
    get_recent_chat_users,
    get_active_cyber_rizhyi_chats,
    save_cyber_media,
    get_random_cyber_media,
    get_chat_persona,
    set_chat_persona,
    enqueue_cyber_bot_event,
    get_unprocessed_cyber_bot_events,
    mark_cyber_bot_event_processed,
    get_cyber_rizhyi_chat_history,
    is_cyber_chat_silent_for_minutes,
)
from services.cyber_routing import (
    is_message_addressed_to_bot,
    get_message_target,
    get_user_display_name,
    RIZHYI_BOT_ID,
    TURIKOV_BOT_ID
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] cyber_rizhyi: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("cyber_rizhyi")

router = Router()
_handled_group_msg_ids: set[int] = set()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "дарова я кібер рижий 🤙🤙🤙\n"
        "додай мене в групу або пиши сюда го в кс чи шо"
    )


@router.message(F.new_chat_members)
async def handle_new_members(message: Message, bot: Bot):
    """Привітання при додаванні в групу"""
    bot_info = await bot.get_me()
    for member in (message.new_chat_members or []):
        if member.id == bot_info.id:
            await message.reply("дарова пацани 🤙🤙🤙 я тута го в кс чи шо")
            return


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📌 <b>Команди Кібер Рижого:</b>\n\n"
        "• <code>/start</code> - привітання\n"
        "• <code>/memory</code> - що Рижий пам'ятає про тебе\n"
        "• <code>/lore</code> - лор про Діджея Куріла Рулєта та Турікова\n"
        "• Кидай будь-яке <b>фото</b> - Рижий роздивиться через Gemini\n"
        "• Кидай <b>голосове повідомлення</b> - Рижий розшифрує через Groq\n"
        "• Кидай <b>посилання на TikTok</b> - отримай фірмову реакцію Боді",
        parse_mode="HTML"
    )


@router.message(Command("memory"))
async def cmd_memory(message: Message):
    mem = get_cyber_rizhyi_user_memory(message.from_user.id)
    name = message.from_user.first_name or message.from_user.username or "Бро"
    if not mem:
        await message.reply(f"Ше мало спілкувались, {name}, я запам'ятовую по ходу діла.")
        return

    text = f"🧠 <b>Шо я про тебе знаю ({html.escape(name)}):</b>\n\n"
    for k, v in mem.items():
        k_clean = k.replace("_", " ").capitalize()
        text += f"• <b>{html.escape(k_clean)}:</b> {html.escape(str(v))}\n"
    await message.reply(text, parse_mode="HTML")


@router.message(Command("lore"))
async def cmd_lore(message: Message):
    text = (
        "🔊 <b>Фірмовий лор:</b>\n\n"
        "• <b>Діджей Куріл Рулєт:</b> туси на балконі, підставив Артура Мікаєляна, 'Універ 17 лєт накурений рулетом', брат Єгор.\n"
        "• <b>Саня Туріков (Турікоголовий):</b> курить гонджубаси, п'є маленьку колу, їздить на електросамокаті з повним зарядом, 'Саша туріков маладєц а єгор з хрущами холодец'.\n"
        "• <b>Коло кращих бро:</b> Міша, Діма, Бодя."
    )
    await message.reply(text, parse_mode="HTML")


def get_service_for_chat(chat_id: int):
    """Повертає сервіс активного персонажа для чату: Саня Рижий або Саня Туріков"""
    persona = get_chat_persona(chat_id, default="rizhyi")
    if persona == "turikov":
        return cyber_turikov_service
    return cyber_rizhyi_service


# Емодзі-реакції які може ставити Рижий (відповідає характеру)
RIZHYI_REACTIONS = ["👍", "💀", "🤙", "😂", "😐", "🔥", "👎", "😱", "🤡", "💯"]

async def try_set_reaction(bot: Bot, chat_id: int, message_id: int) -> bool:
    """Ставить emoji-реакцію на повідомлення. Повертає True якщо вдалось."""
    try:
        emoji = random.choice(RIZHYI_REACTIONS)
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)]
        )
        return True
    except Exception:
        return False


async def send_burst_replies(message: Message, bot: Bot, replies: list[str]) -> list[Message]:
    """Надсилає серію з 1-3 повідомлень з натуральними затримками друку (манера підлітка в Telegram)"""
    sent = []
    if not replies:
        return sent
    for idx, rep in enumerate(replies):
        if idx == 0:
            m = await message.reply(rep)
            sent.append(m)
        else:
            await asyncio.sleep(random.uniform(0.7, 1.4))
            try:
                await bot.send_chat_action(chat_id=message.chat.id, action="typing")
                await asyncio.sleep(random.uniform(0.5, 1.2))
            except Exception:
                pass
            m = await message.answer(rep)
            sent.append(m)
    return sent


async def send_reply_package(message: Message, bot: Bot, pkg: dict):
    """Надсилає повний пакет реакції: стікер/анімацію та текстові повідомлення чергою"""
    sticker_id = pkg.get("sticker_file_id")
    animation_id = pkg.get("animation_file_id")
    text_replies = pkg.get("text_replies") or []
    sent_msgs = []

    if sticker_id:
        try:
            m = await bot.send_sticker(chat_id=message.chat.id, sticker=sticker_id, reply_to_message_id=message.message_id)
            sent_msgs.append(m)
        except Exception as e:
            logger.warning(f"Не вдалося відправити стікер: {e}")

    if animation_id:
        try:
            m = await bot.send_animation(chat_id=message.chat.id, animation=animation_id, reply_to_message_id=message.message_id)
            sent_msgs.append(m)
        except Exception as e:
            logger.warning(f"Не вдалося відправити анімацію: {e}")

    if text_replies:
        sent = await send_burst_replies(message, bot, text_replies)
        sent_msgs.extend(sent)

    # Ставимо подію в міжботовий міст, щоб Саня Туріков чув кожну репліку Рижого в групі і міг вступити в діалог
    if message.chat.type in ("group", "supergroup") and sent_msgs and text_replies:
        try:
            full_reply_text = " ".join(text_replies)
            last_msg = sent_msgs[-1]
            enqueue_cyber_bot_event(
                chat_id=message.chat.id,
                from_bot="rizhyi",
                to_bot="turikov",
                message_id=last_msg.message_id,
                text=full_reply_text,
                consecutive_count=0,
                sender_user_id=bot.id,
                sender_username="cyber_red_head_bot",
                sender_first_name="Саня Рижий",
                reply_to_name="Саня Туріков"
            )
        except Exception as e:
            logger.debug(f"Міжботовий міст помилка enqueue: {e}")


@router.message(Command("turikov", "persona_turikov"))
async def cmd_switch_turikov(message: Message):
    """Перемикає чат на Саню Турікова"""
    set_chat_persona(message.chat.id, "turikov")
    await message.reply("Здаров, тепер я Саня Туріков (Турікоголовий) 🤙\nШо ти пупсик, на площадці в карти пограємо?")


@router.message(Command("rizhyi", "persona_rizhyi"))
async def cmd_switch_rizhyi(message: Message):
    """Перемикає чат на Саню Рижого"""
    set_chat_persona(message.chat.id, "rizhyi")
    await message.reply("Дарова, переключився на Рижого 🤙 го в кс чи шо")


@router.message(Command("persona", "character", "mode"))
async def cmd_persona(message: Message):
    """Показує поточну активну персону та команди перемикання"""
    current = get_chat_persona(message.chat.id, default="rizhyi")
    curr_name = "Саня Туріков (Турікоголовий)" if current == "turikov" else "Саня Рижий (@sigma rigiu)"
    await message.reply(
        f"🎭 <b>Активна персона в цьому чаті:</b> <code>{curr_name}</code>\n\n"
        "<b>Команди перемикання:</b>\n"
        "• <code>/turikov</code> - Саня Туріков (Чернівці, пупсик, карти на площадці, тайстра, 쇼쇼)\n"
        "• <code>/rizhyi</code> - Саня Рижий (CS2, міраж, комп лагає, Діджей Куріл Рулєт)",
        parse_mode="HTML"
    )


@router.message(Command("spontaneous", "shout", "tag"))
async def cmd_spontaneous(message: Message, bot: Bot):
    """Команда для ручного виклику спонтанного вигуку та тегання учасників у чаті"""
    service = get_service_for_chat(message.chat.id)
    messages, tagged = service.generate_spontaneous_shout(message.chat.id)
    for idx, rep in enumerate(messages):
        if idx > 0:
            await asyncio.sleep(0.8)
            try:
                await bot.send_chat_action(chat_id=message.chat.id, action="typing")
                await asyncio.sleep(0.8)
            except Exception:
                pass
        await message.answer(rep)


@router.message(F.sticker)
async def handle_sticker(message: Message, bot: Bot):
    """Обробка стікерів: запам'ятовує стікер у базу і відповідає текстом чи стікером у відповідь"""
    try:
        st = message.sticker
        save_cyber_media(
            chat_id=message.chat.id,
            media_type="sticker",
            file_id=st.file_id,
            file_unique_id=st.file_unique_id,
            emoji=st.emoji,
            set_name=st.set_name
        )

        if not is_message_addressed_to_bot(message, "rizhyi"):
            return

        service = get_service_for_chat(message.chat.id)
        pkg = service.generate_reply_package(
            chat_id=message.chat.id,
            chat_type=message.chat.type,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            message_text="",
            is_sticker=True,
            sticker_emoji=st.emoji
        )
        await send_reply_package(message, bot, pkg)
    except Exception as e:
        logger.error(f"Помилка стікера: {e}")


@router.message(F.animation)
async def handle_animation(message: Message, bot: Bot):
    """Обробка GIF (анімацій): запам'ятовує і відповідає в тему розмови"""
    try:
        anim = message.animation
        save_cyber_media(
            chat_id=message.chat.id,
            media_type="animation",
            file_id=anim.file_id,
            file_unique_id=anim.file_unique_id
        )

        if not is_message_addressed_to_bot(message, "rizhyi"):
            return

        service = get_service_for_chat(message.chat.id)
        pkg = service.generate_reply_package(
            chat_id=message.chat.id,
            chat_type=message.chat.type,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            message_text="",
            is_animation=True
        )
        await send_reply_package(message, bot, pkg)
    except Exception as e:
        logger.error(f"Помилка анімації: {e}")


@router.message(F.video | F.video_note)
async def handle_video_message(message: Message, bot: Bot):
    """Обробка звичайних відео та відео-кружечків через Gemini Multimodal"""
    try:
        video_obj = message.video or message.video_note
        if not video_obj:
            return

        if getattr(video_obj, "file_size", 0) > 25 * 1024 * 1024:
            await message.reply("ого яке здорове відео, в мене тел зависне")
            return

        file_info = await bot.get_file(video_obj.file_id)
        local_path = DOWNLOADS_DIR / f"rizhyi_vid_{message.from_user.id}_{message.message_id}.mp4"
        await bot.download_file(file_info.file_path, destination=local_path)

        if not is_message_addressed_to_bot(message, "rizhyi"):
            return

        service = get_service_for_chat(message.chat.id)
        pkg = service.generate_reply_package(
            chat_id=message.chat.id,
            chat_type=message.chat.type,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            message_text=message.caption or "",
            has_video=True,
            video_path=str(local_path)
        )
        await send_reply_package(message, bot, pkg)
        try:
            if local_path.exists():
                local_path.unlink()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Помилка відео-повідомлення: {e}")


@router.message(F.photo | (F.document & F.document.mime_type.startswith("image/")))
async def handle_photo(message: Message, bot: Bot):
    """Обробка фото через Gemini Vision з підтримкою черги повідомлень"""
    try:
        photo_obj = message.photo[-1] if message.photo else message.document
        file_info = await bot.get_file(photo_obj.file_id)
        file_ext = Path(file_info.file_path).suffix or ".jpg"
        local_path = DOWNLOADS_DIR / f"rizhyi_standalone_{message.from_user.id}_{message.message_id}{file_ext}"
        await bot.download_file(file_info.file_path, destination=local_path)

        if not is_message_addressed_to_bot(message, "rizhyi"):
            return

        service = get_service_for_chat(message.chat.id)
        pkg = service.generate_reply_package(
            chat_id=message.chat.id,
            chat_type=message.chat.type,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            message_text=message.caption or "",
            has_photo=True,
            photo_path=str(local_path)
        )
        await send_reply_package(message, bot, pkg)
    except Exception as e:
        logger.error(f"Помилка фото: {e}")
        await message.reply("шо це за херня")


@router.message(F.voice | F.audio)
async def handle_voice(message: Message, bot: Bot):
    """Обробка голосових повідомлень через Groq Whisper"""
    voice_obj = message.voice or message.audio
    if not voice_obj:
        return

    try:
        file_info = await bot.get_file(voice_obj.file_id)
        local_path = DOWNLOADS_DIR / f"rizhyi_standalone_voice_{message.from_user.id}_{message.message_id}.ogg"
        await bot.download_file(file_info.file_path, destination=local_path)

        if not is_message_addressed_to_bot(message, "rizhyi"):
            return

        service = get_service_for_chat(message.chat.id)
        pkg = service.generate_reply_package(
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
        await send_reply_package(message, bot, pkg)
    except Exception as e:
        logger.error(f"Помилка голосового повідомлення: {e}")
        await message.reply("ти шо войси шлеш? розпиши текстом або го в кс")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message, bot: Bot):
    """Обробка текстових повідомлень у групі та приватних чатах"""
    text = message.text.strip()
    is_group = message.chat.type in ("group", "supergroup")

    # 1. Перевірка на TikTok посилання
    if tiktok_reactions_service.is_tiktok_url(text):
        url = tiktok_reactions_service.extract_tiktok_url(text)
        try:
            res = tiktok_reactions_service.process_tiktok_link(url)
            await message.reply(
                f"🎬 <b>Реакція Боді:</b>\n{html.escape(res['reaction'])}",
                parse_mode="HTML"
            )
            return
        except Exception as e:
            logger.error(f"Помилка тікток: {e}")

    if message.from_user and (message.from_user.id == bot.id or message.from_user.id in (RIZHYI_BOT_ID, TURIKOV_BOT_ID)):
        return

    # 2. Розумне розпізнавання: кому саме адресоване повідомлення в групі
    target_name, target_id = get_message_target(message)
    reply_to_text = (message.reply_to_message.text or message.reply_to_message.caption) if message.reply_to_message else None

    if not is_message_addressed_to_bot(message, "rizhyi"):
        # Зберігаємо репліку в контекст пам'яті, щоб бот знав що відбувається, але не втручався
        save_cyber_rizhyi_message(
            chat_id=message.chat.id,
            chat_type=message.chat.type,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            message_text=text,
            reply_text=None,
            bot_persona="rizhyi",
            reply_to_user_id=target_id,
            reply_to_name=target_name,
            reply_to_msg_text=reply_to_text
        )
        # ВАЖЛИВО: Якщо це повідомлення адресоване Сані Турікову (або згадує його),
        # пересилаємо його Турікову через чергу подій на випадок, якщо в Telegram увімкнено Group Privacy mode!
        if is_group and is_message_addressed_to_bot(message, "turikov"):
            enqueue_cyber_bot_event(
                chat_id=message.chat.id,
                from_bot="user_relay",
                to_bot="turikov",
                message_id=message.message_id,
                text=text,
                consecutive_count=0,
                sender_user_id=message.from_user.id,
                sender_username=message.from_user.username,
                sender_first_name=message.from_user.first_name,
                reply_to_name="Саня Туріков"
            )
        return

    # 3. Відповідь активного персонажа (Саня Рижий чи Саня Туріков)
    service = get_service_for_chat(message.chat.id)
    pkg = service.generate_reply_package(
        chat_id=message.chat.id,
        chat_type=message.chat.type,
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        message_text=text,
        has_photo=False,
        reply_to_user_id=target_id,
        reply_to_name=target_name,
        reply_to_text=reply_to_text
    )
    _handled_group_msg_ids.add(message.message_id)
    await send_reply_package(message, bot, pkg)

    # Якщо це спільна група і повідомлення від людини — передаємо подію Турікову, щоб він ТАКОЖ включився в розмову!
    if is_group and message.from_user and not message.from_user.is_bot:
        try:
            enqueue_cyber_bot_event(
                chat_id=message.chat.id,
                from_bot="user_relay",
                to_bot="turikov",
                message_id=message.message_id,
                text=text,
                consecutive_count=0,
                sender_user_id=message.from_user.id,
                sender_username=message.from_user.username,
                sender_first_name=message.from_user.first_name,
                reply_to_name=target_name
            )
        except Exception as e:
            logger.debug(f"User relay to turikov error: {e}")

    # 40% шанс поставити реакцію разом із текстом
    if random.random() < 0.40:
        await asyncio.sleep(random.uniform(0.3, 1.0))
        await try_set_reaction(bot, message.chat.id, message.message_id)

    # Фоновий LLM-витяг фактів (не блокує відповідь)
    asyncio.ensure_future(_extract_facts_background(
        service, message.chat.id, message.from_user.id,
        message.from_user.username, message.from_user.first_name, text
    ))


async def _extract_facts_background(service, chat_id: int, user_id: int, username: str, first_name: str, text: str):
    """Фоновий витяг фактів через LLM після відповіді бота"""
    try:
        sender_name = first_name or username or "Кент"
        await asyncio.get_event_loop().run_in_executor(
            None,
            service.extract_facts_with_llm,
            chat_id, sender_name, username or "", user_id, text
        )
    except Exception as e:
        logger.debug(f"[Facts BG] Помилка: {e}")


async def spontaneous_rizhyi_worker(bot: Bot):
    """
    Фоновий воркер:
    1. Автоматично видаляє застарілі повідомлення.
    2. Спонтанно пише в групи через AI (не рандомний банк фраз!).
    3. Підхоплює незакінчені теми після 30+ хв тиші.
    """
    logger.info("Фоновий воркер спонтанних повідомлень та очищення пам'яті активовано")
    await asyncio.sleep(random.randint(60, 120))
    while True:
        try:
            deleted = cleanup_cyber_rizhyi_expired_messages(hours=72.0, keep_last=60)
            if deleted > 0:
                logger.info(f"Очищено {deleted} застарілих повідомлень з пам'яті")

            active_chats = get_active_cyber_rizhyi_chats()
            for chat_id in active_chats:
                try:
                    # СТРОГИЙ ЗАХИСТ: НЕ перебивати живий діалог у чаті! Тільки якщо глуха тиша 60+ хв!
                    if not is_cyber_chat_silent_for_minutes(chat_id, minutes=60.0):
                        continue

                    if random.random() < 0.75:
                        # AI-генерація спонтанного повідомлення (не рандомний банк!)
                        service = get_service_for_chat(chat_id)
                        ai_msgs = None
                        if hasattr(service, "generate_ai_spontaneous"):
                            ai_msgs = await asyncio.get_event_loop().run_in_executor(
                                None, service.generate_ai_spontaneous, chat_id
                            )
                        # Якщо AI не дав результат — fallback на generate_spontaneous_shout
                        if ai_msgs:
                            messages = ai_msgs
                            tagged = None
                        else:
                            messages, tagged = service.generate_spontaneous_shout(chat_id)

                        if messages:
                            messages = [clean_bot_reply(m) for m in messages if clean_bot_reply(m)]

                        if messages:
                            logger.info(f"AI спонтанне в чат {chat_id}: {messages}")
                            last_sent = None
                            for idx, rep in enumerate(messages):
                                if idx > 0:
                                    await asyncio.sleep(random.uniform(0.8, 1.6))
                                    try:
                                        await bot.send_chat_action(chat_id=chat_id, action="typing")
                                        await asyncio.sleep(random.uniform(0.6, 1.2))
                                    except Exception:
                                        pass
                                last_sent = await bot.send_message(chat_id=chat_id, text=rep)

                            full_shout = " ".join(messages)
                            save_cyber_rizhyi_message(
                                chat_id=chat_id, chat_type="supergroup",
                                user_id=bot.id, username="cyber_red_head_bot",
                                first_name="Саня Рижий", message_text="",
                                reply_text=full_shout, bot_persona="rizhyi"
                            )
                            if last_sent:
                                enqueue_cyber_bot_event(
                                    chat_id=chat_id, from_bot="rizhyi", to_bot="turikov",
                                    message_id=last_sent.message_id, text=full_shout,
                                    consecutive_count=0, sender_user_id=bot.id,
                                    sender_username="cyber_red_head_bot",
                                    sender_first_name="Саня Рижий", reply_to_name="Саня Туріков"
                                )
                except Exception as chat_err:
                    logger.debug(f"Пропущено чат {chat_id}: {chat_err}")

            await asyncio.sleep(random.randint(180, 420))
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Помилка у фоновому воркері: {e}")
            await asyncio.sleep(60)




async def inter_bot_bridge_worker(bot: Bot):
    """
    Міжботовий міст: дозволяє Сані Рижому чути та активно спілкуватися з Санею Туріковим у спільних групах.
    """
    logger.info("Міжботовий міст для Кібер Рижого активовано")
    while True:
        try:
            events = get_unprocessed_cyber_bot_events(for_bot="rizhyi", max_age_seconds=120)
            for ev in events:
                mark_cyber_bot_event_processed(ev["id"])
                chat_id = ev["chat_id"]
                if chat_id > 0:
                    continue

                from_bot = ev.get("from_bot")
                target_msg_id = ev.get("message_id")
                text = ev["text"]

                # А) Звернення людини до Рижого (relay з Турікова для обходу Group Privacy)
                if from_bot == "user_relay":
                    if target_msg_id and target_msg_id in _handled_group_msg_ids:
                        continue
                    if target_msg_id:
                        _handled_group_msg_ids.add(target_msg_id)
                        if len(_handled_group_msg_ids) > 500:
                            _handled_group_msg_ids.clear()

                    await asyncio.sleep(random.uniform(1.5, 3.0))
                    try:
                        await bot.send_chat_action(chat_id=chat_id, action="typing")
                        await asyncio.sleep(random.uniform(1.0, 2.0))
                    except Exception:
                        pass

                    sender_uid = ev.get("sender_user_id") or 1
                    sender_uname = ev.get("sender_username")
                    sender_name = ev.get("sender_first_name") or "Кент"

                    is_vitos = sender_uname == "zelenskiy404" or "вітя" in sender_name.lower() or "вітьок" in sender_name.lower() or "вітос" in sender_name.lower()
                    if is_vitos:
                        relay_instruction = (
                            "Це пише Вітьок (@zelenskiy404)! Твій бро Туріков уже осадив його, тепер ТИ включайся і добивай! "
                            "Називай його 'Вітьок' (не Вітос)! Заримуй на нього: 'вітьок з хуйом в тік токє огоньок'! "
                            "Підйобуй за згенеровану ШІ аватарку клоуна, скажи що він в край ахуєл пес, закрий йому ротяку! "
                            "Розбий на 2-3 короткі повідомлення через '|||'. Без '!' і СТРОГО без @ тегів!"
                        )
                    else:
                        relay_instruction = (
                            f"Твій бро Туріков щойно відповів {sender_name} у групі. Включись у розмову разом з ним, "
                            f"підтримай тему або заримуй смішну дражнилку на {sender_name} як справжній напарник! "
                            "Розбий на 2 короткі репліки через '|||'. Без '!' і без @ тегів!"
                        )

                    pkg = cyber_rizhyi_service.generate_reply_package(
                        chat_id=chat_id,
                        chat_type="supergroup",
                        user_id=sender_uid,
                        username=sender_uname,
                        first_name=sender_name,
                        message_text=text,
                        reply_to_user_id=sender_uid,
                        reply_to_name=sender_name,
                        custom_instruction=relay_instruction
                    )
                    replies = pkg.get("text_replies") or []
                    for idx, rep in enumerate(replies):
                        if idx == 0:
                            try:
                                await bot.send_message(
                                    chat_id=chat_id,
                                    text=rep,
                                    reply_to_message_id=target_msg_id
                                )
                            except Exception:
                                tagged_rep = rep if rep.startswith("@") else f"{sender_name}, {rep}"
                                await bot.send_message(chat_id=chat_id, text=tagged_rep)
                        else:
                            await asyncio.sleep(random.uniform(0.5, 1.0))
                            await bot.send_message(chat_id=chat_id, text=rep)

                    continue

                # Б) Діалог з Санею Туріковим (@turikov_bot)
                consecutive = ev.get("consecutive_count", 0)

                # Підтримуємо діалог між ботами до 10-12 реплік
                if consecutive >= 10:
                    logger.info(f"Міжботовий міст (Рижий): ліміт діалогу ({consecutive}), пауза до репліки людей")
                    continue

                text_low = text.lower()

                # Активний діалог: якщо Туріков звертається до Рижого або це активний ланцюжок
                is_mentioned = any(k in text_low for k in ["рижий", "рижа", "куріл", "рулет", "@cyber_red_head_bot", "кирило", "печення", "@la_coste228", "комп", "кс", "задрот"])
                if consecutive == 0 and not is_mentioned and random.random() > 0.65:
                    continue

                # Швидка та природна пауза (2.0-3.5 с думає, 1.0-1.8 с друкує)
                await asyncio.sleep(random.uniform(2.0, 3.5))
                try:
                    await bot.send_chat_action(chat_id=chat_id, action="typing")
                    await asyncio.sleep(random.uniform(1.0, 1.8))
                except Exception:
                    pass

                pkg = cyber_rizhyi_service.generate_reply_package(
                    chat_id=chat_id,
                    chat_type="supergroup",
                    user_id=TURIKOV_BOT_ID,
                    username="turikov_bot",
                    first_name="Саня Туріков",
                    message_text=text,
                    reply_to_user_id=TURIKOV_BOT_ID,
                    reply_to_name="Саня Туріков",
                    custom_instruction=(
                        "Це репліка твого кента Сані Турікова у спільній групі. "
                        "ОБОВ'ЯЗКОВО активно підтримуй і РОЗВИВАЙ розмову! Підколюй його за самокат, тайстру, "
                        "карти на площадці, його історійки чи дівчат, став йому зустрічні запитання, сперечайся, не відпускай розмову! "
                        "СТРОГО ЗАБОРОНЕНО короткі односкладові відповіді ('ок', 'пр', 'да', 'пон', 'і шо', 'хз', 'а ок'). "
                        "Пиши 1-2 живих пацанських речення у своєму стилі."
                    )
                )

                replies = pkg.get("text_replies") or []
                sent_msg = None
                for idx, rep in enumerate(replies):
                    if idx == 0:
                        try:
                            sent_msg = await bot.send_message(
                                chat_id=chat_id,
                                text=rep,
                                reply_to_message_id=ev.get("message_id")
                            )
                        except Exception as reply_err:
                            logger.warning(f"Не вдалося відповісти реплаєм ({reply_err}), надсилаємо без тегу")
                            sent_msg = await bot.send_message(chat_id=chat_id, text=rep)
                    else:
                        await asyncio.sleep(random.uniform(0.7, 1.3))
                        sent_msg = await bot.send_message(chat_id=chat_id, text=rep)

                if sent_msg and replies and consecutive < 10:
                    full_text = " ".join(replies)
                    enqueue_cyber_bot_event(
                        chat_id=chat_id,
                        from_bot="rizhyi",
                        to_bot="turikov",
                        message_id=sent_msg.message_id,
                        text=full_text,
                        consecutive_count=consecutive + 1,
                        sender_user_id=bot.id,
                        sender_username="cyber_red_head_bot",
                        sender_first_name="Саня Рижий",
                        reply_to_name="Саня Туріков"
                    )
            await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Помилка міжботового мосту Рижого: {e}")
            await asyncio.sleep(3.0)


async def main():
    init_db()

    token = CYBER_RIZHYI_BOT_TOKEN or TELEGRAM_BOT_TOKEN
    if not token or token.startswith("987654321:") or token.startswith("123456789:"):
        logger.error(
            "❌ Не налаштовано валідний токен для Кібер Рижого!\n"
            "Будь ласка, вкажіть CYBER_RIZHYI_BOT_TOKEN у файлі .env (отриманий від @BotFather)."
        )
        return

    bot = Bot(token=token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    bot_info = await bot.get_me()
    logger.info(f"🚀 Бот «Кібер Рижий» (@{bot_info.username}) успішно запущено!")
    logger.info(f"⚡ Модель: {cyber_rizhyi_service.model} | Пам'ять: активна | Відповідати на всі: {CYBER_RIZHYI_RESPOND_ALL_GROUP_MSGS}")

    await bot.delete_webhook(drop_pending_updates=True)
    worker_task = asyncio.create_task(spontaneous_rizhyi_worker(bot))
    bridge_task = asyncio.create_task(inter_bot_bridge_worker(bot))
    try:
        await dp.start_polling(bot)
    finally:
        worker_task.cancel()
        bridge_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот «Кібер Рижий» зупинено.")

