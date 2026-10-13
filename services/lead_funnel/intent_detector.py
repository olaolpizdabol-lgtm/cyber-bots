"""
🧠 Smart Comment Intent Detector & AI Auto-Responder (English)

Detects whether a user's comment is:
1. LEAD_MAGNET: Asking for the resource/prompts (via keywords like 'GPT' or natural request).
2. QUESTION_OR_CHAT: General comment, praise, or technical question -> generates a smart, charismatic English reply as Bohdan GPT.
3. SPAM: Irrelevant promo, links, scams, or gibberish.
"""
import re
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from services.gemini_ai import gemini_service, sanitize_typography
from core.database import get_lead_funnel_triggers

logger = logging.getLogger("intent_detector")

BOHDAN_AI_PERSONA_PROMPT = """
You are Bohdan (@bohdan.gpt), an elite AI engineer, tech creator, and prompt specialist.
Your style:
- Friendly, confident, modern tech creator vibe.
- Concise (1 to 2 short sentences max, social-media ready).
- High energy with relevant emojis (⚡, 🚀, 🧠, 🔥).
- Strictly in English.
- Always encourage engagement or answer their specific question clearly.
"""


class CommentIntentResult:
    def __init__(
        self,
        intent: str, # 'lead_magnet', 'question_chat', 'spam'
        matched_trigger: Optional[str] = None,
        confidence: float = 1.0,
        ai_reply_text: Optional[str] = None
    ):
        self.intent = intent
        self.matched_trigger = matched_trigger
        self.confidence = confidence
        self.ai_reply_text = ai_reply_text

    def is_lead_magnet(self) -> bool:
        return self.intent == "lead_magnet"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "matched_trigger": self.matched_trigger,
            "confidence": self.confidence,
            "ai_reply_text": self.ai_reply_text
        }


def clean_text_for_matching(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", text or "").lower()


def detect_comment_intent(comment_text: str, custom_triggers: Optional[List[str]] = None) -> CommentIntentResult:
    """
    Двоетапне розпізнавання наміру коментаря:
    1. Швидкий точний / Regex пошук по списку активних тригерів (GPT, PROMPT, VAULT, тощо).
    2. Якщо точного слова немає — розумний аналіз через LLM (Gemini 3.5 Flash).
    """
    raw_text = (comment_text or "").strip()
    if not raw_text:
        return CommentIntentResult("spam", confidence=1.0)

    raw_lower = raw_text.lower()

    # --- ЕТАП 0: Швидкий спам-фільтр (реклама, скам, крипта, номери телефонів) ---
    spam_pattern = r"(whatsapp|\+?\d{9,}|crypto|bitcoin|invest in|binance|forex|telegram @|dm @|promo code|follow me for|check my bio for money)"
    if re.search(spam_pattern, raw_lower):
        return CommentIntentResult("spam", confidence=0.99)

    triggers = custom_triggers if custom_triggers is not None else get_lead_funnel_triggers(only_active=True)
    clean_words = set(clean_text_for_matching(raw_text).split())

    # --- ЕТАП 1: Точний та морфологічний матчинг тригерів (GPT, PROMPT, VAULT, тощо) ---
    for trigger in triggers:
        t_clean = trigger.strip().lower()
        if not t_clean:
            continue
        # Перевірка як окремого слова або частини короткого коментаря
        if t_clean in clean_words or (len(raw_text) <= 30 and t_clean in raw_lower):
            return CommentIntentResult(
                intent="lead_magnet",
                matched_trigger=trigger.upper(),
                confidence=1.0
            )

    # Також перевіряємо очевидні фрази англійською та українською
    common_lead_phrases = [
        "send me", "dm me", "link please", "where is the link", "can i get",
        "drop the link", "скинь", "де посилання", "дай промпт", "хочу базу"
    ]
    for phrase in common_lead_phrases:
        if phrase in raw_lower:
            return CommentIntentResult(
                intent="lead_magnet",
                matched_trigger="NATURAL_REQUEST",
                confidence=0.95
            )

    # --- ЕТАП 2: Швидке розпізнавання похвали (Instant Charismatic Response) ---
    praise_phrases = [
        "great video", "awesome video", "awesome", "great content", "love this",
        "super helpful", "nice video", "fire 🔥", "top content", "clean editing", "amazing work"
    ]
    if any(p in raw_lower for p in praise_phrases) and not any(t in raw_lower for t in ["gpt", "link", "prompt", "vault"]):
        return CommentIntentResult(
            intent="question_chat",
            matched_trigger="PRAISE",
            confidence=0.95,
            ai_reply_text="Appreciate you checking out the video! Let me know if you need any AI tips 🚀"
        )

    # --- ЕТАП 3: LLM (Gemini) класифікація складних питань та генерація відповіді ---
    llm_result = _classify_and_reply_with_gemini(raw_text)
    return llm_result


def _classify_and_reply_with_gemini(comment_text: str) -> CommentIntentResult:
    """
    Використовує Gemini для семантичного розпізнавання та генерації відповіді англійською.
    Якщо квота вичерпана або сталася помилка — миттєво повертає харизматичний фолбек без затримок.
    """
    prompt = f"""{BOHDAN_AI_PERSONA_PROMPT}

Task: Analyze this user comment under Bohdan's AI tutorial video/Reel:
Comment: "{comment_text}"

Classify into one of 3 categories:
1. "lead_magnet": User is asking for the prompt list, files, cheat sheet, link, access, guides, or resources, even without exact keywords.
2. "question_chat": General positive comment, feedback, tech question, or discussion about the video.
3. "spam": Obvious spam, bot promotion, crypto scam, or offensive noise.

If "question_chat": write a short (1 sentence max), charismatic English reply from Bohdan.
If "lead_magnet": set ai_reply to null.
If "spam": set ai_reply to null.

Output STRICT JSON ONLY:
{{
  "intent": "lead_magnet" | "question_chat" | "spam",
  "confidence": 0.95,
  "matched_trigger": "AI_INFERRED" or null,
  "ai_reply": "..." or null
}}
"""
    try:
        cl = gemini_service.client
        if cl:
            resp = cl.models.generate_content(
                model=getattr(gemini_service, "model_name", "gemini-3.5-flash"),
                contents=[prompt]
            )
            if resp and getattr(resp, "text", None):
                txt = resp.text.strip()
                json_match = re.search(r"\{.*\}", txt, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(0))
                    intent = data.get("intent", "question_chat")
                    reply = data.get("ai_reply")
                    if reply:
                        reply = sanitize_typography(reply.strip())
                    return CommentIntentResult(
                        intent=intent,
                        matched_trigger=data.get("matched_trigger"),
                        confidence=float(data.get("confidence", 0.9)),
                        ai_reply_text=reply
                    )
    except Exception as e:
        logger.debug(f"LLM класифікація коментаря пропущена (квота/помилка): {e}")

    # Швидкий фолбек за замовчуванням
    return CommentIntentResult(
        intent="question_chat",
        confidence=0.5,
        ai_reply_text="Appreciate you checking out the video! Let me know if you need any AI tips 🚀"
    )
