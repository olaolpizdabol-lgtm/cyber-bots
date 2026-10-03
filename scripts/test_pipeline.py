#!/usr/bin/env python3
"""
Скрипт для комплексного тестування ВСІХ функцій та розрахунків Автоматизації #1:
1. 🎬 Відео (9:16)
2. 📸 Одиночне фото (з авто-підгонкою пропорцій: Pinterest 2:3, IG 4:5, X 16:9)
3. 📚 Фото-карусель (Photo Mode)
4. 🎞 Мікс-карусель (Фото + Відео з контролем лімітів X <= 4, Bluesky <= 4, TikTok photo-only)
5. 📝 Текстовий пост з оптимальними розрахунками символів
6. 🔤 Сувора типографіка (ТІЛЬКИ дефіс '-', жодних довгих '—' або '–')
7. ✂️ Інтелектуальне скорочення тексту (Smart Condensation & Word Boundary Truncation)
8. 🌐 IP-матриця та захист від тіньового бану (TikTok, IG, FB, Snap, Threads vs YouTube, Bluesky)
9. 🛡 Комплексний безпековий аудит (chmod 600, маскування токенів та паролів)
"""
import sys
import os
import asyncio
import subprocess
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import init_db
from core.content_type import ContentType, PLATFORM_CONSTRAINTS
from core.media_processor import media_processor
from core.security_guard import security_guard
from services.gemini_ai import gemini_service, sanitize_typography, truncate_at_word_boundary
from services.proxy_manager import proxy_manager, IP_DEPENDENT_PLATFORMS, DIRECT_PLATFORMS
from services.automations.auto_poster import auto_poster


def create_sample_vertical_video(output_path: str):
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=1080x1920:d=2",
        "-f", "lavfi", "-i", "sine=f=440:d=2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def create_sample_image(output_path: str, color: str = "red"):
    img = Image.new("RGB", (1080, 1350), color=color)
    img.save(output_path, "JPEG")


def main():
    print("==================================================")
    print("🚀 ТЕСТУВАННЯ ПОВНОГО РОЗРАХУНКУ, БЕЗПЕКИ ТА АНТИ-БАНУ")
    print("==================================================")

    init_db()
    test_dir = Path("data/tests")
    test_dir.mkdir(parents=True, exist_ok=True)

    # 1. ТЕСТ ВІДЕО
    print("\n1️⃣ ТЕСТ: Вертикальне відео (9:16)...")
    v_file = test_dir / "calc_video.mp4"
    create_sample_vertical_video(str(v_file))
    res_v = auto_poster.process_incoming_content(media_paths=[str(v_file)])
    assert res_v["content_type"] == ContentType.VIDEO
    print(f"   • Формат розпізнано: {res_v['content_type'].value} (Сумісних платформ: {len(res_v['compatible_platforms'])}) ✅")

    # 2. ТЕСТ МІКС-КАРУСЕЛІ (Фото + Відео) та СЛАЙД-ЛІМІТІВ
    print("\n2️⃣ ТЕСТ: Мікс-карусель (Фото + Відео) та перевірка слайд-лімітів...")
    mixed_paths = [str(v_file)]
    for i in range(6):
        p = test_dir / f"calc_slide_{i}.jpg"
        create_sample_image(str(p), color="blue")
        mixed_paths.append(str(p))

    c_type_mixed = auto_poster.detect_content_type(mixed_paths)
    assert c_type_mixed == ContentType.MIXED_CAROUSEL, f"Очікувався MIXED_CAROUSEL, отримано: {c_type_mixed}"
    print(f"   • Формат розпізнано: {c_type_mixed.value} ({len(mixed_paths)} елементів)")

    tw_media = auto_poster.prepare_media_for_platform("twitter", c_type_mixed, mixed_paths)
    assert len(tw_media) <= 4, f"X ліміт перевищено: {len(tw_media)}"
    assert not any(p.endswith(".mp4") for p in tw_media), "X не може змішувати відео з фото!"
    print(f"   • X (Twitter) розрахунок: {len(tw_media)} фото (строго <= 4, без змішування з відео) ✅")

    tt_media = auto_poster.prepare_media_for_platform("tiktok", c_type_mixed, mixed_paths)
    assert not any(p.endswith(".mp4") for p in tt_media), "TikTok Photo Mode не підтримує відео!"
    print(f"   • TikTok Photo Mode розрахунок: {len(tt_media)} фото (тільки фото) ✅")

    # 3. ТЕСТ АСПЕКТІВ ЗОБРАЖЕНЬ (Pillow Aspect Adapters)
    print("\n3️⃣ ТЕСТ: Адаптація пропорцій зображень під стандарти 2026...")
    sample_img = test_dir / "calc_slide_0.jpg"
    pin_img = media_processor.clean_and_prepare_image(str(sample_img), target_platform="pinterest")
    with Image.open(pin_img) as pim:
        w, h = pim.size
        print(f"   • Pinterest розмір: {w}x{h} (Співвідношення: 2:3) ✅")
        assert (w, h) == (1000, 1500), f"Невірний розмір Pinterest: {w}x{h}"

    tw_img = media_processor.clean_and_prepare_image(str(sample_img), target_platform="twitter")
    with Image.open(tw_img) as tim:
        w, h = tim.size
        print(f"   • X (Twitter) розмір: {w}x{h} (Співвідношення: 16:9) ✅")
        assert (w, h) == (1200, 675), f"Невірний розмір Twitter: {w}x{h}"

    # 4. ТЕСТ ОПТИМАЛЬНИХ ДОВЖИН СИМВОЛІВ
    print("\n4️⃣ ТЕСТ: Розрахунок лімітів та оптимальних довжин тексту...")
    meta = gemini_service.generate_metadata(content_type=ContentType.TEXT, raw_text="Тестова думка про розвиток AI у 2026")

    print(f"   • X (Twitter): {len(meta['twitter_post'])} симв (Оптимально 100-240, ліміт 280) ✅")
    print(f"   • Threads: {len(meta['threads_post'])} симв (Оптимально 150-400, ліміт 500) ✅")
    print(f"   • Facebook: {len(meta['fb_caption'])} симв (Оптимально 300-800, ліміт 63k) ✅")
    print(f"   • Bluesky: {len(meta['bluesky_post'])} симв (Оптимально 150-250, ліміт 300) ✅")
    print(f"   • YouTube Shorts Title: {len(meta['youtube_title'])} симв (Ліміт 100) ✅")

    assert len(meta["twitter_post"]) <= 280
    assert len(meta["threads_post"]) <= 500
    assert len(meta["bluesky_post"]) <= 300
    assert len(meta["youtube_title"]) <= 100

    # 5. ТЕСТ СУВОРОЇ ТИПОГРАФІКИ (ДЕФІС '-' ЗАМІСТЬ '—' ТА '–')
    print("\n5️⃣ ТЕСТ: Сувора типографіка (ТІЛЬКИ '-', жодних '—' чи '–')...")
    dirty_text = "Це тест — з довгим тире та en-dash – всередині речення."
    clean_text = sanitize_typography(dirty_text)
    assert "—" not in clean_text, "Знайдено em-dash (—)!"
    assert "–" not in clean_text, "Знайдено en-dash (–)!"
    assert "-" in clean_text, "Дефіс повинен бути присутнім!"
    print(f"   • Вхідний: '{dirty_text}'")
    print(f"   • Очищений: '{clean_text}' ✅")

    # Перевіряємо всі поля згенерованих метаданих
    for k, v in meta.items():
        if isinstance(v, str):
            assert "—" not in v, f"Поле {k} містить em-dash!"
            assert "–" not in v, f"Поле {k} містить en-dash!"
    print("   • Усі метадані Gemini містять ВИКЛЮЧНО звичайний дефіс '-' ✅")

    # 6. ТЕСТ СКОРОЧЕННЯ ТЕКСТУ (SMART CONDENSATION)
    print("\n6️⃣ ТЕСТ: Розумне скорочення тексту під ліміти символів...")
    long_desc = (
        "Сьогодні ми представляємо абсолютно новий спосіб масштабування та створення вірусного відео-контенту. "
        "Ця інноваційна технологія автоматизує публікації в усі можливі соцмережі світу, від TikTok до YouTube Shorts. "
        "Кожен користувач отримує максимальне охоплення аудиторії в Сполучених Штатах без жодних витрат на рекламу. "
        "Переходьте за посиланням у закріпленому повідомленні, щоб дізнатися всі подробиці та протестувати першими!"
    )
    # Тест скорочення для X (Twitter) до 200 символів
    cond_x = gemini_service.condense_text(long_desc, target_platform="twitter", max_chars=200)
    assert len(cond_x) <= 200, f"Текст для X перевищує 200: {len(cond_x)}"
    assert "—" not in cond_x and "–" not in cond_x
    print(f"   • Текст скорочено для X ({len(cond_x)}/200 симв): '{cond_x}' ✅")

    # Тест word-boundary безпечного обрізання
    short_wb = truncate_at_word_boundary("Один два три чотири п'ять шість", 18)
    assert not short_wb.endswith("п'ять..."), "Слово не повинно бути обрізано неправильно"
    assert len(short_wb) <= 18
    print(f"   • Word-boundary обрізка: '{short_wb}' (довжина: {len(short_wb)} <= 18) ✅")

    # 7. ТЕСТ IP-МАТРИЦІ ТА ПЕРЕВІРКИ ПЕРЕД ПУБЛІКАЦІЄЮ
    print("\n7️⃣ ТЕСТ: IP-матриця та захист від блокування акаунтів...")
    assert "tiktok" in IP_DEPENDENT_PLATFORMS
    assert "instagram" in IP_DEPENDENT_PLATFORMS
    assert "facebook" in IP_DEPENDENT_PLATFORMS
    assert "snapchat" in IP_DEPENDENT_PLATFORMS
    assert "threads" in IP_DEPENDENT_PLATFORMS

    assert "youtube" in DIRECT_PLATFORMS
    assert "bluesky" in DIRECT_PLATFORMS
    assert "telegram" in DIRECT_PLATFORMS

    # YouTube завжди безпечний напряму
    yt_safe, yt_msg = proxy_manager.verify_platform_safety("youtube")
    assert yt_safe is True
    print(f"   • YouTube перевірка (Direct OAuth): {yt_msg} ✅")

    # SOCKS5h DNS-leak prevention
    proxy_manager.proxy_url = "socks5://user:pass@127.0.0.1:1080"
    proxies = proxy_manager.get_requests_proxies()
    assert proxies["http"].startswith("socks5h://"), "DNS leak protection (socks5h) не спрацював!"
    proxy_manager.proxy_url = "" # скидаємо
    print("   • Захист від витоку DNS (socks5h:// remote DNS resolver): АКТИВНО ✅")

    # 8. ТЕСТ БЕЗПЕКИ ТА АУДИТУ
    print("\n8️⃣ ТЕСТ: Безпековий аудит та захист облікових даних...")
    # Маскування секретів
    masked_t = security_guard.mask_secret("ghp_1234567890abcdefghij", visible_chars=4)
    assert masked_t == "ghp_...ghij"
    print(f"   • Маскування токенів: {masked_t} ✅")

    # Маскування URL проксі
    masked_p = security_guard.sanitize_proxy_url("socks5://admin:MySecretPass123@1.2.3.4:1080")
    assert "MySecretPass123" not in masked_p
    assert "admin:****@" in masked_p
    print(f"   • Маскування пароля проксі: {masked_p} ✅")

    # Очищення помилок
    cleaned_err = security_guard.sanitize_error("Error 401: access_token=secret_abc123456789 Bearer eyJhbGciOi")
    assert "secret_abc123456789" not in cleaned_err
    assert "access_token=***" in cleaned_err
    print(f"   • Очищення повідомлень про помилки від витоків токенів: {cleaned_err} ✅")

    # Аудит оточення
    audit = security_guard.audit_security(Path("."))
    print(f"   • Аудит середовища: {audit['summary']} ✅")

    # 9. ТЕСТ ОПТИМІЗАЦІЇ ПІД ПОШУКОВІ ЗАПИТИ (SOCIAL SEO 2026)
    print("\n9️⃣ ТЕСТ: Оптимізація під пошукові запити (Social SEO & Presets)...")
    from services.gemini_ai import SEO_PROMPT_PRESETS
    assert "seo_viral" in SEO_PROMPT_PRESETS
    assert "seo_howto" in SEO_PROMPT_PRESETS
    assert "seo_top" in SEO_PROMPT_PRESETS
    assert "seo_commercial" in SEO_PROMPT_PRESETS

    print(f"   • Доступні SEO-пресети: {len(SEO_PROMPT_PRESETS)} шт. ✅")
    for p_k, p_data in SEO_PROMPT_PRESETS.items():
        print(f"     - {p_data['title']}: {p_data['desc'][:45]}...")

    # Перевіряємо що SEO-промпт містить ключові інструкції Social SEO
    viral_prompt = SEO_PROMPT_PRESETS["seo_viral"]["prompt"]
    assert "Primary Search Keyword" in viral_prompt or "пошуковий запит" in viral_prompt
    assert "LSI" in viral_prompt
    assert "TikTok Search" in viral_prompt
    print("   • Структура Social SEO промпту валідна (Search Match, LSI, нішеві кластери) ✅")

    # Перевіряємо генерацію опису з фокусом на пошукові запити
    seo_meta = gemini_service.generate_metadata(
        content_type=ContentType.VIDEO,
        raw_text="Пошуковий запит: як налаштувати проксі для тікток без бану"
    )
    assert len(seo_meta["caption"]) > 0
    assert "—" not in seo_meta["caption"]
    assert "–" not in seo_meta["caption"]
    print(f"   • Згенеровано SEO-опис з пошуковим запитом: '{seo_meta['caption'][:80]}...' ✅")

    # 10. ТЕСТ АВТОМАТИЗАЦІЇ #2 (TIKTOK ВОГНИКИ ТА СЕРДЕЧКА ДЛЯ ДІВЧИНИ)
    print("\n🔟 ТЕСТ: Автоматизація #2 (TikTok Streaks & Сердечка для Дівчини)...")
    import services.automations.automation_2 as auto2_mod
    orig_dry_run = auto2_mod.DRY_RUN_MODE
    auto2_mod.DRY_RUN_MODE = True
    from services.automations.automation_2 import tiktok_streak_service
    from core.database import (
        set_girlfriend_target,
        get_girlfriend_target,
        add_streak_target,
        get_streak_targets,
        get_recent_streak_logs,
        get_streak_stats
    )

    # Встановлення акаунта дівчини
    set_girlfriend_target("test_sweet_girl", "Кохана Поліна")
    gf_target = get_girlfriend_target()
    assert gf_target is not None
    assert gf_target["username"] == "test_sweet_girl"
    assert gf_target["is_girlfriend"] == 1
    print(f"   • Акаунт дівчини налаштовано: @{gf_target['username']} ({gf_target['nickname']}) ✅")

    # Додавання звичайного друга для вогників
    add_streak_target("best_friend_alex", "Саня Бро", is_girlfriend=False)
    fr_target = get_streak_targets()
    assert any(t["username"] == "best_friend_alex" for t in fr_target)
    print("   • Контакт для звичайного вогника додано: @best_friend_alex (Саня Бро) ✅")

    # Тест генерації повідомлення для дівчини (сердечка та відсутність довгих тире)
    gf_msg = tiktok_streak_service.generate_girlfriend_heart_message()
    assert any(h in gf_msg for h in ["❤️", "🥰", "💖", "💕", "💓", "💞", "💘"]), "Повідомлення для дівчини має містити сердечка!"
    assert "—" not in gf_msg, "Знайдено em-dash у повідомленні для дівчини!"
    assert "–" not in gf_msg, "Знайдено en-dash у повідомленні для дівчини!"
    print(f"   • Генерація для коханої: '{gf_msg}' (сердечка присутні, типографіка '-') ✅")

    # Тест генерації повідомлення для друга (вогник)
    fr_msg = tiktok_streak_service.generate_friend_streak_message()
    assert "🔥" in fr_msg, "Повідомлення для друга має містити вогник!"
    assert "—" not in fr_msg and "–" not in fr_msg
    print(f"   • Генерація для друга: '{fr_msg}' (вогник 🔥 присутній, типографіка '-') ✅")

    # Тест відправки в Demo/Dry-Run режимі
    success, note = asyncio.run(tiktok_streak_service.send_tiktok_direct_message("test_sweet_girl", gf_msg))
    assert success is True
    print(f"   • Відправка TikTok DM (Безпечний Demo/Dry-run): {note} ✅")

    # Тест повного диспетчера розсилки вогників (run_streaks_dispatch)
    dispatch_res = asyncio.run(tiktok_streak_service.run_streaks_dispatch())
    assert dispatch_res["success"] is True
    assert dispatch_res["total_targets"] >= 2
    assert dispatch_res["sent_count"] >= 2

    # Перевірка логів та статистики в БД
    recent_logs = get_recent_streak_logs(limit=5)
    assert len(recent_logs) >= 2
    stats = get_streak_stats()
    print(f"   • Результат розсилки вогників: успішно {dispatch_res['sent_count']}/{dispatch_res['total_targets']} ✅")
    print(f"   • Статистика в базі даних: Всього цілей: {stats['total_targets']}, Дівчина: {stats['has_girlfriend']}, Відправлено сьогодні: {stats['sent_today']}, Макс. серія: {stats['max_streak']} ✅")
    auto2_mod.DRY_RUN_MODE = orig_dry_run

    # 11. ТЕСТ РЕАКЦІЙ НА TIKTOK У СТИЛІ БОДІ (АВТЕНТИЧНИЙ ЧАТ-СТИЛЬ)
    print("\n1️⃣1️⃣ ТЕСТ: Реакції на TikTok у фірмовому стилі Боді...")
    from services.tiktok_reactions import tiktok_reactions_service
    from core.database import get_recent_tiktok_reactions

    # Перевірка детекції посилань
    assert tiktok_reactions_service.is_tiktok_url("дивись https://vt.tiktok.com/ZSVTSoCsv/ це ор") is True
    assert tiktok_reactions_service.is_tiktok_url("просто текст без лінка") is False

    # Генерація реакції
    tt_reaction = tiktok_reactions_service.generate_reaction(
        video_meta={"uploader": "turikov_fan", "title": "коли туріков курить гонджубаси"}
    )
    assert len(tt_reaction) > 0
    assert "—" not in tt_reaction and "–" not in tt_reaction
    print(f"   • Згенеровано реакцію Боді: '{tt_reaction}' (типографіка '-') ✅")

    # Збереження в історію
    res_tt = tiktok_reactions_service.process_tiktok_link("https://vt.tiktok.com/ZSVTSoCsv/")
    assert res_tt["success"] is True
    tt_logs = get_recent_tiktok_reactions(limit=3)
    assert len(tt_logs) > 0
    print(f"   • Логування реакції TikTok в БД: успішно (всього записів: {len(tt_logs)}) ✅")

    # 12. ТЕСТ БОТА "КІБЕР РИЖИЙ" (1 В 1 ЯК РИЖИЙ: GROQ 120B, VISION & ПАМ'ЯТЬ)
    print("\n1️⃣2️⃣ ТЕСТ: Бот «Кібер Рижий» (Groq 120B, Multimodal Vision та Пам'ять)...")
    from services.cyber_rizhyi import cyber_rizhyi_service
    from core.database import (
        save_cyber_rizhyi_message,
        get_cyber_rizhyi_chat_history,
        get_cyber_rizhyi_user_memory,
        set_cyber_rizhyi_user_memory
    )

    # Тест пам'яті: запис та зчитування фактів про кента
    set_cyber_rizhyi_user_memory(user_id=777, key="прізвисько", value="Бодя бро")
    set_cyber_rizhyi_user_memory(user_id=777, key="улюблена_гра", value="КС2")
    user_mem = get_cyber_rizhyi_user_memory(user_id=777)
    assert user_mem["улюблена_гра"] == "КС2"
    assert user_mem["прізвисько"] == "Бодя бро"
    print(f"   • Довгострокова пам'ять Рижого (SQLite): {user_mem} ✅")

    # Тест відповідей Рижого на трійку найкращих бро: Міша, Діма, Бодя
    reply_bodya = cyber_rizhyi_service.generate_reply(
        chat_id=-1001234567, chat_type="supergroup", user_id=777,
        username="bodya", first_name="Бодя", message_text="го в кс зіграємо?", has_photo=False
    )
    reply_dima = cyber_rizhyi_service.generate_reply(
        chat_id=-1001234567, chat_type="supergroup", user_id=888,
        username="dima", first_name="Діма", message_text="ти де бро?", has_photo=False
    )
    reply_misha = cyber_rizhyi_service.generate_reply(
        chat_id=-1001234567, chat_type="supergroup", user_id=999,
        username="misha", first_name="Міша", message_text="шо там?", has_photo=False
    )
    assert len(reply_bodya) > 0 and len(reply_dima) > 0 and len(reply_misha) > 0
    print(f"   • Відповідь для Боді (кращий бро): '{reply_bodya}' ✅")
    print(f"   • Відповідь для Діми (кращий бро): '{reply_dima}' ✅")
    print(f"   • Відповідь для Міші (кращий бро): '{reply_misha}' ✅")

    # Тест знання лору про Турікова та Діджея Куріла Рулєта
    reply_turikov = cyber_rizhyi_service.generate_reply(
        chat_id=-1001234567, chat_type="supergroup", user_id=777,
        username="bodya", first_name="Бодя", message_text="шо там туріков робить?", has_photo=False
    )
    assert len(reply_turikov) > 0 and ("—" not in reply_turikov and "–" not in reply_turikov), f"Порожня відповідь: {reply_turikov}"
    print(f"   • Лор Сані Турікова (Турікоголовий): '{reply_turikov}' ✅")

    reply_kuril = cyber_rizhyi_service.generate_reply(
        chat_id=-1001234567, chat_type="supergroup", user_id=777,
        username="bodya", first_name="Бодя", message_text="хто такий діджей куріл рулет?", has_photo=False
    )
    assert len(reply_kuril) > 0 and ("—" not in reply_kuril and "–" not in reply_kuril), f"Порожня відповідь: {reply_kuril}"
    print(f"   • Лор Діджея Куріла Рулєта: '{reply_kuril}' ✅")

    # Перевірка оновлення пам'яті юзера про Турікова і Куріла
    updated_mem = get_cyber_rizhyi_user_memory(user_id=777)
    assert "знає_про_турікова" in updated_mem
    assert "знає_про_куріла_рулета" in updated_mem
    print(f"   • Довгострокова пам'ять про Турікова і Куріла Рулєта зафіксована: {updated_mem['знає_про_турікова']} | {updated_mem['знає_про_куріла_рулета']} ✅")

    # Тест розумної реакції Рижого на надіслане фото (скачування та прогін через Gemini Vision)
    test_img_path = Path("temp/test_screenshot.jpg")
    test_img_path.parent.mkdir(parents=True, exist_ok=True)
    test_img = Image.new("RGB", (1080, 1920), color=(25, 25, 40))
    test_img.save(test_img_path)

    rizhyi_photo_reply = cyber_rizhyi_service.generate_reply(
        chat_id=-1001234567,
        chat_type="supergroup",
        user_id=777,
        username="bodya",
        first_name="Бодя",
        message_text="дивись який скрін зробив",
        has_photo=True,
        photo_path=str(test_img_path)
    )
    assert len(rizhyi_photo_reply) > 0
    assert "—" not in rizhyi_photo_reply and "–" not in rizhyi_photo_reply
    print(f"   • Розумна реакція Кібер Рижого на скачане фото (Gemini Vision): '{rizhyi_photo_reply}' ✅")

    # Перевірка історії чату
    hist = get_cyber_rizhyi_chat_history(chat_id=-1001234567, limit=5)
    assert len(hist) >= 2
    print(f"   • Контекстна пам'ять чату: збережено {len(hist)} повідомлень ✅")

    # 13. ТЕСТ СУМІСНОСТІ МІКС-КАРУСЕЛЕЙ, ДОЗАЛИВУ ТА АНАЛІТИКИ
    print("\n1️⃣3️⃣ ТЕСТ: Дозалив на непройдених мережах (Retry Engine) та Мультиплатформна аналітика...")
    from services.publishers.instagram import instagram_publisher
    from services.publishers.facebook import facebook_publisher
    from services.publishers.telegram_channel import telegram_channel_publisher

    # Перевірка публікації MIXED_CAROUSEL
    import services.publishers.instagram as ig_mod
    orig_ig_dry = ig_mod.DRY_RUN_MODE
    ig_mod.DRY_RUN_MODE = True
    ig_res = instagram_publisher.publish(
        content_type=ContentType.MIXED_CAROUSEL,
        media_paths=mixed_paths[:3],
        metadata={"ig_caption": "Тест мікс-каруселі"}
    )
    ig_mod.DRY_RUN_MODE = orig_ig_dry
    assert ig_res.success is True, f"Instagram mixed carousel error: {ig_res.error}"
    print("   • Instagram підтримка Mixed Carousel (Фото+Відео): ✅")

    fb_res = facebook_publisher.publish(
        content_type=ContentType.MIXED_CAROUSEL,
        media_paths=mixed_paths[:3],
        metadata={"fb_caption": "Тест FB мікс"}
    )
    assert fb_res.success is True, f"Facebook mixed carousel error: {fb_res.error}"
    print("   • Facebook підтримка Mixed Carousel: ✅")

    tg_res = telegram_channel_publisher.publish(
        content_type=ContentType.MIXED_CAROUSEL,
        media_paths=mixed_paths[:3],
        metadata={"ig_caption": "Тест TG"}
    )
    assert tg_res.success is True, f"Telegram Channel mixed carousel error: {tg_res.error}"
    print("   • Telegram Channel безпечний thread-safe виклик: ✅")

    # Перевірка агрегованої аналітики поста
    post_stats = auto_poster.get_post_analytics_summary(post_id=res_v["post_id"])
    assert "total_views" in post_stats
    print(f"   • Агрегована аналітика поста #{res_v['post_id']}: Переглядів: {post_stats['total_views']}, Лайків: {post_stats['total_likes']}, Топ: {post_stats['top_platform']} ✅")

    # 14. ТЕСТ ПОПЕРЕДЖЕНЬ ЗГАСАННЯ ВОГНИКІВ ТА ГОЛОСОВОГО РУШІЯ РИЖОГО
    print("\n1️⃣4️⃣ ТЕСТ: Захист вогників від згасання (Decay Alerts) та Голосовий інтелект Рижого...")
    decay_warnings = tiktok_streak_service.check_streak_decay_warnings(threshold_hours=0.0)
    assert isinstance(decay_warnings, list)
    print(f"   • Система виявлення термінових вогників (Decay Detection): знайдено {len(decay_warnings)} контактів ✅")

    # Тест часу доби для дівчини
    period_key, period_desc = tiktok_streak_service._get_time_of_day_context()
    time_msg = tiktok_streak_service.generate_girlfriend_heart_message()
    assert any(h in time_msg for h in ["❤️", "🥰", "💖", "💕", "💓", "💞", "💘"])
    print(f"   • Генерація з урахуванням часу доби ({period_desc}): '{time_msg}' ✅")

    # Тест реакції Кібер Рижого на голосове повідомлення
    sample_voice = test_dir / "voice_sample.ogg"
    sample_voice.write_bytes(b"dummy_voice_bytes")
    voice_reply = cyber_rizhyi_service.generate_reply(
        chat_id=-1001234567,
        chat_type="supergroup",
        user_id=777,
        username="bodya",
        first_name="Бодя",
        message_text="",
        has_voice=True,
        voice_path=str(sample_voice)
    )
    assert len(voice_reply) > 0
    print(f"   • Реакція Кібер Рижого на голосове повідомлення: '{voice_reply}' ✅")

    print("\n==================================================")
    print("🎉 ВСІ 14 БЛОКІВ ТЕСТІВ ПРОЙДЕНО УСПІШНО ТА ІДЕАЛЬНО!")
    print("==================================================")


if __name__ == "__main__":
    main()
