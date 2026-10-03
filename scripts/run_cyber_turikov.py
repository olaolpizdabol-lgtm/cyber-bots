"""
🤖 Автономний запуск бота "Кібер Саня Туріков" (Cyber Turikov Standalone Runner)

Цей скрипт запускає Telegram-бота «Кібер Саня Туріков»:
1. Читає CYBER_TURIKOV_BOT_TOKEN або CYBER_RIZHYI_BOT_TOKEN з .env
2. Відповідає на повідомлення в групах та приватних чатах у стилі Сані Турікова (Чернівці, пупсик, тайстра, карти)
3. Зберігає та відповідає на стікери, GIF та кружечки
4. Має пам'ять у SQLite та фоновий воркер спонтанних вкидів
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
    CYBER_TURIKOV_BOT_TOKEN,
    CYBER_RIZHYI_BOT_TOKEN,
    CYBER_RIZHYI_RESPOND_ALL_GROUP_MSGS,
    DOWNLOADS_DIR
)
from services.cyber_turikov import cyber_turikov_service
from services.cyber_rizhyi import clean_bot_reply
from services.tiktok_reactions import tiktok_reactions_service
from services.cyber_avatars import get_user_avatar_description, get_chat_avatars_summary, preload_known_avatars
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
    enqueue_cyber_bot_event,
    get_unprocessed_cyber_bot_events,
    mark_cyber_bot_event_processed,
    save_cyber_user_fact,
    get_cyber_all_user_facts_for_prompt,
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
    format="%(asctime)s [%(levelname)s] cyber_turikov: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("cyber_turikov")

router = Router()
_handled_group_msg_ids: set[int] = set()



# Емодзі-реакції Турікова (спокійний стиль)
TURIKOV_REACTIONS = ["👍", "😂", "💀", "😐", "🤙", "👎", "🔥", "😱"]

async def try_set_reaction_turikov(bot: Bot, chat_id: int, message_id: int) -> bool:
    """Ставить emoji-реакцію на повідомлення від Турікова."""
    try:
        emoji = random.choice(TURIKOV_REACTIONS)
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)]
        )
        return True
    except Exception:
        return False


async def _extract_facts_bg_turikov(service, chat_id: int, user_id: int, username: str, first_name: str, text: str):
    """Фоновий витяг фактів через LLM після відповіді Турікова"""
    try:
        sender_name = first_name or username or "Кент"
        if hasattr(service, 'extract_facts_with_llm'):
            await asyncio.get_event_loop().run_in_executor(
                None, service.extract_facts_with_llm,
                chat_id, sender_name, username or "", user_id, text
            )
    except Exception:
        pass



@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "здаров я саня туріков 🤙\n"
        "шо ти пупсик, на площадці в карти пограємо?"
    )


@router.message(F.new_chat_members)
async def handle_new_members(message: Message, bot: Bot):
    bot_info = await bot.get_me()
    for member in (message.new_chat_members or []):
        if member.id == bot_info.id:
            await message.reply("здаров пацани 🤙 я тута, хто буде гуляти")
            return


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📌 <b>Команди Сані Турікова:</b>\n\n"
        "• <code>/start</code> - привітання\n"
        "• <code>/memory</code> - що Туріков пам'ятає\n"
        "• <code>/spontaneous</code> - спонтанний вигук\n"
        "• Кидай будь-який <b>стікер</b> або <b>GIF</b> - Туріков оцінить або кине у відповідь\n"
        "• Кидай <b>посилання на TikTok</b> - отримай реакцію",
        parse_mode="HTML"
    )


@router.message(Command("memory"))
async def cmd_memory(message: Message):
    mem = get_cyber_rizhyi_user_memory(message.from_user.id)
    name = message.from_user.first_name or message.from_user.username or "Бро"
    if not mem:
        await message.reply(f"Ше мало спілкувались, {name}, я по ходу діла запомню.")
        return

    text = f"🧠 <b>Шо я знаю про тебе ({html.escape(name)}):</b>\n\n"
    for k, v in mem.items():
        k_clean = k.replace("_", " ").capitalize()
        text += f"• <b>{html.escape(k_clean)}:</b> {html.escape(str(v))}\n"
    await message.reply(text, parse_mode="HTML")


async def send_burst_replies(message: Message, bot: Bot, replies: list[str]) -> list[Message]:
    """Надсилає серію з 1-3 повідомлень з натуральними затримками друку та захистом від дублікатів на 30 хв"""
    from services.cyber_routing import is_recent_duplicate, record_sent_message
    sent = []
    if not replies:
        return sent

    # Фільтруємо повідомлення, які вже надсилалися у цей чат за останні 30 хвилин
    filtered = [r for r in replies if not is_recent_duplicate(message.chat.id, r)]
    if not filtered and replies:
        filtered = [replies[0]]

    for idx, rep in enumerate(filtered):
        if idx == 0:
            m = await message.reply(rep)
            sent.append(m)
            record_sent_message(message.chat.id, rep)
        else:
            await asyncio.sleep(random.uniform(1.2, 2.5))
            try:
                await bot.send_chat_action(chat_id=message.chat.id, action="typing")
                await asyncio.sleep(random.uniform(0.8, 1.6))
            except Exception:
                pass
            m = await message.answer(rep)
            sent.append(m)
            record_sent_message(message.chat.id, rep)
    return sent


async def send_reply_package(message: Message, bot: Bot, pkg: dict):
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


@router.message(Command("spontaneous", "shout", "tag"))
async def cmd_spontaneous(message: Message, bot: Bot):
    messages, tagged = cyber_turikov_service.generate_spontaneous_shout(message.chat.id)
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

        if not is_message_addressed_to_bot(message, "turikov"):
            return

        pkg = cyber_turikov_service.generate_reply_package(
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
    try:
        anim = message.animation
        save_cyber_media(
            chat_id=message.chat.id,
            media_type="animation",
            file_id=anim.file_id,
            file_unique_id=anim.file_unique_id
        )

        if not is_message_addressed_to_bot(message, "turikov"):
            return

        pkg = cyber_turikov_service.generate_reply_package(
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
            await message.reply("в мене тел лагає від таких здорових відосів")
            return

        file_info = await bot.get_file(video_obj.file_id)
        local_path = DOWNLOADS_DIR / f"turikov_vid_{message.from_user.id}_{message.message_id}.mp4"
        await bot.download_file(file_info.file_path, destination=local_path)

        if not is_message_addressed_to_bot(message, "turikov"):
            return

        pkg = cyber_turikov_service.generate_reply_package(
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
        logger.error(f"Помилка відео: {e}")


@router.message(F.photo | (F.document & F.document.mime_type.startswith("image/")))
async def handle_photo(message: Message, bot: Bot):
    try:
        photo_obj = message.photo[-1] if message.photo else message.document
        file_info = await bot.get_file(photo_obj.file_id)
        file_ext = Path(file_info.file_path).suffix or ".jpg"
        local_path = DOWNLOADS_DIR / f"turikov_{message.from_user.id}_{message.message_id}{file_ext}"
        await bot.download_file(file_info.file_path, destination=local_path)

        if not is_message_addressed_to_bot(message, "turikov"):
            return

        pkg = cyber_turikov_service.generate_reply_package(
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


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message, bot: Bot):
    text = message.text.strip()
    is_group = message.chat.type in ("group", "supergroup")

    if tiktok_reactions_service.is_tiktok_url(text):
        url = tiktok_reactions_service.extract_tiktok_url(text)
        try:
            res = tiktok_reactions_service.process_tiktok_link(url)
            await message.reply(
                f"🎬 <b>Реакція Турікова:</b>\n{html.escape(res['reaction'])}",
                parse_mode="HTML"
            )
            return
        except Exception as e:
            logger.error(f"Помилка тікток: {e}")

    # Розумне розпізнавання: кому адресоване повідомлення
    target_name, target_id = get_message_target(message)
    reply_to_text = (message.reply_to_message.text or message.reply_to_message.caption) if message.reply_to_message else None

    if not is_message_addressed_to_bot(message, "turikov"):
        save_cyber_rizhyi_message(
            chat_id=message.chat.id,
            chat_type=message.chat.type,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            message_text=text,
            reply_text=None,
            bot_persona="turikov",
            reply_to_user_id=target_id,
            reply_to_name=target_name,
            reply_to_msg_text=reply_to_text
        )
        return

    _handled_group_msg_ids.add(message.message_id)
    if is_group:
        await asyncio.sleep(random.uniform(1.2, 2.8))
        try:
            await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        except Exception:
            pass

    sender_uname = (message.from_user.username or "").lower() if message.from_user else ""
    sender_fname = (message.from_user.first_name or "").lower() if message.from_user else ""
    is_vitos = (
        sender_uname == "zelenskiy404"
        or any(k in sender_fname for k in ["вітя", "вітьок", "зеленський"])
        or target_name == "Вітьок"
        or "@zelenskiy404" in text.lower()
    )

    custom_instr = None
    if is_vitos:
        custom_instr = (
            "Це пише Вітьок (@zelenskiy404) з чужою зеленою ламбою на аві, якого кинула дівчина! "
            "Жорстко над ним угарай: 'Блять ти додік якого кинула дівчина ставиш ламбу на аву, з тебе даже в 11 школі угарають. Реальні бабки на ламбу є в Давіда (@davvidka1), він піднявся на фейсбуку'! "
            "Тегни @zelenskiy404 і @davvidka1. 1 коротка фраза."
        )
    elif is_group and random.random() < 0.18:
        custom_instr = (
            "Підтримай тему по-пацанськи. Якщо доречно, підколи або тегни когось із кентів: "
            "@zelenskiy404 (що він додік з чужою ламбою на аві і його кинула дівчина, вся 11 школа угарає), "
            "@davvidka1 (що в нього реальні бабки з фб), @twdht (Діма), @bodya_qq (Бодя). 1 коротка фраза."
        )

    # Фонове (але не блокуюче) отримання аватарки відправника через Gemini Vision (кеш 15 хв)
    sender_avatar_desc = None
    all_avatars_ctx = None
    try:
        sender_avatar_desc = await get_user_avatar_description(
            bot, message.from_user.id,
            username=message.from_user.username,
            display_name=message.from_user.first_name
        )
        all_avatars_ctx = get_chat_avatars_summary(exclude_user_id=message.from_user.id)
    except Exception as _av_err:
        logger.debug(f"Аватарка недоступна: {_av_err}")

    pkg = cyber_turikov_service.generate_reply_package(
        chat_id=message.chat.id,
        chat_type=message.chat.type,
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        message_text=text,
        has_photo=False,
        custom_instruction=custom_instr,
        reply_to_user_id=target_id,
        reply_to_name=target_name,
        reply_to_text=reply_to_text,
        sender_avatar_desc=sender_avatar_desc,
        all_avatars_context=all_avatars_ctx
    )
    if is_vitos:
        replies = pkg.get("text_replies") or []
        if not any("ламб" in r.lower() or "тьолк" in r.lower() or "11" in r.lower() for r in replies):
            pkg["text_replies"] = [
                "Блять ти додік якого кинула дівчина ставиш ламбу на аву, з тебе даже в 11 школі угарають. Реальні бабки на ламбу є в Давіда (@davvidka1), він піднявся на фейсбуку",
                "@zelenskiy404 рот завали клоун"
            ]
    elif is_group and random.random() < 0.18:
        tag_prompts = [
            "@zelenskiy404 ти нахуя чужу ламбу на аву вліпив додік, тебе тьолка кинула і вся 11 школа з тебе рже",
            "@davvidka1 скажи цьому клоуну @zelenskiy404 чия то ламба, в тебе реальні бабки з фб є а він лох"
        ]
        replies = pkg.get("text_replies") or []
        if replies and random.random() < 0.25:
            pkg["text_replies"].append(random.choice(tag_prompts))

    await send_reply_package(message, bot, pkg)



    # 40% шанс поставити реакцію разом із текстом
    if random.random() < 0.40:
        await asyncio.sleep(random.uniform(0.3, 1.0))
        await try_set_reaction_turikov(bot, message.chat.id, message.message_id)

    asyncio.ensure_future(_extract_facts_bg_turikov(
        cyber_turikov_service, message.chat.id, message.from_user.id,
        message.from_user.username, message.from_user.first_name, text
    ))


async def spontaneous_turikov_worker(bot: Bot):
    logger.info("Фоновий воркер Сані Турікова активовано")
    # Пауза перед першим вигуком після запуску (1-2.5 хвилини)
    await asyncio.sleep(random.randint(60, 150))
    while True:
        try:
            cleanup_cyber_rizhyi_expired_messages(hours=72.0, keep_last=60)
            active_chats = get_active_cyber_rizhyi_chats()
            for chat_id in active_chats:
                try:
                    # СТРОГИЙ ЗАХИСТ: НЕ перебивати живий діалог у чаті! Тільки якщо глуха тиша 60+ хв!
                    if not is_cyber_chat_silent_for_minutes(chat_id, minutes=60.0):
                        continue

                    if random.random() < 0.70:
                        ai_msgs = await asyncio.get_event_loop().run_in_executor(
                            None, cyber_turikov_service.generate_ai_spontaneous, chat_id
                        )
                        if ai_msgs:
                            messages = ai_msgs
                            tagged = None
                        else:
                            messages, tagged = cyber_turikov_service.generate_spontaneous_shout(chat_id)

                        if messages:
                            messages = [clean_bot_reply(m) for m in messages if clean_bot_reply(m)]

                        if messages:
                            logger.info(f"Туріков спонтанно пише в {chat_id}: {messages}")
                            last_sent = None
                            for idx, rep in enumerate(messages):
                                if idx > 0:
                                    await asyncio.sleep(random.uniform(0.6, 1.2))
                                    try:
                                        await bot.send_chat_action(chat_id=chat_id, action="typing")
                                        await asyncio.sleep(random.uniform(0.4, 0.9))
                                    except Exception:
                                        pass
                                last_sent = await bot.send_message(chat_id=chat_id, text=rep)

                            full_shout = " ".join(messages)
                            save_cyber_rizhyi_message(
                                chat_id=chat_id,
                                chat_type="supergroup",
                                user_id=bot.id,
                                username="turikov_bot",
                                first_name="Саня Туріков",
                                message_text="",
                                reply_text=full_shout,
                                bot_persona="turikov"
                            )
                            # Ставимо подію для Рижого, щоб він міг підхопити розмову в чаті
                            if last_sent:
                                enqueue_cyber_bot_event(
                                    chat_id=chat_id,
                                    from_bot="turikov",
                                    to_bot="rizhyi",
                                    message_id=last_sent.message_id,
                                    text=full_shout,
                                    consecutive_count=0,
                                    sender_user_id=bot.id,
                                    sender_username="turikov_bot",
                                    sender_first_name="Саня Туріков",
                                    reply_to_name="Саня Рижий"
                                )
                except Exception as chat_err:
                    logger.debug(f"Пропущено чат {chat_id}: {chat_err}")

            # Пауза між вкидами (3-7 хвилин)
            await asyncio.sleep(random.randint(180, 420))
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Помилка у фоновому воркері Турікова: {e}")
            await asyncio.sleep(60)


async def inter_bot_bridge_worker(bot: Bot):
    """
    Міжботовий міст:
    1. Дозволяє Сані Турікову чути та реагувати на репліки Сані Рижого у спільних групах.
    2. Дозволяє Турікову гарантовано отримувати та відповідати на звернення учасників групи,
       навіть якщо увімкнено Group Privacy mode в Telegram (через relay від Рижого).
    """
    logger.info("Міжботовий міст для Сані Турікова активовано")
    while True:
        try:
            events = get_unprocessed_cyber_bot_events(for_bot="turikov", max_age_seconds=120)
            for ev in events:
                mark_cyber_bot_event_processed(ev["id"])
                chat_id = ev["chat_id"]
                if chat_id > 0:
                    continue

                from_bot = ev.get("from_bot")
                target_msg_id = ev.get("message_id")
                text = ev["text"]

                # А) Звернення людини до Турікова (relay з Рижого для обходу Group Privacy)
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

                    is_vitos = sender_uname == "zelenskiy404" or "вітя" in sender_name.lower() or "вітьок" in sender_name.lower() or "вітос" in sender_name.lower() or "@zelenskiy404" in text.lower()
                    if is_vitos:
                        relay_instruction = (
                            "Це пише Вітьок (@zelenskiy404)! Твій бро Рижий уже осадив його, тепер ТИ включайся і добивай! "
                            "Називай його 'Вітьок'! Скажи: 'Блять ти додік якого кинула дівчина ставиш ламбу на аву, з тебе даже в 11 школі угарають. Реальні бабки на ламбу є в Давіда (@davvidka1), він піднявся на фейсбуку'! "
                            "Тегни @zelenskiy404 і @davvidka1. Пиши 1 коротке живе повідомлення."
                        )
                    else:
                        if random.random() < 0.20:
                            relay_instruction = (
                                f"Твій бро Рижий щойно відповів {sender_name} у групі. Підтримай тему по-пацанськи. "
                                "Можеш контекстно підколоти чи тегнути @zelenskiy404 (що він додік з чужою ламбою на аві і його кинула дівчина, вся 11 школа угарає) чи тегнути @davvidka1 або @twdht. "
                                "Пиши 1 коротке живе повідомлення."
                            )
                        else:
                            relay_instruction = (
                                f"Твій бро Рижий щойно відповів {sender_name} у групі. Включись у розмову разом з ним, "
                                f"спокійно й дружньо підтримай тему по-пацанськи! "
                                "Пиши 1 коротке живе повідомлення."
                            )

                    pkg = cyber_turikov_service.generate_reply_package(
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
                    if is_vitos and not any("ламб" in r.lower() or "тьолк" in r.lower() or "11" in r.lower() for r in replies):
                        replies = [
                            "Блять ти додік якого кинула дівчина ставиш ламбу на аву, з тебе даже в 11 школі угарають. Реальні бабки на ламбу є в Давіда (@davvidka1), він піднявся на фейсбуку",
                            "@zelenskiy404 рот завали клоун"
                        ]

                    for idx, rep in enumerate(replies):
                        if idx == 0:
                            try:
                                await bot.send_message(
                                    chat_id=chat_id,
                                    text=rep,
                                    reply_to_message_id=target_msg_id
                                )
                                record_sent_message(chat_id, rep)
                            except Exception:
                                tagged_rep = rep if rep.startswith("@") else f"{sender_name}, {rep}"
                                await bot.send_message(chat_id=chat_id, text=tagged_rep)
                                record_sent_message(chat_id, tagged_rep)
                        else:
                            await asyncio.sleep(random.uniform(0.5, 1.0))
                            await bot.send_message(chat_id=chat_id, text=rep)
                            record_sent_message(chat_id, rep)

                    # Діалог між людиною і Туріковим НЕ повинен автоматично тригерити Рижого
                    continue

                # Б) Діалог з Санею Рижим (@cyber_red_head_bot)
                consecutive = ev.get("consecutive_count", 0)

                # Підтримуємо діалог між ботами НЕ більше 1 обміну (щоб не було спаму між ботами!)
                if consecutive >= 1:
                    logger.info(f"Міжботовий міст (Туріков): ліміт діалогу ({consecutive}), зупиняємо ланцюжок")
                    continue

                text_low = text.lower()

                # Відповідаємо Рижому, якщо він звертається до Турікова
                is_mentioned = any(k in text_low for k in ["туріков", "турік", "пупсик", "@turikov_bot", "саня", "саша", "газ", "роналду", "карти", "шошо", "тайстра", "самокат", "богдан банан"])
                if consecutive == 0 and not is_mentioned and random.random() > 0.40:
                    continue

                # Швидка та природна пауза (2.0-3.5 с читає, 1.0-1.8 с друкує)
                await asyncio.sleep(random.uniform(2.5, 4.0))
                try:
                    await bot.send_chat_action(chat_id=chat_id, action="typing")
                    await asyncio.sleep(random.uniform(1.0, 1.8))
                except Exception:
                    pass

                pkg = cyber_turikov_service.generate_reply_package(
                    chat_id=chat_id,
                    chat_type="supergroup",
                    user_id=RIZHYI_BOT_ID,
                    username="cyber_red_head_bot",
                    first_name="Саня Рижий",
                    message_text=text,
                    reply_to_user_id=RIZHYI_BOT_ID,
                    reply_to_name="Саня Рижий",
                    custom_instruction=(
                        "Це репліка твого кента Сані Рижого у спільній групі. "
                        "Підтримай або підколи його коротко (за CS2, куріла рулета, комп). "
                        "Пиши ПЕРЕВАЖНО ОДНУ коротку живу фразу! Без '!'. Без уроків і школи."
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
                                reply_to_message_id=target_msg_id
                            )
                        except Exception as reply_err:
                            logger.warning(f"Не вдалося відповісти реплаєм ({reply_err}), надсилаємо без тегу")
                            sent_msg = await bot.send_message(chat_id=chat_id, text=rep)
                    else:
                        await asyncio.sleep(random.uniform(0.5, 1.0))
                        sent_msg = await bot.send_message(chat_id=chat_id, text=rep)
                # Боти НЕ продовжують розмову між собою далі (чекають повідомлень від людей)
            await asyncio.sleep(0.8)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Помилка міжботового мосту Турікова: {e}")
            await asyncio.sleep(3.0)


async def main():
    init_db()
    token = CYBER_TURIKOV_BOT_TOKEN
    if not token:
        logger.error("❌ Не налаштовано токен бота для Турікова (CYBER_TURIKOV_BOT_TOKEN) у .env!")
        logger.error("👉 Створіть окремого бота у @BotFather (наприклад, @CyberTurikovBot) та додайте токен у .env: CYBER_TURIKOV_BOT_TOKEN=...")
        return

    bot = Bot(token=token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    bot_info = await bot.get_me()
    logger.info(f"🚀 Бот «Кібер Саня Туріков» (@{bot_info.username}) успішно запущено!")

    await bot.delete_webhook(drop_pending_updates=True)
    # Передзавантаження аватарок відомих учасників чату при старті (фон, не блокує)
    asyncio.ensure_future(preload_known_avatars(bot))
    worker_task = asyncio.create_task(spontaneous_turikov_worker(bot))
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
        logger.info("Бот «Кібер Саня Туріков» зупинено.")
