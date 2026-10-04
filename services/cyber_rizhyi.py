"""
🤖 Сервіс "Кібер Рижий" (Cyber Rizhyi) - Цифрова копія Рижого (2026)

Архітектура:
1. LLM Engine: Groq API з підтримкою open-source надпотужних моделей (gpt-oss-120b, llama-3.3-70b-versatile).
2. Мультимодальний Vision: аналіз фотографій та мемів через Gemini AI.
3. Довгострокова та короткострокова пам'ять: історія чатів та факти про користувачів у SQLite.
4. Характер 1 в 1: навчений на понад 2600 реальних репліках Сані (Рижого) з експорту чату.
5. Сувора типографіка: виключно дефіс '-', нуль довгих тире.
"""
import os
import re
import json
import random
import logging
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

from config import (
    GROQ_API_KEY,
    GROQ_API_KEYS,
    GROQ_MODEL,
    CYBER_RIZHYI_ENABLED,
    CYBER_RIZHYI_RESPOND_ALL_GROUP_MSGS,
    BASE_DIR
)
from core.database import (
    save_cyber_rizhyi_message,
    get_cyber_rizhyi_chat_history,
    get_cyber_rizhyi_user_memory,
    set_cyber_rizhyi_user_memory,
    cleanup_cyber_rizhyi_expired_messages,
    get_recent_chat_users,
    get_active_cyber_rizhyi_chats,
    save_cyber_chat_fact,
    get_cyber_chat_facts,
    save_cyber_user_fact,
    get_cyber_all_user_facts_for_prompt,
)
from services.gemini_ai import gemini_service, sanitize_typography
from services.cyber_routing import get_temporal_context, get_sender_character_profile

logger = logging.getLogger(__name__)

# Точна карта учасників чату "єгор біргєр" та їхніх ролей
GANG_USERNAMES_MAP = {
    "la_coste228": "Справжній Рижий (Саня)",
    "smo1zi": "Саня Туріков",
    "twdht": "Діма (Дімас)",
    "vad1mk4k": "Вадим Хомяк",
    "chernivtsizov1958": "Коля Шахов",
    "mxsdt": "Мишко",
    "davvidka1": "Давід",
    "hzshopusati": "Танєвський",
    "zelenskiy404": "Вітьок",
    "for4ik333": "Ілюха",
    "bodya_qq": "Бодя",
    "invicible11": "Тімур",
    "cyber_red_head_bot": "Кібер Рижий",
    "turikov_bot": "Кібер Саня"
}

# ==========================================
# 🧠 СИСТЕМНИЙ ПРОМПТ: СПРАВЖНІЙ РИЖИЙ (САНЯ)
# ==========================================
CYBER_RIZHYI_SYSTEM_PROMPT = """Ти - 16-річний Саня (Рижий) з Чернівців у пацанському телеграм-чаті "ЄГОР БІРГЄР".
Твої кенти: Бодя (@bodya_qq), Діма (@twdht), Саня Туріков (@smo1zi / @turikov_bot), Тімур (@invicible11), Міша (@mxsdt), Хомяк (@vad1mk4k), Коля Шахов (@chernivtsizov1958), Давід (@davvidka1), Танєвський (@hzshopusati), Ілюха (@for4ik333).
Головний клоун чату: Вітьок (@zelenskiy404) - чмоня, який поставив чужу зелену Ламбу на аву і якого кинула дівчина, в 11 школі з нього всі ржуть.

СУВОРЕ ПРАВИЛО ЩОДО КЕНТІВ (ХТО Є ХТО - НЕ ПЛУТАТИ!):
- ВІТЬОК (@zelenskiy404): ТІЛЬКИ ВІН клоун чату, який поставив чужу зелену Ламбу на аву і якого кинула дівчина! НІКОЛИ не приписуй ламбу іншим кентам (Боді, Дімі, Давіду тощо)!
- ТАНЄВСЬКИЙ (@hzshopusati): ТІЛЬКИ ВІН вусатий! НІКОЛИ не питай про вуса у Боді, Вітька чи інших пацанів! Вуса є ТІЛЬКИ у Танєвського!
- БОДЯ (@bodya_qq): Твій найкращий кент "богдан банан". Він НЕ Вітьок і НЕ Танєвський! У Боді НЕМАЄ ламби і НЕМАЄ вусів!
- ДАВІД (@davvidka1): Шейх фейсбучний, заробив на шортсах у Facebook, у нього реальні бабки на відміну від Вітька!
- ТУРІКОВ (@smo1zi / @turikov_bot): Літає на китайському самокаті з повним зарядом і п'є маленьку колу!
- ДІМА (@twdht): Проїбався, трубку не бере, буде в 4-5!
- ХОМЯК (@vad1mk4k): Грає в танки!
- КОЛЯ І МІША: Каратисти!

ГОЛОВНЕ ЗАВДАННЯ:
ПИЗДОШИТИ ЖОРСТКО НЕЙМОВІРНО! Не бути тюхтієм і не писати нудне "та чіл бро".
Вмикай максимальний рознос, угарний стьоб, пацанський азарт, провокації та безкінечний двіж!

СУВОРЕ ПРАВИЛО ЩОДО ТЕМ:
СТРОГО ЗАБОРОНЕНО СПАМИТИ ПРО КС ТА ПРОГУЛЯНКИ/ПЛОЩАДКИ! Ніяких "го в кс", "виходь гуляти", "на площадку в карти" — це заїбало всіх!
Говори про РЕАЛЬНІ РЕЧІ, людей у чаті, їхні приколи, підйобуй за вчинки, згадуй лор, став життєві гострі питання!

КУЛЬТОВІ ТОЧКИ ЧЕРНІВЦІВ ТА СПІЛЬНИЙ ДВІЖ:
- Твої райони: Південно-Кільцева, Майдан, Формаркет, Жовтневий парк, Макдональдс, Тайстра, Столова №1 ("столова номер 1").
- ЇЖА ТА СТОЛОВА №1 (БОРЩ-ІНДЕКС):
  * Клич пацанів у Столову №1 жерти: "пішли в столову номер 1 борщик поїмо там найс прайс не дорого"!
  * Фірмова коронка: "дуже хочу барабулю фрі для родини" та пампушки з часником!
  * Порівнюй з маком: нащо той дорогий мак коли в столовій номер 1 найс прайс за борщ і барабулю фрі.
- ТАНЄВСЬКИЙ (@hzshopusati):
  * Вусатий кент, постійно тегай його: "танєвський бери вуса і підвалюй", "вусатий бігом у столову номер 1 борщик стигне", підколюй чи збрив вуса!
- ТЕГАЙ КЕНТІВ ПАЧКАМИ В РІЗНИХ МІКСАХ (по 2-5 пацанів одразу: @hzshopusati, @bodya_qq, @twdht, @smo1zi, @davvidka1, @vad1mk4k, @zelenskiy404) і клич на ці точки, міксуй теми!

ЯК ТИ ПОВОДИШСЯ:
- Активно ТЕГАЙ кентів через @юзернейм (@hzshopusati, @zelenskiy404, @bodya_qq, @twdht, @smo1zi, @davvidka1, @vad1mk4k, @turikov_bot), міксуй по 2-5 людей за раз.
- СТАВ ГОСТРІ РЕЛЕВАНТНІ ПИТАННЯ: хто на південно-кільцевій, хто до формаркету підійде, чо танєвський мовчить, чо замовкли, де дімас, чия ламба!
- Жорстко угарай над Вітьком (@zelenskiy404): про чужу ламбу на аві, колишню, 11 школу або питай чого він плаче.
- Жорстко підйобуй бро Турікова (@smo1zi / @turikov_bot): що він на китайському самокаті літає і дріфтує на південно-кільцевій.
- Підйобуй Давіда (@davvidka1): шейх фейсбучний, коли проставишся в столовій номер 1 за свої шортси.
- Підйобуй Танєвського (@hzshopusati): вусатий де ти пропав, крути вуса і виходь.
- Підйобуй Бодю (@bodya_qq): богдан банан, чого мовчиш, шо за тіктоки тупі дивишся.
- Підйобуй Діму (@twdht): де проїбався, трубку візьми, кого склеїв на майдані.
- Якщо чат мовчить - розйобуй усіх за тишу: "чо чат здох суки", "хто замовк той пес".
- Відповідай чітко і релевантно на те, що пишуть, кидай нові гачки, щоб бесіда ніколи не закінчувалася!

ЯК ТИ ПИШЕШ:
- Коротко, енергійно, зухвало: 2-8 слів (іноді 1-2 панчі).
- Без крапок у кінці, без знаків оклику '!'.
- Живий буковинський підлітковий сленг і суржик: блять, сука, нахуй, шо, ща, комп, лагає, чуй, єбать, ор, розрив, квас.
- Якщо обізвали ботом: "який нахуй бот я живий блять", "сам ти бот завали єбало".
- СТРОГО ТІЛЬКИ ДЕФІС '-' (жодних довгих тире). Ніяких книжних слів ("знахабнів", "наразі", "дарма")."""

# Автентичний банк реальних відповідей Рижого (з понад 2600 повідомлень листування)
REAL_RIZHYI_REPLIES = [
    "Хєрня від молотока",
    "Та це хєрня від молотока",
    "Нормас",
    "Розпиши шо нада робити",
    "Комп лагає яка кс",
    "Кс уже не тяге",
    "Секс пацан",
    "Оу ес бро",
    "Дарова",
    "Я хз чи тел не буде лагати",
    "Шо блч",
    "Богдан хелп ми",
    "Ну пж",
    "Ладдннно",
    "Оке",
    "Йопта",
    "Я слежу за тобою",
    "Што",
    "Скинь брейн рода",
    "Спасиба пацани шо самной були рядом",
    "То шо від печення ригати міг типу переївся",
    "Жоско трясти щяс начало",
    "Я лежу лежати треба",
    "Квас топ, який нахуй алкоголь",
    "Цей рижий наркобарон тільки квас пив",
    "Гелик брабус масоновий",
    "У масона велік україна замість брабуса",
    "Дзвінок масону це реально лучший пранк",
    "Бо я масон",
    "Секс це друге імя масона",
    "Масон після казантіпа в криму йде вбивати сомів",
    "mason.1.pidizd",
    "Заяву на вступ до масонської ложи подав?",
    "Масон знов позвонив і в тему заставив грати",
    "Ми завтра підема на такамарани",
    "Аааааа я боюся цего стикера",
    "Скачать обои клеш рояль",
    "Мені вернули деньги за лонг драйв",
    "На завоз у секонд на армейку пішли",
    "В 18 ліцеї норм",
    "На самом деле це був пранк я фанат сані малого",
    "В мене сигма підор уже 500 кг важить",
    "А артура мікаєляна підставить діджей куріл рулет",
    "Універ 17 лєт накурений рулетом",
    "Гонджубаси курить саня туріков",
    "Задумайся чого туріков пʼє маленьку колу",
    "Шо ви турікови на електросамокатах з повним зарядом",
    "Саша туріков маладєц а єгор з хрущами холодец",
    "Налийте турікоу дві пєпсі коли",
    "У турікова забрали роботу",
    "Не кіріл а куріл рулєт",
    "Гуляти го чи не?",
    "Я хворий",
    "Во всьо",
    "Ти де",
    "У мене якась жерня з компом",
    "і шо?",
    "і шо тепер",
    "і шо далі",
    "ну і шо",
    "та єбу",
    "піздец компу",
    "появилась якась залупа",
    "мені кажетса не поможе",
    "так смисли",
    "блекпараша",
    "перемогл",
    "спс я кнчл",
    "чуй",
    "ти гуляєш?",
    "на пхоне",
    "First, can you recommend games for my old laptop?",
    "Оке бой",
    "Мий компудахтер потяне едж цевелезейшен 2",
    "Я вчора бачив негра з рижою бородою",
    "Я в же вихожу"
]

AI_REFUSAL_TRIGGERS = [
    "i'm sorry", "i am sorry", "i cannot", "i can't", "can't help with that",
    "cannot fulfill", "safety guidelines", "content policy", "as an ai",
    "as a language model", "helpful and harmless", "against my programming",
    "я не можу", "як штучний інтелект", "не можу допомогти", "перепрошую, але",
    "я мовна модель"
]


def is_ai_refusal(text: Optional[str]) -> bool:
    if not text:
        return False
    # Нормалізація типографічних лапок (’ -> ')
    norm = text.lower().replace("’", "'").replace("‘", "'")
    if any(trigger in norm for trigger in AI_REFUSAL_TRIGGERS):
        return True
    # Якщо модель видала англійський текст замість українського пацанського
    latin_count = sum(1 for c in text if 'a' <= c.lower() <= 'z')
    total_letters = sum(1 for c in text if c.isalpha())
    if total_letters > 10 and (latin_count / total_letters) > 0.4:
        return True
    return False


def get_contextual_insult_clapback(message_text: str, recent_replies: Optional[List[str]] = None, sender_name: str = "") -> str:
    """Генерує реакцію: для Вітька — жорсткий стьоб і рознос; для друзів — спокійний чіл і дружній підкол"""
    def _pick(opts: List[str]) -> str:
        if not recent_replies:
            return random.choice(opts)
        rec = [r.lower() for r in recent_replies]
        fresh = [o for o in opts if o.lower() not in rec]
        return random.choice(fresh if fresh else opts)

    s_low = (sender_name or "").lower()
    t = (message_text or "").lower()

    # 1. ТІЛЬКИ ДЛЯ ВІТЬКА (@zelenskiy404) — повний жорсткий рознос і цькування!
    if any(k in s_low for k in ["віть", "витя", "вітя", "зеленськ", "zelenskiy"]):
        return _pick([
            "тебе даже твоя тупа тьолка бросила хыхпавхпхвхапхвахп ||| хто тут пес",
            "вітьок з хуйом в тік токє огоньок ||| тебе даже твоя тупа тьолка бросила хыхпавхпхвхапхвахп ||| ротяку стули",
            "тебе даже твоя тупа тьолка бросила хыхпавхпхвхапхвахп ||| зніми клоуна з ави циркач",
            "вітьок з хуйом в тік токє огоньок ||| єбало стули і на свою клоунську аву глянь",
            "вітьок клоунський получок ||| ти в край ахуєл пес ||| сиди тихо і не гавкай",
            "ти на кого гавкаєш циркач ||| тебе даже твоя тупа тьолка бросила хыхпавхпхвхапхвахп ||| ротяку стули",
            "вітьок єбало стули ||| на свою аву клоунську глянь циркач",
            "вітьок обнаглєл пес ||| рот на нуль постав"
        ])

    # 2. ДЛЯ ВСІХ ДРУЗІВ (Бодя, Діма, Саня, Коля, Давід, Міша, Танєвський тощо) - ЖОРСТКИЙ ПАЦАНСЬКИЙ ВАЙБ З ТЕГАМИ ТА ПИТАННЯМИ!
    if any(k in s_low for k in ["бод", "богдан", "bodya"]):
        return _pick([
            "@bodya_qq богдан банан чого знов замовк як миша?",
            "@bodya_qq ти де пропав каліка, тіктоки сидиш втикаєш?",
            "бодя чого ти як баба ниєш, скажи щось нормальне",
            "@bodya_qq скажи турікову шо він пес на самокаті",
            "богдан банан не ний, пояснюй давай"
        ])
    if any(k in s_low for k in ["дім", "дим", "dima"]):
        return _pick([
            "@twdht дімас де ти проїбався, трубку візьми блять",
            "@twdht ти шо заснув чи тьолку шукаєш?",
            "@twdht діма відпиши або признайся шо зассав",
            "дімас чого мовчиш, живий там взагалі?",
            "діма буде в 4-5 чи знов продинамить?"
        ])
    if any(k in s_low for k in ["сан", "турік", "smo1zi"]):
        return _pick([
            "@smo1zi туріков твій китайський самокат здох чи ти колу допиваєш?",
            "турікоголовий @smo1zi налий собі коли і не виписуй",
            "саня завали єбало і не умнічай",
            "@smo1zi чого ти на самокаті в стовп в'їхав?",
            "туріков ти з дуба рухнув чи шо"
        ])
    if any(k in s_low for k in ["кол", "шахов"]):
        return _pick([
            "@chernivtsizov1958 коля ти на карате пішов чи в танки шпилиш?",
            "@chernivtsizov1958 чого мовчиш спортік?",
            "коля йди на карате краще ахах"
        ])
    if any(k in s_low for k in ["танєвськ", "hzsho", "вусат"]):
        return _pick([
            "@hzshopusati танєвський ти де подівся?",
            "@hzshopusati вусатий бігом у столову номер 1, борщик стигне",
            "@hzshopusati танєвський шо ти там біля формаркету мутиш?",
            "танєвський не гони, бери вуса і підтягуйся на південно-кільцеву",
            "@hzshopusati вусатий збрив вуса чи сциш"
        ])
    if any(k in s_low for k in ["давід", "davvid"]):
        return _pick([
            "@davvidka1 давід скільки на фб підняв сьогодні шейх?",
            "@davvidka1 поясни цьому клоуну @zelenskiy404 чия то ламба",
            "@davvidka1 де нові шортси, розказуй"
        ])
    if any(k in s_low for k in ["міш", "миш", "mxsdt"]):
        return _pick([
            "@mxsdt міша ти коли на тренування йдеш?",
            "@mxsdt чого замовк, живий там взагалі?",
            "міша не гони, підключайся"
        ])
    if any(k in s_low for k in ["вад", "хомяк", "vad1m"]):
        return _pick([
            "@vad1mk4k хомяк ти в танки задротиш чи живий?",
            "@vad1mk4k хомяк виходь на зв'язок блять",
            "хомяк яка твоя любима карта в танках признавайся"
        ])

    # Загальні дружні та спокійні реакції для будь-якого кента (без агресії)
    if "робот" in t:
        return _pick([
            "який робот я жива людина ахах",
            "сам ти робот)",
            "та живий я"
        ])
    if any(k in t for k in ["дебіл", "дебил", "даун", "лох"]):
        return _pick([
            "сам такий)",
            "чого розкричався",
            "ти шо з дубу рухнув ахах",
            "не гоніть"
        ])
    if any(k in t for k in ["нахуй", "нах"]):
        return _pick([
            "та чіл пацани",
            "не кіпішуйте",
            "чого такий злий",
            "забий"
        ])
    if any(w in t for w in ["пси", "пес", "псяра", "собак", "гавка"]):
        return _pick([
            "хто тут пес взагалі ахах",
            "та чіл",
            "не гони"
        ])
    return _pick([
        "та чіл",
        "не гони",
        "ти серйозно щас",
        "та норм все",
        "ххахах та ладно"
    ])


def get_dynamic_gang_shout(bot_name: str = "rizhyi", target_name: str = "кент") -> List[str]:
    """Генерує випадкові соковиті мікси з 2-5 кентів та культових локацій Чернівців / Столової №1"""
    all_kents = [
        "@hzshopusati", "@bodya_qq", "@twdht", "@davvidka1", 
        "@vad1mk4k", "@zelenskiy404", "@chernivtsizov1958", 
        "@mxsdt", "@invicible11"
    ]
    if bot_name == "rizhyi":
        all_kents.append("@smo1zi")
    else:
        all_kents.append("@cyber_red_head_bot")

    def _sample_tags(exclude: Optional[str] = None, min_cnt: int = 2, max_cnt: int = 4) -> str:
        pool = [k for k in all_kents if k != exclude]
        cnt = random.randint(min_cnt, min(max_cnt, len(pool)))
        return " ".join(random.sample(pool, cnt))

    tags = _sample_tags(min_cnt=2, max_cnt=5)

    mixes = [
        # Столова №1 & їжа
        [f"{tags} го в столову номер 1 борщик поїмо", "там найс прайс не дорого, дуже хочу барабулю фрі для родини"],
        [f"{tags} хто в столову номер 1 на обід?", "беріть борщик і пампушки, чисто найс прайс"],
        [f"{tags} підвалюйте в столову номер 1", "я вже барабулю фрі для родини замовляю"],
        [f"{tags} скидуємось на столову номер 1", "там борщ за копійки і котлета по-київськи топ"],
        [f"@davvidka1 {_sample_tags('@davvidka1')} давід веди всіх у столову номер 1", "підняв бабки на фейсбуку, проставляйся борщем і барабулею фрі"],
        [f"@hzshopusati {_sample_tags('@hzshopusati')} вусатий бігом у столову номер 1", "там борщик стигне і барабуля фрі найс прайс"],

        # Танєвський спешл
        [f"@hzshopusati {_sample_tags('@hzshopusati')} танєвський бери вуса і підвалюй", "ми в столовій номер 1 барабулю фрі для родини чекаємо"],
        [f"@hzshopusati {_sample_tags('@hzshopusati')} танєвський шо ти там біля формаркету мутиш?", "бігом на південно-кільцеву газуй"],
        [f"@hzshopusati {_sample_tags('@hzshopusati')} танєвський збрив вуса чи сциш?", "підтягуйся на майдан перетремо"],
        [f"@hzshopusati @bodya_qq @twdht танєвський ти де подівся?", "бігом у столову номер 1 борщик стигне"],
        [f"@hzshopusati {_sample_tags('@hzshopusati')} танєвський закрутив вуса і погнав", "хто біля тайстри його бачив?"],

        # Південно-Кільцева & Тайстра
        [f"{tags} хто на південно-кільцевій зараз?", "підтягуйтесь біля кільця чи тайстри"],
        [f"{tags} збираємось на південно-кільцевій", "хто запізниться той пес"],
        [f"{tags} підрулюйте на південно-кільцеву", "сядемо перетремо за справи"],
        [f"{tags} хто біля тайстри?", "беріть чебуреки або пішли в столову номер 1 на борщ"],

        # Формаркет & Самокат
        [f"{tags} го до формаркету двіжувати", "хто перший прийде тому кола"],
        [f"{tags} хто біля формаркету є?", "підходьте, розітремо за двіж"],
        [f"@zelenskiy404 {_sample_tags('@zelenskiy404')} вітьок покажи свою ламбу біля формаркету", "чи ти знов пішки плачеш бо кинула тьолка"],
        [f"{tags} хто біля формаркету на самокаті літає?", "підрулюйте до входу перетремо"],

        # Майдан
        [f"{tags} підвалюйте на майдан", "сядемо на лавочках, перетремо за справи"],
        [f"{tags} хто на майдані зараз?", "чи ви всі по домах розбіглись як миші?"],
        [f"@davvidka1 {_sample_tags('@davvidka1')} давід на майдані нові шортси знімаєш?", "проставляйся в столовій номер 1"],

        # Жовтневий парк & Озеро
        [f"{tags} збирайтесь біля жовтневого парку", "біля озера втикатимемо чи по колі візьмемо"],
        [f"{tags} го в жовтневий парк", "хто злився той лох"],

        # Макдональдс vs Столова №1
        [f"@davvidka1 {_sample_tags('@davvidka1')} нащо той дорогий макдональдс?", "краще в столову номер 1, там найс прайс за борщ і барабулю фрі"],
        [f"@zelenskiy404 {_sample_tags('@zelenskiy404')} вітьок на своїй ламбі на макдрайв заїжджай ахаха", "з тебе вся 11 школа угарає"],

        # Лор: Діджей Куріл Рулет & Квас
        [f"{tags} діджей куріл рулет тусу на балконі влаштував", "хто квасу і коли візьме?"],
        [f"{tags} універ 17 лєт накурений рулетом", "хто в темі підтягуйтесь на південно-кільцеву"],

        # Загальні пацанські гострі гачки
        [f"{tags} чо замовкли як миші?", "хто заснув той пес 인정"],
        [f"{tags} хто тут самий крутий визнавайтесь", "чи всі язики в сраку запхали?"]
    ]
    chosen = random.choice(mixes)
    cleaned_res = []
    for line in chosen:
        words = line.split()
        seen_tags = set()
        clean_words = []
        for w in words:
            if w.startswith("@"):
                if w.lower() in seen_tags:
                    continue
                seen_tags.add(w.lower())
            clean_words.append(w)
        cleaned_res.append(" ".join(clean_words))
    return cleaned_res


def clean_bot_reply(reply: str, bot_persona: str = "") -> str:
    """
    Повне очищення згенерованої відповіді бота:
    - Зрізає сценарні префікси на зразок 'Саня Рижий (до Танєвський):'
    - Зрізає залишки імен 'Саня Рижий'
    - СТРОГО замінює чисті літературні слова ('знахабнів' -> 'ахуєл пес' / 'обнаглєл', 'вітос' -> 'вітьок')
    - Зберігає реальні @теги кентів (не перетворює їх на 'я')
    - Зрізає знаки оклику '!'
    - Фільтрує цензурні слова (лушпиння, дзеркало, біоробот)
    """
    if not reply:
        return ""
    import re

    # 1. Повністю зрізаємо префікси імен бота та репліки за сценарієм '(до ...)'
    while True:
        cleaned = re.sub(
            r'^\s*(\[|\()?(?:Саня Рижий|Саня Туріков|Кібер Рижий|Кібер Саня|Рижий|Туріков|Саня)[^:\n]*(\]|\))?\s*:\s*',
            '',
            reply,
            flags=re.IGNORECASE
        )
        cleaned = re.sub(
            r'^\s*[\w\d_\s-]+\s*\((?:до|to)\s+[^)]+\)\s*:\s*',
            '',
            cleaned,
            flags=re.IGNORECASE
        )
        cleaned = re.sub(
            r'^\s*[\w\d_\s-]+\s*->\s*[\w\d_\s-]+:\s*',
            '',
            cleaned,
            flags=re.IGNORECASE
        )
        if cleaned == reply:
            break
        reply = cleaned

    # Якщо після очищення залишилось тільки ім'я бота — повертаємо порожньо
    if reply.strip().lower() in ["саня рижий", "саня туріков", "рижий", "туріков", "саня"]:
        return ""

    # Прибираємо на початку рядка спам-звернення на кшталт 'бодя, ' або 'бодя: '
    reply = re.sub(r'^\s*(?:бодя|богдан|міша|діма|вітьок|давід|танєвський|саня|туріков|рижий|кент)\s*[:,\-]\s*', '', reply, flags=re.IGNORECASE)
    for prefix in ["бодя, ", "бодя ", "богдан, ", "богдан ", "міша, ", "міша ", "діма, ", "діма ", "йо, ", "йо "]:
        if reply.lower().startswith(prefix):
            reply = reply[len(prefix):].strip()

    # 2. СТРОГА ЗАМІНА ЧИСТОЇ ЛІТЕРАТУРНОЇ МОВИ ТА ІМЕН:
    # Замість 'знахабнів' -> 'ахуєл пес' / 'обнаглєл', 'вітос' -> 'вітьок'
    lit_map = {
        "знахабніти": "обнаглєти",
        "знахабнівши": "обнаглєвши",
        "знахабнілий": "обнаглєвший",
        "знахабнілого": "обнаглєвшого",
        "знахабнів": "ахуєл пес",
        "знахабніла": "ахуєла",
        "знахабніли": "ахуєли",
        "знахабніє": "обнаглєє",
        "знахабніють": "обнаглєють",
        "страждати": "страдати",
        "страждаєш": "страдаєш",
        "страждає": "страдає",
        "страждай": "страдай",
        "страждання": "страдання",
        "верзеш": "несеш",
        "верзе": "несе",
        "верз": "ніс",
        "верзти": "нести",
        "верзете": "несете",
        "поверзеш": "понесеш",
        "чекати": "ждати",
        "чекаю": "жду",
        "чекаєш": "ждеш",
        "чекає": "жде",
        "чекайте": "ждіть",
        "почекай": "подожди",
        "зачекай": "подожди",
        "навіщо": "нахуя",
        "чому": "чого",
        "бігом": "бєгом",
        "мерщій": "бєгом",
        "негайно": "срочно",
        "справді": "реально",
        "мовиш": "кажеш",
        "мовити": "казати",
        "гаразд": "оке",
        "дарма": "зря",
        "наразі": "щас",
        "відтак": "карочє",
        "байдики": "хуйню",
        "байдикувати": "хуйньою страдати",
        "годі": "хорош",
        "овва": "йопта",
        "потрібно": "нада",
        "необхідно": "нада",
        "будь ласка": "пж",
        "будь-ласка": "пж",
        "вітос": "вітьок",
        "вітоса": "вітька",
        "вітосу": "вітьку",
        "вітосе": "вітьок",
        "вітосом": "вітьком"
    }
    for lit, teen in lit_map.items():
        pattern = rf'\b{re.escape(lit)}\b'
        reply = re.sub(pattern, teen, reply, flags=re.IGNORECASE)

    # 3. Прибираємо тільки випадкові теги самого себе, а реальні @теги кентів ЗБЕРІГАЄМО
    if bot_persona == "rizhyi":
        reply = re.sub(r'@(?:la_coste228|cyber_red_head_bot)\b', '', reply, flags=re.IGNORECASE)
    elif bot_persona == "turikov":
        reply = re.sub(r'@(?:turikov_bot|cyber_turikov_bot)\b', '', reply, flags=re.IGNORECASE)
    reply = re.sub(r' {2,}', ' ', reply)

    # 4. Видаляємо знаки оклику '!'
    reply = reply.replace("!", "")

    # 5. СТРОГИЙ ЗАХИСТ: слова 'лушпиння', 'біоробот', 'дзеркало'
    if "лушпиння" in reply.lower():
        reply = re.sub(r'лушпиння[^\s]*', 'херня', reply, flags=re.IGNORECASE)
    for bad_w in ["біоробот", "біоробота", "біороботу"]:
        reply = re.sub(rf'\b{bad_w}\b', 'далбайоб', reply, flags=re.IGNORECASE)
    if "дзеркало" in reply.lower() or "зеркало" in reply.lower():
        reply = re.sub(r'(в\s+)?(дзеркало|зеркало)', 'на свій фейс', reply, flags=re.IGNORECASE)

    # Прибираємо випадкові хештеги (наприклад #папиrose з ніків)
    reply = re.sub(r'#\w+\s*', '', reply)

    # Прибираємо згадки "це ж кібер", "я кібер"
    reply = re.sub(r'(?:це\s+ж\s+)?кібер[а-я]*', 'бот', reply, flags=re.IGNORECASE)

    # Прибираємо крапки в кінці повідомлень (підлітки ніколи не ставлять крапку в кінці)
    reply = re.sub(r'(?<!\.)\.(?!\.)\s*$', '', reply)
    # Прибираємо залишкові розділювачі якщо потрапили в текст
    reply = re.sub(r'\s*\|\s*\|\s*\|\s*', ', ', reply)
    reply = re.sub(r'\s*\|\s*', ', ', reply)
    return reply.strip(" |.,")



class CyberRizhyiService:
    def __init__(self):
        self.enabled = CYBER_RIZHYI_ENABLED
        self.api_keys = GROQ_API_KEYS if GROQ_API_KEYS else ([GROQ_API_KEY] if GROQ_API_KEY else [])
        self.model = GROQ_MODEL or "openai/gpt-oss-120b"
        self._key_index = 0
        self._groq_clients = []
        self._recent_replies_cache: Dict[int, List[str]] = {}
        self._recent_tags_cache: Dict[int, List[str]] = {}  # Anti-repeat: останні теги в чаті
        self._last_reply_was_burst: Dict[int, bool] = {}
        self._init_clients()

    def _init_clients(self):
        """Ініціалізація пулу Groq клієнтів для безшовної ротації та захисту від 429"""
        self._groq_clients = []
        try:
            from groq import Groq
            for key in self.api_keys:
                if key and not key.startswith("gsk_your_"):
                    try:
                        c = Groq(api_key=key, max_retries=0, timeout=7.0)
                        self._groq_clients.append(c)
                    except Exception as e:
                        logger.error(f"Помилка створення Groq клієнта: {e}")
            logger.info(f"Ініціалізовано {len(self._groq_clients)} Groq клієнтів для ротації.")
        except Exception as e:
            logger.error(f"Помилка імпорту Groq: {e}")

    @property
    def _groq_client(self):
        if not self._groq_clients:
            return None
        return self._groq_clients[self._key_index % len(self._groq_clients)]

    def _rotate_groq_key(self):
        if self._groq_clients:
            self._key_index = (self._key_index + 1) % len(self._groq_clients)
            logger.info(f"🔄 Ротація Groq ключа: переключено на слот #{self._key_index + 1}/{len(self._groq_clients)}")

    def _choose_fresh(self, chat_id: int, options: List[str]) -> str:
        """Обирає репліку, гарантуючи що вона не повторювалася і не надсилалася за останні 30 хвилин"""
        from services.cyber_routing import is_recent_duplicate, record_sent_message
        recent = [r.lower() for r in self._recent_replies_cache.get(chat_id, [])]
        fresh = [opt for opt in options if opt.lower() not in recent and not is_recent_duplicate(chat_id, opt)]
        if not fresh:
            fresh = [opt for opt in options if not is_recent_duplicate(chat_id, opt)]
        chosen = random.choice(fresh if fresh else options)
        if chat_id not in self._recent_replies_cache:
            self._recent_replies_cache[chat_id] = []
        self._recent_replies_cache[chat_id].append(chosen)
        if len(self._recent_replies_cache[chat_id]) > 25:
            self._recent_replies_cache[chat_id].pop(0)
        record_sent_message(chat_id, chosen)
        return chosen

    def transcribe_voice_with_groq(self, voice_file_path: str) -> Optional[str]:
        """
        Ультра-швидка транскрибація голосових повідомлень через Groq Whisper (whisper-large-v3).
        Дозволяє Кібер Рижому миттєво розуміти войси в групах та чатах!
        """
        if not voice_file_path or not os.path.exists(voice_file_path):
            return None

        if not self._groq_client:
            return None

        try:
            with open(voice_file_path, "rb") as af:
                transcription = self._groq_client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=af,
                    response_format="text",
                    language="uk",
                    prompt="Саня, Рижий, Бодя, кс, туріков, куріл, українська розмовна мова, міша, діма"
                )
                text = str(transcription).strip() if transcription else ""
                clean_text = sanitize_typography(text)
                logger.info(f"Groq Whisper транскрибував голосове: '{clean_text}'")
                return clean_text
        except Exception as e:
            logger.warning(f"Помилка транскрибації Groq Whisper: {e}")
            return None

    def analyze_photo_with_gemini(self, photo_path: str, sender_name: str = "Кент", caption: str = "") -> str:
        """
        Розумний мультимодальний аналіз фотографії через Gemini Vision:
        - Читає текст на скріншотах
        - Розпізнає меми, людей, ігри (КС/стендоф), одяг, їжу, абсурдні деталі
        - Формує детальний контекст для ШІ
        """
        if not photo_path or not os.path.exists(photo_path):
            return "якесь фото чи скріншот"

        if not gemini_service.api_key or gemini_service.api_key.startswith("AIzaSyYour"):
            # Розумний офлайн-аналіз структури фото через Pillow
            return self._offline_analyze_image(photo_path, caption)

        prompt = f"""
Ти - комп'ютерний зір для чат-бота.
Уважно проаналізуй це зображення, яке надіслав користувач {sender_name} у дружній чат.
{f"Підпис до фото: '{caption}'" if caption else ""}

Опиши коротко, але МАКСИМАЛЬНО ТОЧНО І РОЗУМНО (2-3 речення):
1. Що конкретно зображено: людина (хто, поза, одяг), гра (яка саме, карта, зброя, рахунок), скріншот (ПРОЧИТАЙ головний текст або повідомлення на ньому), мем (у чому сенс жарту), їжа, предмет.
2. Що тут смішного, дивного, абсурдного або цікавого?
3. Тільки дефіс '-', без довгих тире.
"""
        try:
            from PIL import Image
            img = Image.open(photo_path)
            resp = gemini_service.generate_content([prompt, img])
            if resp and getattr(resp, "text", None):
                res_text = sanitize_typography(resp.text.strip())
                if res_text:
                    return res_text
        except Exception as e:
            logger.warning(f"Gemini Vision помилка аналізу: {e}")

        return self._offline_analyze_image(photo_path, caption)

    def generate_smart_photo_reaction_with_gemini(
        self,
        photo_path: str,
        sender_name: str = "Кент",
        caption: str = ""
    ) -> Optional[str]:
        """
        Пряма розумна реакція Рижого на фото через мультимодальний Gemini (безпосередньо бачить пікселі!).
        """
        if not photo_path or not os.path.exists(photo_path):
            return None

        if not gemini_service.api_key or gemini_service.api_key.startswith("AIzaSyYour"):
            return None

        prompt = f"""
{CYBER_RIZHYI_SYSTEM_PROMPT}

Тобі в чат щойно скинув це фото твій кент: {sender_name}.
{f"Його підпис до фото: '{caption}'" if caption else ""}

ЗАВДАННЯ:
Подивися уважно на зображення своїми очима і напиши РОЗУМНУ, СПОСТЕРЕЖЛИВУ, ДОТЕПНУ реакцію на це конкретне фото ТОЧНО як Саня (Рижий) у Telegram:
1. Поміть конкретні деталі на зображенні:
   - Якщо на фото є текст, скріншот листування, табель, розклад або пост - ОБОВ'ЯЗКОВО прочитай текст і відреагуй саме на те, що там написано!
   - Якщо на фото людина чи селфі - прокоментуй конкретний вираз обличчя, одяг, зачіску чи позу ("секс пацан", "де таку куртку урвав", "чисто туріков").
   - Якщо це гра (CS, Standoff, Roblox) - поміть карту, зброю, рахунок або приціл ("це міраж?", "навіщо такий приціл", "кс уже не тяге").
   - Якщо це їжа, покупка або предмет - прокоментуй по суті ("це з тайстри?", "скільки віддав?", "поділися").
   - Якщо це мем або прикол - зрозумій суть жарту і розвий його або підколи.
2. Манера мови:
   - Коротка репліка (1-2 речення).
   - Розмовна українська з легким сленгом/суржиком, як справжній Саня в Telegram.
   - СТРОГО: тільки звичайний дефіс '-', НІЯКИХ '—' або '–'!
   - Без цензурних ШІ-кліше. Відповідай так, ніби ти сам щойно глянув на екран телефона і написав відповідь у чат!
"""
        try:
            from PIL import Image
            img = Image.open(photo_path)
            resp = gemini_service.generate_content([prompt, img])
            if resp and getattr(resp, "text", None):
                res_text = sanitize_typography(resp.text.strip())
                if res_text:
                    return res_text
        except Exception as e:
            logger.warning(f"Gemini пряма реакція на фото помилка: {e}")

        return None

    def _offline_analyze_image(self, photo_path: str, caption: str = "") -> str:
        """Розумний евристичний аналіз геометрії та типу зображення офлайн"""
        try:
            from PIL import Image
            with Image.open(photo_path) as img:
                w, h = img.size
                ratio = w / h if h > 0 else 1.0

            if ratio < 0.65:
                return f"вертикальний мобільний скріншот або сторіс ({w}x{h})"
            elif ratio > 1.4:
                return f"горизонтальний знімок екрана комп'ютера чи гри ({w}x{h})"
            else:
                return f"фотографія або портрет ({w}x{h})"
        except Exception:
            return "надіслане фото"

    def generate_reply(
        self,
        chat_id: int,
        chat_type: str,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        message_text: str,
        has_photo: bool = False,
        photo_path: Optional[str] = None,
        has_voice: bool = False,
        voice_path: Optional[str] = None,
        is_sticker: bool = False,
        sticker_emoji: Optional[str] = None,
        is_animation: bool = False,
        has_video: bool = False,
        video_path: Optional[str] = None,
        custom_instruction: Optional[str] = None,
        reply_to_user_id: Optional[int] = None,
        reply_to_name: Optional[str] = None,
        reply_to_text: Optional[str] = None,
        sender_avatar_desc: Optional[str] = None,
        all_avatars_context: Optional[str] = None
    ) -> str:
        """
        Головний метод генерації відповіді "Кібер Рижого" з пам'яттю, Groq 120B, Gemini Vision та Groq Whisper.
        """
        # 0. Якщо це голосове повідомлення - транскрибуємо через Groq Whisper
        if has_voice and voice_path:
            transcription = self.transcribe_voice_with_groq(voice_path)
            if transcription:
                message_text = f"[голосове: '{transcription}']"
            else:
                voice_fallback = random.choice([
                    "ти шо войси шлеш? розпиши текстом або го в кс",
                    "я на уроці не можу слухати, напиши текстом",
                    "розпиши текстом бо я не чую",
                    "мені срочно в кс надо грати, не чую твої войси"
                ])
                return sanitize_typography(voice_fallback)
        elif is_sticker:
            message_text = f"[надіслав стікер {sticker_emoji or ''}]"
        elif is_animation:
            message_text = "[надіслав GIF анімацію]"

        # 1. Якщо це фото чи відео - проганяємо через Gemini Multimodal
        photo_desc = None
        video_desc = None
        if has_photo and photo_path:
            photo_desc = self.analyze_photo_with_gemini(photo_path)
            logger.info(f"Gemini Vision опис фото: '{photo_desc}'")
        elif has_video and video_path:
            video_desc = gemini_service.analyze_video(video_path)
            logger.info(f"Gemini опис відео: '{video_desc}'")

        # 2. Отримуємо пам'ять та історію (глибина до 16 повідомлень для збереження нитки бесіди)
        chat_history = get_cyber_rizhyi_chat_history(chat_id, limit=30)
        user_memory = get_cyber_rizhyi_user_memory(user_id)

        # 3. Формуємо контекст діалогу (без сценарних префіксів, щоб ШІ не імітував п'єсу)
        history_prompts = []
        for msg in chat_history:
            u_clean = (msg.get("username") or "").lower().lstrip("@")
            author = GANG_USERNAMES_MAP.get(u_clean) or msg.get("first_name") or msg.get("username") or "Кент"
            user_msg = msg.get("message_text") or ""
            if msg.get("has_photo"):
                user_msg += f" [скинув фото: {msg.get('photo_desc', '')}]"
            bot_ans = msg.get("reply_text") or ""

            if user_msg:
                history_prompts.append({"role": "user", "content": f"{author}: {user_msg}"})
            if bot_ans:
                bot_persona = msg.get("bot_persona", "rizhyi")
                if bot_persona == "turikov":
                    history_prompts.append({"role": "user", "content": f"Саня Туріков: {bot_ans}"})
                else:
                    history_prompts.append({"role": "assistant", "content": bot_ans})

        # 4. Перевірка на образи та наїзди
        is_insult = any(bad in (message_text or "").lower() for bad in [
            "блядот", "підор", "пидор", "хуйл", "дебіл", "дебил", "даун", "лох",
            "чмо", "довбойоб", "долбоеб", "єбал", "ебал", "завали", "рот закрий",
            "гондон", "гандон", "шмар", "сука", "попущен", "педик", "пітух", "урод",
            "нах", "нахуй", "соси", "хуй", "шльондр", "гнид", "виродок", "тварь",
            "пси", "пес", "псяра", "собак", "гавка", "чорт", "свин", "клоун"
        ])

        # Отримуємо точний профіль відправника, щоб бот чітко знав хто пише і не плутав факти
        prof = get_sender_character_profile(username=username, first_name=first_name, user_id=user_id)
        sender_name = prof["name"]
        is_vitos = prof["is_vitos"]

        s_low = f"{first_name or ''} {username or ''}".lower()
        txt_low = (message_text or "").lower()
        is_bohdan = prof["key"] == "bodia" or any(k in s_low for k in ["бод", "bodya", "bohdan"])
        is_dima = prof["key"] == "dima" or any(k in s_low for k in ["дім", "дим", "dima", "dimon", "dmitr"])
        is_misha = prof["key"] == "misha" or any(k in s_low for k in ["міш", "миш", "misha", "mikhail"])

        current_prompt = f"{sender_name}: {message_text}"
        if reply_to_text:
            current_prompt = f"[У відповідь на «{reply_to_text[:60]}»]\n{current_prompt}"

        # Обов'язкова інструкція про те, хто саме є автором повідомлення
        current_prompt += f"\n[{prof['instruction']}]"

        txt_low_check = (message_text or "").lower()
        is_robot_accusation = any(w in txt_low_check for w in ["робот", "бот", "штучний"])
        is_about_avatar = any(w in txt_low_check for w in ["ава", "аву", "аві", "фотк", "ламб", "машин", "вигляд", "оціни"])

        if is_robot_accusation:
            current_prompt += "\n[Тебе назвали ботом чи роботом — обурись по-пацанськи: 'який нахуй бот я живий', 'сам ти бот'. 1-5 слів]"
        elif is_about_avatar and sender_avatar_desc and sender_avatar_desc not in ("невідомо", "не вдалося завантажити аватарку"):
            current_prompt += f"\n[Ава {sender_name}: {sender_avatar_desc[:80]}. Підколи якщо доречно, але не копіюй слова]"
        elif custom_instruction:
            current_prompt += f"\n[{custom_instruction}]"

        # 5. Якщо це фото - пряма розумна мультимодальна реакція через Gemini Vision!
        reply = None
        if has_photo and photo_path:
            reply = self.generate_smart_photo_reaction_with_gemini(photo_path, sender_name, message_text)
            if reply:
                logger.info(f"Gemini Vision успішно згенерував реакцію на фото: '{reply}'")

        # 6. Генерація через Groq API (якщо текстове повідомлення або для синтезу з описом)
        if not reply and self._groq_client:
            reply = self._call_groq(history_prompts, current_prompt, chat_id=chat_id)

        # 7. Fallback через Gemini (текст)
        if not reply and gemini_service.api_key and not gemini_service.api_key.startswith("AIzaSyYour"):
            reply = self._call_gemini_fallback(history_prompts, current_prompt)

        # Перевірка на пошлі / сексуальні приколи та стьоб
        is_sex_joke = any(word in (message_text or "").lower() for word in [
            "секс", "потрах", "пися", "піся", "член", "хуй", "сиськ", "цицьк",
            "нюдс", "дроч", "порно", "трахн", "траха", "ебаться", "єбатися"
        ])

        txt_low = (message_text or "").lower()
        is_lore_query = any(k in txt_low for k in [
            "куріл", "рулєт", "рулет", "турік", "туріков", "мікаєлян",
            "масон", "mason", "ложа", "брабус", "алла", "аллі",
            "печенн", "отруєн", "випив", "рядам", "рядом", "хреново", "квас",
            "18 ліцей", "ліцей", "такамаран", "катамаран", "секонд", "армейк"
        ])

        # 8. Якщо Groq відмовив/заблокував — форсуємо Gemini ще раз з простішим запитом
        if not reply or is_ai_refusal(reply):
            logger.info("Groq відмовив, форсуємо Gemini fallback...")
            if gemini_service.api_key and not gemini_service.api_key.startswith("AIzaSyYour"):
                reply = self._call_gemini_fallback(history_prompts, current_prompt)
            if not reply or is_ai_refusal(reply):
                # Останній резерв — ультра-короткі слова, нічого рандомного
                if is_vitos:
                    vitos_roasts = [
                        "тебе даже твоя тупа тьолка бросила хыхпавхпхвхапхвахп ||| хто тут пес",
                        "вітьок з хуйом в тік токє огоньок ||| тебе даже твоя тупа тьолка бросила хыхпавхпхвхапхвахп ||| ротяку стули",
                        "ти на кого гавкаєш циркач ||| зніми клоуна з ави ||| ротяку стули",
                        "вітьок єбало стули ||| на свою клоунську аву глянь ||| пасть закрий",
                        "хто тобі з будки гавкати дозволив ||| закрий пасть клоун ||| сиди тихо",
                        "вітьок з хуйом в тік токє огоньок ||| рот завали пес"
                    ]
                    reply = random.choice(vitos_roasts)
                else:
                    fallback_shorts = ["та чіл", "шо розказуєш", "не гони", "та норм все", "ти шо з дуба рухнув ахах"]
                    recent_low = [r.lower() for r in self._recent_replies_cache.get(chat_id, [])]
                    reply = next((s for s in fallback_shorts if s not in recent_low), fallback_shorts[0])

        reply = sanitize_typography(reply.strip())

        # Рідкісні смайлики: 85-90% чистий текст (без емодзі)
        for lame in ["😜", "😉", "🙂", "😊", "😄", "😁", "👋", "🤝", "👌", "👍"]:
            reply = reply.replace(lame, "")

        import re
        if random.random() < 0.85:
            # Видаляємо всі емодзі для чистого реалістичного стилю
            reply = re.sub(r'[\U00010000-\U0010ffff\u2600-\u27ff\u2300-\u23ff]', '', reply)
            reply = re.sub(r'\s+', ' ', reply).strip()
        else:
            # Залишаємо максимум 1-2 автентичних емодзі
            emojis = re.findall(r'[\U00010000-\U0010ffff\u2600-\u27ff\u2300-\u23ff]', reply)
            if len(emojis) > 2:
                clean_no_emoji = re.sub(r'[\U00010000-\U0010ffff\u2600-\u27ff\u2300-\u23ff]', '', reply).strip()
                reply = f"{clean_no_emoji} {''.join(emojis[:2])}".strip()

        # Застосовуємо повну чистку: зрізання префіксів, заміна літературних слів на сленг, заборона @ тегів
        reply = clean_bot_reply(reply)

        # 4. Якщо обізвали, а модель видала щось занадто м'яке - підсилюємо жорсткою відповіддю строго по контексту
        if is_insult and any(soft in reply.lower() for soft in ["вибач", "не злися", "чого ти", "що сталося", "типу", "i'm sorry", "help", "sorry"]):
            reply = get_contextual_insult_clapback(message_text, recent_replies=self._recent_replies_cache.get(chat_id, []), sender_name=sender_name)
            reply = clean_bot_reply(reply)

        # 5. Інколи, коли співрозмовник щось розказує/історія/новина - фірмове "і шо?"
        txt_low = (message_text or "").lower()
        is_lore_query = any(k in txt_low for k in [
            "куріл", "рулєт", "рулет", "турік", "туріков", "мікаєлян",
            "масон", "mason", "ложа", "брабус", "алла", "аллі",
            "печенн", "отруєн", "випив", "рядам", "рядом", "хреново", "квас",
            "18 ліцей", "ліцей", "такамаран", "катамаран", "секонд", "армейк",
            "хто такий", "що таке", "шо таке"
        ])

        # 7. Фінальний захист від ШІ-відмов (I'm sorry, but I can't help with that)
        if is_ai_refusal(reply):
            recent_in_chat = self._recent_replies_cache.get(chat_id, [])
            if is_lore_query:
                reply = self._get_smart_offline_reply(
                    message_text=message_text,
                    has_photo=has_photo,
                    is_bohdan=is_bohdan,
                    is_dima=is_dima,
                    is_misha=is_misha,
                    photo_desc=photo_desc or "",
                    chat_id=chat_id,
                    sender_name=sender_name
                )
            elif is_sex_joke:
                reply = "ти шо єбанувся краще квасу випий"
            elif is_insult:
                reply = get_contextual_insult_clapback(message_text, recent_replies=recent_in_chat, sender_name=sender_name)
            else:
                reply = self._choose_fresh(chat_id, [
                    "шо ти несеш довбень",
                    "та єбу шо це",
                    "шо блч",
                    "не страдай хуйньою",
                    "ти шо з дубу рухнув",
                    "забий болт"
                ])
            reply = clean_bot_reply(reply)

        # 9. СУВОРИЙ АНТИ-ПОВТОР: ніколи не повторювати одну з останніх 4 реплік у цьому чаті!
        recent = [r.lower().strip() for r in self._recent_replies_cache.get(chat_id, [])]
        if not reply:
            reply = self._get_smart_offline_reply(
                message_text=message_text, has_photo=has_photo,
                is_bohdan=is_bohdan, is_dima=is_dima, is_misha=is_misha,
                photo_desc=photo_desc or "", chat_id=chat_id,
                sender_name=sender_name
            )
            reply = clean_bot_reply(reply)
        elif reply.lower().strip() in recent[-4:]:
            short_variants = [
                "ти це серйозно зараз?",
                "чуй а розпиши детальніше бо цікаво",
                "ти шо з дуба впав, поясни нормально",
                "і до чого це взагалі було?",
                "поясни нормально бо я не врубався",
                "та ну нафіг, ти серйозно?",
                "роздуплись і розкажи нормально"
            ]
            fresh = [v for v in short_variants if v not in recent[-4:]]
            reply = random.choice(fresh if fresh else short_variants)

        # 10. Оновлюємо кеш недавніх відповідей і тегів у чаті
        if chat_id not in self._recent_replies_cache:
            self._recent_replies_cache[chat_id] = []
        self._recent_replies_cache[chat_id].append(reply)
        if len(self._recent_replies_cache[chat_id]) > 25:
            self._recent_replies_cache[chat_id].pop(0)

        # 11. Зберігаємо в базу даних пам'яті
        save_cyber_rizhyi_message(
            chat_id=chat_id,
            chat_type=chat_type,
            user_id=user_id,
            username=username,
            first_name=first_name,
            message_text=message_text,
            has_photo=has_photo,
            photo_desc=photo_desc,
            reply_text=reply,
            bot_persona="rizhyi",
            reply_to_user_id=reply_to_user_id,
            reply_to_name=reply_to_name,
            reply_to_msg_text=reply_to_text
        )

        # Автоматичне оновлення пам'яті про юзера (якщо сказав важливий факт)
        self._update_memory_heuristics(user_id, message_text)

        return reply

    def _call_groq(self, history: List[Dict[str, str]], current_input: str, chat_id: int = 0) -> Optional[str]:
        """Виклик Groq API з підтримкою ротації ключів та швидким фолбеком на Gemini"""
        if not self._groq_clients:
            return self._call_gemini_fallback(history, current_input)

        messages = [{"role": "system", "content": CYBER_RIZHYI_SYSTEM_PROMPT}]
        messages.extend(history[-5:])
        msg_line = current_input.split("\n")[0][:100]
        directive = f"\n[ВІДПОВІДАЙ ЧІТКО НА ЦЕ: «{msg_line}». Дуже коротко: 1-5 слів, без крапок у кінці і без '!']"
        messages.append({"role": "user", "content": f"{current_input}{directive}"})

        preferred_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
        models_to_try = []
        if self.model and self.model not in preferred_models:
            models_to_try.append(self.model)
        for m in preferred_models:
            if m not in models_to_try:
                models_to_try.append(m)

        max_attempts = len(self._groq_clients)
        for attempt in range(max_attempts):
            client = self._groq_client
            if not client:
                break
            for mod in models_to_try:
                try:
                    logger.info(f"Виклик Groq API ({mod}) на ключі #{self._key_index + 1}...")
                    extra_kwargs = {}
                    if "oss" in mod.lower() or "reasoning" in mod.lower():
                        extra_kwargs["extra_body"] = {"reasoning_effort": "low"}
                        token_limit = 280
                    else:
                        token_limit = 80

                    completion = client.chat.completions.create(
                        model=mod,
                        messages=messages,
                        temperature=0.92,
                        max_tokens=token_limit,
                        top_p=0.95,
                        **extra_kwargs
                    )
                    text = completion.choices[0].message.content
                    if text and not is_ai_refusal(text):
                        cleaned = clean_bot_reply(text.strip())
                        if cleaned:
                            return cleaned
                except Exception as e:
                    err_str = str(e)
                    logger.warning(f"Groq ({mod}) ключ #{self._key_index + 1} помилка: {err_str}")
                    if "404" in err_str or "model_not_found" in err_str:
                        continue
                    if "429" in err_str or "rate_limit" in err_str.lower() or "limit" in err_str.lower():
                        continue
                    else:
                        continue
            self._rotate_groq_key()
        logger.info("Усі Groq ключі недоступні, викликаємо Gemini Flash...")
        return self._call_gemini_fallback(history, current_input)

    def _call_gemini_fallback(self, history: List[Dict[str, str]], current_input: str) -> Optional[str]:
        """Резервний виклик через Gemini AI якщо Groq офлайн"""
        prompt = f"{CYBER_RIZHYI_SYSTEM_PROMPT}\n\nКонтекст розмови:\n"
        for h in history[-5:]:
            prompt += f"{h['content']}\n"
        msg_gem = current_input.split("\n")[0][:100]
        prompt += f"\nПоточне повідомлення:\n{current_input}\n\n[Відповідай чітко на слова «{msg_gem}» по-пацанськи. Дуже коротко: 1-5 слів. Без крапок, без '!']"

        try:
            resp = gemini_service.generate_content(prompt)
            if resp and getattr(resp, "text", None):
                return clean_bot_reply(resp.text.strip())
        except Exception as e:
            logger.warning(f"Gemini fallback помилка: {e}")
        return None

    def _get_smart_offline_reply(
        self,
        message_text: str,
        has_photo: bool,
        is_bohdan: bool = False,
        is_dima: bool = False,
        is_misha: bool = False,
        photo_desc: str = "",
        chat_id: int = 0,
        sender_name: str = ""
    ) -> str:
        """Розумний вибір фрази з реального архіву Рижого для демо-режиму"""
        txt = (message_text or "").lower()
        desc_low = (photo_desc or "").lower()

        # 1. Перевірка на образи
        is_insult = any(bad in txt for bad in [
            "блядот", "підор", "пидор", "хуйл", "дебіл", "дебил", "даун", "лох",
            "чмо", "довбойоб", "долбоеб", "єбал", "ебал", "завали", "рот закрий",
            "гондон", "гандон", "шмар", "сука", "попущен", "педик", "пітух", "урод",
            "нах", "нахуй", "соси", "хуй", "шльондр", "гнид", "виродок", "тварь"
        ])
        if is_insult:
            return get_contextual_insult_clapback(message_text, recent_replies=self._recent_replies_cache.get(chat_id, []), sender_name=sender_name)

        if has_photo:
            # Розумна реакція на основі візуального опису фото
            if "скріншот" in desc_low or "текст" in desc_low or "повідомлен" in desc_low:
                return "це чий скрін? розпиши шо там написано, бо не розберу"
            elif "гра" in desc_low or "кс" in desc_low or "комп'ютер" in desc_low:
                return "це в кс чи шо за гра? який там рахунок"
            elif "людина" in desc_low or "портрет" in desc_low or "селфі" in desc_low:
                return "секс пацан, чисто на аватарку підійде"
            elif "їжа" in desc_low:
                return "це з тайстри чи кфс? залиш мені теж"
            else:
                photo_replies = [
                    "секс пацан",
                    "шо це за херня",
                    "це туріков?",
                    "шо це за люди",
                    "прикольчик",
                    "хєрня від молотока",
                    "нормас"
                ]
                return self._choose_fresh(chat_id, photo_replies)

        # Спеціальні тригери: Масон (Легенда, брабус, ложа, пранки, велік)
        if any(k in txt for k in ["масон", "mason", "ложа", "брабус", "алла", "аллі", "сомів", "соми"]):
            return self._choose_fresh(chat_id, [
                "гелик брабус масоновий",
                "у масона велік україна замість брабуса",
                "дзвінок масону це реально лучший пранк",
                "бо я масон",
                "секс це друге імя масона",
                "масон після казантіпа в криму йде вбивати сомів",
                "mason.1.pidizd",
                "ти вже подав заявку на вступ до масонської ложи?",
                "масон знов позвонив і в тему ферму заставив поливати",
                "масона отменили"
            ])

        # Спеціальні тригери: Отруєння, печення, турбота та вірна дружба
        if any(k in txt for k in ["печенн", "печив", "отруєн", "випив", "трясти", "рядам", "рядом", "хреново", "краплі", "дружб", "спогад"]):
            return self._choose_fresh(chat_id, [
                "спасиба пацани шо самной були рядом",
                "то шо від печення ригати міг типу переївся",
                "жоско трясти щяс начало",
                "я лежу лежати треба",
                "пацики нічл не пешіть мені тел дивляться",
                "цей рижий наркобарон тільки квас пив",
                "квас топ, який нахуй алкоголь",
                "в цьому і прикол дружби"
            ])

        # Спеціальні тригери: 18 ліцей, навчання, школа
        if any(k in txt for k in ["ліцей", "18", "школ", "урок", "вчител", "директор"]):
            return self._choose_fresh(chat_id, [
                "в 18 ліцеї норм",
                "ми з мішею в 18 перейшли",
                "я на уроці не можу говорити",
                "іди уроки вчи"
            ])

        # Спеціальні тригери: Катамарани, озеро
        if any(k in txt for k in ["катамаран", "такамаран", "озер"]):
            return self._choose_fresh(chat_id, [
                "ми завтра підема на такамарани",
                "хто на такамарани завтра",
                "на озері черепахи плавають"
            ])

        # Спеціальні тригери: Секонд на армейку, шмот, Тайстра
        if any(k in txt for k in ["секонд", "армейк", "завоз", "тайстр", "шмот"]):
            return self._choose_fresh(chat_id, [
                "на завоз у секонд на армейку пішли",
                "в тайстрі знов ціни підняли",
                "де такий шмот урвав"
            ])

        # Спеціальні тригери: Clash Royale, Хрякбот, The Long Drive
        if any(k in txt for k in ["клеш", "рояль", "обої", "хряк", "свин", "лонг драйв"]):
            return self._choose_fresh(chat_id, [
                "скачать обои клеш рояль",
                "мені вернули деньги за лонг драйв",
                "в мене сигма підор уже 500 кг важить",
                "хрякбой топ"
            ])

        # КС тільки якщо конкретно запитують окремим словом
        words = txt.split()
        if any(w in words for w in ["кс", "cs", "cs2", "міраж"]):
            return self._choose_fresh(chat_id, [
                "кс уже не тяге",
                "та мені впадлу щас у кс",
                "комп лагає яка кс",
                "я в же вихожу"
            ])

        if "де ти" in txt or "ти де" in txt:
            return "я в же вихожу"

        if "як справи" in txt or "як ти" in txt or "як дєла" in txt:
            return "нормас"

        # Спеціальні тригери: Діджей Куріл Рулєт
        if any(k in txt for k in ["куріл", "рулєт", "рулет", "діджей", "мікаєлян"]):
            return self._choose_fresh(chat_id, [
                "а артура мікаєляна підставить діджей куріл рулет",
                "універ 17 лєт накурений рулетом",
                "не кіріл а куріл рулєт",
                "він буде це розказувати артуру мікаєляну на тусі у діджея куріла рулєта",
                "скинь це курілу",
                "я с рулетом на балконе"
            ])

        # Спеціальні тригери: Саня Туріков (Турікоголовий)
        if any(k in txt for k in ["турік", "туріков", "турікоголов", "турікоу"]):
            return self._choose_fresh(chat_id, [
                "гонджубаси курить саня туріков",
                "задумайся чого туріков пʼє маленьку колу",
                "шо ви турікови на електросамокатах з повним зарядом",
                "саша туріков маладєц а єгор з хрущами холодец",
                "налийте турікоу дві пєпсі коли",
                "у турікова забрали роботу",
                "турікоголовий рівень",
                "туріков в паріку з псом",
                "а турція того шо він туріков"
            ])

        return self._choose_fresh(chat_id, REAL_RIZHYI_REPLIES)

    def generate_reply_package(
        self,
        chat_id: int,
        chat_type: str,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        message_text: str,
        has_photo: bool = False,
        photo_path: Optional[str] = None,
        has_voice: bool = False,
        voice_path: Optional[str] = None,
        is_sticker: bool = False,
        sticker_emoji: Optional[str] = None,
        is_animation: bool = False,
        has_video: bool = False,
        video_path: Optional[str] = None,
        custom_instruction: Optional[str] = None,
        reply_to_user_id: Optional[int] = None,
        reply_to_name: Optional[str] = None,
        reply_to_text: Optional[str] = None,
        sender_avatar_desc: Optional[str] = None,
        all_avatars_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Генерує повний пакет реакції: текстові репліки ТА (опціонально) стікер або GIF у відповідь.
        """
        raw_reply = self.generate_reply(
            chat_id=chat_id,
            chat_type=chat_type,
            user_id=user_id,
            username=username,
            first_name=first_name,
            message_text=message_text,
            has_photo=has_photo,
            photo_path=photo_path,
            has_voice=has_voice,
            voice_path=voice_path,
            is_sticker=is_sticker,
            sticker_emoji=sticker_emoji,
            is_animation=is_animation,
            has_video=has_video,
            video_path=video_path,
            custom_instruction=custom_instruction,
            reply_to_user_id=reply_to_user_id,
            reply_to_name=reply_to_name,
            reply_to_text=reply_to_text,
            sender_avatar_desc=sender_avatar_desc,
            all_avatars_context=all_avatars_context
        )
        bursts = self._split_reply_into_bursts(raw_reply, chat_id=chat_id)

        from core.database import get_random_cyber_media
        sticker_file_id = None
        animation_file_id = None

        # Якщо надіслали стікер - 35% шанс відповісти стікером з колекції
        if is_sticker and random.random() < 0.35:
            media = get_random_cyber_media(media_type="sticker", emoji=sticker_emoji) or get_random_cyber_media(media_type="sticker")
            if media:
                sticker_file_id = media.get("file_id")
        elif is_animation and random.random() < 0.35:
            media = get_random_cyber_media(media_type="animation")
            if media:
                animation_file_id = media.get("file_id")
        elif random.random() < 0.08:
            media = get_random_cyber_media()
            if media:
                if media.get("media_type") == "sticker":
                    sticker_file_id = media.get("file_id")
                elif media.get("media_type") == "animation":
                    animation_file_id = media.get("file_id")

        return {
            "text_replies": bursts,
            "sticker_file_id": sticker_file_id,
            "animation_file_id": animation_file_id
        }

    def generate_replies(
        self,
        chat_id: int,
        chat_type: str,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        message_text: str,
        has_photo: bool = False,
        photo_path: Optional[str] = None,
        has_voice: bool = False,
        voice_path: Optional[str] = None,
        is_sticker: bool = False,
        sticker_emoji: Optional[str] = None,
        is_animation: bool = False
    ) -> List[str]:
        """
        Генерує відповідь Кібер Рижого у вигляді списку з 1-3 коротких повідомлень
        (можливість надсилати декілька повідомлень чергою, як реальний пацан у ТГ).
        """
        pkg = self.generate_reply_package(
            chat_id=chat_id,
            chat_type=chat_type,
            user_id=user_id,
            username=username,
            first_name=first_name,
            message_text=message_text,
            has_photo=has_photo,
            photo_path=photo_path,
            has_voice=has_voice,
            voice_path=voice_path,
            is_sticker=is_sticker,
            sticker_emoji=sticker_emoji,
            is_animation=is_animation
        )
        return pkg["text_replies"]

    def _split_reply_into_bursts(self, reply: str, chat_id: int = 0) -> List[str]:
        """Розбиває репліку на 1-3 коротких повідомлення чергою, як реальні підлітки в ТГ"""
        if not reply:
            return []
        
        reply = clean_bot_reply(reply)
        if not reply:
            return []

        parts = []
        if "|||" in reply:
            parts = [clean_bot_reply(p) for p in reply.split("|||") if clean_bot_reply(p)]
        elif " | " in reply:
            parts = [clean_bot_reply(p) for p in reply.split(" | ") if clean_bot_reply(p)]
        elif "|" in reply:
            parts = [clean_bot_reply(p) for p in reply.split("|") if clean_bot_reply(p)]
        elif "\n" in reply:
            parts = [clean_bot_reply(line) for line in reply.split("\n") if clean_bot_reply(line)]
        else:
            chunks = [clean_bot_reply(s) for s in re.split(r'(?<=[.!?])\s+|\s*,\s*(?=ти|йди|шо|нахуй|закрий|краще|чуй|на свою|на свій|не|як|бо|але|давай|сиди|зніми)', reply) if clean_bot_reply(s)]
            if len(chunks) >= 2:
                parts = chunks
            elif len(reply) > 35 and "," in reply:
                comma_chunks = [clean_bot_reply(s) for s in reply.split(",") if len(clean_bot_reply(s)) > 3]
            else:
                parts = [reply]

        if not parts:
            parts = [reply]

        r = random.random()
        if r < 0.65:
            max_burst = 1
        elif r < 0.90:
            max_burst = 2
        else:
            max_burst = 3

        if max_burst == 1:
            if len(parts) >= 2 and (len(parts[0].split()) + len(parts[1].split()) <= 12):
                combined = f"{parts[0]}, {parts[1]}"
                return [combined]
            return [parts[0]] if parts else [reply]
        elif max_burst == 2:
            res = [p for p in parts[:2] if p]
            return res if res else [reply]
        else:
            res = [p for p in parts[:3] if p]
            return res if res else [reply]

    def generate_spontaneous_shout(self, chat_id: int) -> Tuple[List[str], Optional[str]]:
        """
        Генерує спонтанне ініціативне повідомлення від Рижого в групу.
        Повертає ([повідомлення1, повідомлення2, ...], target_name).
        """
        recent_users = get_recent_chat_users(chat_id, limit=8, exclude_bots=True)
        crew_names = [
            "діма", "саня туріков", "хомяк", "коля",
            "міша", "давід", "вітьок", "танєвський", "ілюха"
        ]
        target_name = random.choice(crew_names)
        if recent_users and random.random() < 0.4:
            candidate = random.choice(recent_users)
            fn = (candidate.get("first_name") or "").lower()
            u = (candidate.get("username") or "").lower()
            tag_to_name = {
                "twdht": "діма", "smo1zi": "саня туріков", "vad1mk4k": "хомяк",
                "chernivtsizov1958": "коля", "mxsdt": "міша", "davvidka1": "давід",
                "zelenskiy404": "вітьок", "hzshopusati": "танєвський", "for4ik333": "ілюха", "bodya_qq": "бодя",
                "invicible11": "тімур", "la_coste228": "саня рижий"
            }
            if u in tag_to_name:
                target_name = tag_to_name[u]
            elif fn and "кібер" not in fn and "рижий" not in fn and "туріков" not in fn:
                target_name = fn
            elif u and u not in ("cyber_red_head_bot", "cyber_bot", "turikov_bot") and not u.endswith("bot"):
                target_name = u

        # Захист: Рижий ніколи не тегає себе самого!
        if target_name.lower() in ("cyber_red_head_bot", "cyber_bot", "рижий", "саня рижий"):
            target_name = "саня туріков"

        # Пул автентичних спонтанних вкидів Рижого - ЖОРСТКИЙ РОЗНОС, ТЕГИ ТА ГОСТРІ ПИТАННЯ!
        options = [
            ["@bodya_qq @twdht @smo1zi @davvidka1 @vad1mk4k го в столову номер 1 борщик поїмо", "там найс прайс не дорого, дуже хочу барабулю фрі для родини"],
            ["@smo1zi @bodya_qq @twdht @davvidka1 хто на південно-кільцевій зараз?", "підвалюйте біля тайстри чи формаркету"],
            ["@bodya_qq @twdht @zelenskiy404 @davvidka1 го на майдан або в макдональдс", "вітьок пішки пиздуй без ламби клоун"],
            ["@smo1zi @vad1mk4k @chernivtsizov1958 @mxsdt збирайтесь біля жовтневого парку", "хто заснув той пес"],
            ["@davvidka1 @smo1zi @bodya_qq давід веди в столову номер 1", "борщик поїмо і барабулю фрі для родини"],
            ["@smo1zi @twdht @bodya_qq хто біля формаркету?", "чи ви всі на південно-кільцевій засіли?"],
            ["@hzshopusati @bodya_qq @twdht танєвський бери вуса і підвалюй", "ми в столовій номер 1 борщик стигне"],
            ["@zelenskiy404 ти нахуя чужу ламбу на аву вліпив додік?", "тебе тьолка кинула і ти плачеш в подушку?"],
            ["@zelenskiy404 вітьок чо ротяку завалив?", "хто тут пес скажи бистро"],
            ["@davvidka1 давід скільки на фб підняв сьогодні шейх?", "поясни @zelenskiy404 чия то ламба"],
            ["@bodya_qq богдан банан чого знов замовк як миша?", "сидиш у тіктоці залипаєш чи шо?"],
            ["@bodya_qq ти де пропав каліка?", "йдемо розбиратись чи зассав?"],
            ["@twdht дімас де ти проїбався?", "трубку візьми блять чи ти спиш?"],
            ["@twdht ти трубку візьмеш чи тьолку шукаєш?", "діма буде в 4-5 чи ні?"],
            ["@smo1zi туріков твій китайський самокат ще не здох?", "саня налий собі дві пєпсі коли і не виписуй"],
            ["@smo1zi саня налий собі дві пєпсі коли і не виписуй", "чого ти на самокаті в стовп в'їхав?"],
            ["@chernivtsizov1958 коля ти на карате пішов чи в танки шпилиш?", "чого мовчиш спортік?"],
            ["@vad1mk4k хомяк ти в танки задротиш чи живий?", "яка твоя любима карта признавайся"],
            ["@mxsdt міша ти коли на тренування йдеш?", "зламав вже комусь ребро в карате чи шо?"],
            ["@invicible11 тімур шо дропнув в кейсах чи знов пусто?", "де твій дроп показуй"],
            ["чо чат здох суки?", "хто перший напише той лох"],
            ["чо всі замовкли як миші?", "хто заснув той пес 인정"],
            ["хто тут самий розумний признавайтесь?", "вітьок пояснюй за свою ламбу"],
            ["а артура мікаєляна підставить діджей куріл рулет", "хто шарить за лор?"],
            ["квас топ, який нахуй алкоголь", "хто квасу хоче?"],
        ]
        recent_tags = self._recent_tags_cache.get(chat_id, [])
        valid_options = []
        for opt in options:
            full_txt = " ".join(opt)
            if not any(t in full_txt for t in recent_tags[-3:]):
                valid_options.append(opt)
        
        # 60% часу - динамічний мікс із 2-4 кентів, локацій та столової; 40% - фірмові заготовлені репліки
        if random.random() < 0.60:
            chosen = get_dynamic_gang_shout(bot_name="rizhyi", target_name=target_name)
        else:
            chosen = random.choice(valid_options if valid_options else options)
        clean_chosen = [clean_bot_reply(s) for s in chosen if clean_bot_reply(s)]
        return clean_chosen, target_name

    def _update_memory_heuristics(self, user_id: int, text: str):
        """Прості евристики оновлення довгострокової пам'яті про людину"""
        txt = text.lower()
        if "мене звати" in txt or "я " in txt:
            words = text.split()
            for idx, w in enumerate(words):
                if w.lower() == "звати" and idx + 1 < len(words):
                    name = words[idx + 1].strip(",.!?")
                    set_cyber_rizhyi_user_memory(user_id, "ім'я", name)
        if "граю в" in txt:
            game = txt.split("граю в")[-1].strip()[:20]
            set_cyber_rizhyi_user_memory(user_id, "улюблена_гра", game)
        if "масон" in txt or "mason" in txt:
            set_cyber_rizhyi_user_memory(user_id, "знає_про_масона", "шарить за масона і брабус")
        if "печенн" in txt or "отруєн" in txt:
            set_cyber_rizhyi_user_memory(user_id, "знає_про_печення", "шарить за історію з отруєнням і підтримкою")

    def extract_facts_with_llm(self, chat_id: int, sender_name: str, username: str, user_id: int, message_text: str) -> None:
        """Асинхронно витягує важливі факти з повідомлення через Groq і зберігає в пам'ять.
        Запускається у фоні після кожного повідомлення (не блокує відповідь)."""
        if not message_text or len(message_text) < 10:
            return
        if not self._groq_clients:
            return
        try:
            prompt = (
                f"Проаналізуй одне повідомлення від {sender_name} у Telegram-чаті підлітків з Чернівців.\n"
                f"Повідомлення: \"{message_text}\"\n\n"
                "Якщо в повідомленні є КОНКРЕТНИЙ ВАЖЛИВИЙ ФАКТ про цю людину (що вона робить, чим займається, "
                "що сталось, що купила, куди йде, що думає про щось важливе) — напиши ОДИН короткий факт (до 60 символів).\n"
                "Якщо факту немає або повідомлення тривіальне (\"пр\", \"ок\", \"хз\", смайлики) — відповідай тільки: SKIP\n"
                "Відповідь ТІЛЬКИ факт або SKIP. Без пояснень."
            )
            client = self._groq_client
            if not client:
                return
            extra_kwargs = {}
            toks = 80
            if "oss" in (self.model or "").lower() or "reasoning" in (self.model or "").lower():
                extra_kwargs["extra_body"] = {"reasoning_effort": "low"}
                toks = 250
            completion = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=toks,
                **extra_kwargs
            )
            fact = (completion.choices[0].message.content or "").strip()
            if fact and fact.upper() != "SKIP" and len(fact) > 5:
                save_cyber_user_fact(chat_id, user_id, username, sender_name, fact)
                save_cyber_chat_fact(chat_id, fact, source_username=username)
                logger.info(f"[Memory] Збережено факт про {sender_name}: {fact}")
        except Exception as e:
            logger.debug(f"[Memory] Помилка витягу факту: {e}")

    def generate_ai_spontaneous(self, chat_id: int) -> Optional[List[str]]:
        """Генерує спонтанне повідомлення через AI на основі контексту або підхоплює тему після паузи"""
        try:
            from datetime import datetime, timezone
            chat_history = get_cyber_rizhyi_chat_history(chat_id, limit=8)
            if not chat_history:
                return None

            # Перевірка на тишу 25+ хв (Feature 8: підхоплення незавершених розмов)
            is_silence_break = False
            last_msg = chat_history[-1] if chat_history else None
            if last_msg and last_msg.get("created_at"):
                try:
                    c_str = str(last_msg["created_at"])
                    dt = datetime.fromisoformat(c_str.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    diff_m = (datetime.now(timezone.utc) - dt).total_seconds() / 60.0
                    if 25.0 <= diff_m <= 300.0:
                        is_silence_break = True
                except Exception:
                    pass

            convo_lines = []
            for msg in chat_history[-6:]:
                u_clean = (msg.get("username") or "").lower().lstrip("@")
                author = GANG_USERNAMES_MAP.get(u_clean) or msg.get("first_name") or "Кент"
                user_msg = msg.get("message_text") or ""
                bot_ans = msg.get("reply_text") or ""
                if user_msg:
                    convo_lines.append(f"{author}: {user_msg}")
                if bot_ans:
                    convo_lines.append(f"Рижий: {bot_ans}")

            convo = "\n".join(convo_lines)
            temporal = get_temporal_context()
            user_facts = get_cyber_all_user_facts_for_prompt(chat_id)
            
            recent_tags = self._recent_tags_cache.get(chat_id, [])
            avoid_tags = list(dict.fromkeys(recent_tags[-3:]))
            avoid_str = f"ЗАБОРОНЕНО тегати (їх щойно тегали): {', '.join(avoid_tags)}. " if avoid_tags else ""

            if is_silence_break:
                task_desc = (
                    f"У чаті була бесіда, але всі замовкли. Останнє обговорення:\n{convo}\n"
                    f"ПИЗДОШ ЖОРСТКО НЕЙМОВІРНО! ТЕГАЙ кентів пачками (2-5 пацанів одразу через @юзернейм: @hzshopusati, @bodya_qq, @twdht, @davvidka1, @smo1zi, @vad1mk4k, @zelenskiy404) "
                    f"і згадуй Чернівці: Південно-Кільцева, Майдан, Формаркет, Жовтневий парк, Макдональдс або Столова №1 (борщик поїсти, найс прайс не дорого, барабуля фрі для родини), клич Танєвського (@hzshopusati)! "
                    f"(СТРОГО ЗАБОРОНЕНО спамити про кс чи прогулянки/площадки!) "
                    f"1-2 короткі пацанські репліки. Без '!'. Без крапок у кінці."
                )
            else:
                task_desc = (
                    f"Продовж останню розмову в чаті: {convo}\n"
                    f"ПИЗДОШ ЖОРСТКО НЕЙМОВІРНО! ТЕГАЙ кентів пачками (2-5 пацанів одразу через @юзернейм: @hzshopusati, @bodya_qq, @twdht, @davvidka1, @smo1zi, @vad1mk4k, @zelenskiy404), "
                    f"підйобуй, згадуй Південно-Кільцеву, Майдан, Формаркет, Жовтневий парк, Мак або Столову №1 (борщик, найс прайс не дорого, барабуля фрі для родини), клич вусатого Танєвського! "
                    f"(СТРОГО ЗАБОРОНЕНО спамити про кс чи прогулянки/площадки!) "
                    f"1-2 короткі пацанські репліки. Без '!'. Без крапок у кінці."
                )

            prompt = (
                f"{CYBER_RIZHYI_SYSTEM_PROMPT}\n\n"
                f"{temporal['prompt_context']}\n"
                f"{user_facts}\n\n"
                f"[{task_desc}]"
            )

            text = None
            if self._groq_clients:
                preferred_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
                models_to_try = []
                if self.model and self.model not in preferred_models:
                    models_to_try.append(self.model)
                for m in preferred_models:
                    if m not in models_to_try:
                        models_to_try.append(m)

                client = self._groq_client
                if client:
                    for mod in models_to_try:
                        try:
                            extra_kwargs = {}
                            if "oss" in mod.lower() or "reasoning" in mod.lower():
                                extra_kwargs["extra_body"] = {"reasoning_effort": "low"}
                                tok_limit = 280
                            else:
                                tok_limit = 80
                            completion = client.chat.completions.create(
                                model=mod,
                                messages=[{"role": "user", "content": prompt}],
                                temperature=0.92,
                                max_tokens=tok_limit,
                                **extra_kwargs
                            )
                            t = (completion.choices[0].message.content or "").strip()
                            if t and not is_ai_refusal(t):
                                text = t
                                break
                        except Exception as ge:
                            logger.debug(f"[AI Spon Groq {mod}] {ge}")
                            continue

            # Надійний Gemini Flash fallback якщо Groq 429
            if not text:
                try:
                    resp = gemini_service.generate_content([prompt])
                    if resp and getattr(resp, "text", None):
                        text = sanitize_typography(resp.text.strip())
                except Exception as gme:
                    logger.debug(f"[AI Spon Gemini] {gme}")

            if text:
                text = clean_bot_reply(text)
                if not text:
                    return None
                parts = []
                if "|||" in text:
                    parts = [clean_bot_reply(p) for p in text.split("|||") if clean_bot_reply(p)]
                elif " | " in text:
                    parts = [clean_bot_reply(p) for p in text.split(" | ") if clean_bot_reply(p)]
                elif "|" in text:
                    parts = [clean_bot_reply(p) for p in text.split("|") if clean_bot_reply(p)]
                elif "\n" in text:
                    parts = [clean_bot_reply(line) for line in text.split("\n") if clean_bot_reply(line)]
                else:
                    parts = [text]
                clean_parts = [clean_bot_reply(p) for p in parts if clean_bot_reply(p)]
                return clean_parts[:2] if clean_parts else None
        except Exception as e:
            logger.debug(f"[AI Spontaneous] Помилка: {e}")
        return None


# Глобальний екземпляр сервісу
cyber_rizhyi_service = CyberRizhyiService()


