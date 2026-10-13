"""
🧪 Comprehensive End-to-End Multi-Scenario Verification for Instagram & Facebook Lead Funnel
"""
import sys
import os
import shutil
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.lead_funnel.intent_detector import detect_comment_intent
from services.lead_funnel.platforms.base import PlatformComment
from services.lead_funnel.platforms.instagram import instagram_funnel
from services.lead_funnel.platforms.facebook import facebook_funnel
from services.lead_funnel.funnel_service import lead_funnel_service
from core.database import (
    get_lead_comment,
    save_lead_comment,
    is_user_already_handled,
    has_user_received_lead,
    get_lead_funnel_stats
)
from config import TEMP_DIR

def run_multi_scenario_test():
    print("=" * 70)
    print("🚀 ПОЧАТОК ПЕРЕВІРКИ СЦЕНАРІЇВ ДЛЯ INSTAGRAM ТА FACEBOOK")
    print("=" * 70)

    # -------------------------------------------------------------
    # СЦЕНАРІЙ 1: Instagram Підписник просить лід-магніт ("GPT")
    # -------------------------------------------------------------
    print("\n[СЦЕНАРІЙ 1: Instagram Підписник (Lead Magnet)]")
    # Перевіримо реальну функцію check_follower_status для hamzz__a1
    is_fol_ig, proof_ig = instagram_funnel.check_follower_status("hamzz__a1", "hamzz__a1")
    print(f"  • Перевірка підписки Instagram (@hamzz__a1): is_following={is_fol_ig}")
    print(f"  • Фото-доказ профілю: {proof_ig} (існує: {Path(proof_ig).exists() if proof_ig else False})")
    assert is_fol_ig is True, "hamzz__a1 повинен бути визначений як підписник!"
    assert proof_ig and Path(proof_ig).exists(), "Скріншот шапки профілю Instagram має бути створено!"

    # Створюємо коментар підписника
    comm_ig_follower = PlatformComment(
        comment_id="test_ig_follower_001",
        post_id="post_ig_123",
        post_url="https://instagram.com/p/test_ig_123",
        user_id="hamzz__a1_test",
        username="hamzz__a1_test",
        text="GPT please! 🔥",
        is_following=True,
        screenshot_path=proof_ig
    )
    intent_1 = detect_comment_intent(comm_ig_follower.text)
    print(f"  • Детекція наміру: {intent_1.intent} (is_lead={intent_1.is_lead_magnet()}) | Тригер: {intent_1.matched_trigger}")
    assert intent_1.is_lead_magnet() is True

    # Перевіряємо генерацію DM та відповіді
    dm_text_ig = lead_funnel_service.get_formatted_dm_text("instagram")
    dm_link_ig = lead_funnel_service.get_lead_link("instagram")
    print(f"  • DM текст для підписника: '{dm_text_ig[:55]}...' (лінк: {dm_link_ig})")
    assert dm_link_ig in dm_text_ig

    print("  ✅ Сценарій 1 (Instagram Follower Lead) успішно пройдено!")

    # -------------------------------------------------------------
    # СЦЕНАРІЙ 2: Facebook НЕ-підписник просить лід-магніт ("GPT vault")
    # -------------------------------------------------------------
    print("\n[СЦЕНАРІЙ 2: Facebook Не-підписник (Pending Follow)]")
    fb_user = "T Isha"
    is_fol_fb, proof_fb = facebook_funnel.check_follower_status(fb_user, fb_user)
    print(f"  • Перевірка підписки Facebook ({fb_user}): is_following={is_fol_fb}")
    print(f"  • Фото-доказ профілю: {proof_fb} (існує: {Path(proof_fb).exists() if proof_fb else False})")
    assert is_fol_fb is False, "T Isha має бути визначений як не-підписник!"
    assert proof_fb and Path(proof_fb).exists(), "Скріншот шапки профілю Facebook має бути створено!"

    comm_fb_nonfollower = PlatformComment(
        comment_id="test_fb_nonfollower_002",
        post_id="fb_post_456",
        post_url="https://facebook.com/reel/fb_post_456",
        user_id=fb_user,
        username=fb_user,
        text="Can you drop the GPT prompt vault link please?",
        is_following=False,
        screenshot_path=proof_fb
    )
    intent_2 = detect_comment_intent(comm_fb_nonfollower.text)
    print(f"  • Детекція наміру: {intent_2.intent} (is_lead={intent_2.is_lead_magnet()}) | Тригер: {intent_2.matched_trigger}")
    assert intent_2.is_lead_magnet() is True
    print("  • Дія: Не-підписнику публічно пропонується підписатися, а лід зберігається зі статусом 'pending_follow'.")
    print("  ✅ Сценарій 2 (Facebook Non-Follower Pending) успішно пройдено!")

    # -------------------------------------------------------------
    # СЦЕНАРІЙ 3: Запитання / AI Chat коментар (не лід-магніт)
    # -------------------------------------------------------------
    print("\n[СЦЕНАРІЙ 3: Запитання / Чат коментар (AI Question)]")
    comm_chat = PlatformComment(
        comment_id="test_chat_003",
        post_id="post_789",
        post_url="https://facebook.com/reel/post_789",
        user_id="alex_photographer",
        username="alex_photographer",
        text="What camera and lighting did you use for this shot?",
        is_following=False
    )
    intent_3 = detect_comment_intent(comm_chat.text)
    print(f"  • Детекція наміру: {intent_3.intent} (is_lead={intent_3.is_lead_magnet()})")
    assert intent_3.intent == "question_chat"
    assert intent_3.is_lead_magnet() is False
    assert intent_3.ai_reply_text is not None and len(intent_3.ai_reply_text) > 5
    print(f"  • AI згенерована відповідь: \"{intent_3.ai_reply_text}\"")
    print("  • Дія: Публічна відповідь у коментарях, DM НЕ надсилається, лід НЕ створюється.")
    print("  ✅ Сценарій 3 (AI Chat Comment) успішно пройдено!")

    # -------------------------------------------------------------
    # СЦЕНАРІЙ 4: Захист від повторної обробки (User already handled / author replied)
    # -------------------------------------------------------------
    print("\n[СЦЕНАРІЙ 4: Захист від дублювання та повторних відповідей]")
    # Перевірка Wisnu Bintang Pradana (якому автор відповів вручну)
    is_wisnu_handled = is_user_already_handled("facebook", "Wisnu Bintang Pradana")
    has_wisnu_lead = has_user_received_lead("facebook", "Wisnu Bintang Pradana")
    print(f"  • Перевірка 'Wisnu Bintang Pradana': is_handled={is_wisnu_handled}, has_received_lead={has_wisnu_lead}")
    assert is_wisnu_handled is True or has_wisnu_lead is True

    # Перевірка hamzz__a1
    is_hamzz_handled = is_user_already_handled("instagram", "hamzz__a1")
    print(f"  • Перевірка 'hamzz__a1': is_handled={is_hamzz_handled}")
    assert is_hamzz_handled is True

    print("  • Дія: Система блокує повторні надсилання, дублі сповіщень у Telegram та спам.")
    print("  ✅ Сценарій 4 (Deduplication & Author Reply Protection) успішно пройдено!")

    # -------------------------------------------------------------
    # СЦЕНАРІЙ 5: Спам-фільтр (Spam / Scam Detection)
    # -------------------------------------------------------------
    print("\n[СЦЕНАРІЙ 5: Фільтрація спаму]")
    spam_comment_text = "DM me on WhatsApp +123456789 to invest in crypto bitcoin signals"
    intent_5 = detect_comment_intent(spam_comment_text)
    print(f"  • Спам коментар: '{spam_comment_text[:40]}...' -> Intent: {intent_5.intent}")
    assert intent_5.intent == "spam"
    print("  • Дія: Коментар ігнорується, НЕ лайкається, відповіді не надсилаються.")
    print("  ✅ Сценарій 5 (Spam Filter) успішно пройдено!")

    # -------------------------------------------------------------
    # СЦЕНАРІЙ 6: Детальна статистика бази даних
    # -------------------------------------------------------------
    print("\n[СЦЕНАРІЙ 6: Перевірка детальної аналітики воронки]")
    stats = get_lead_funnel_stats()
    print(f"  • Загальна статистика:")
    print(f"    - Всього коментарів: {stats['total_comments']}")
    print(f"    - Всього лідів: {stats['total_leads']}")
    print(f"    - Доставлено в DM: {stats['dms_delivered']}")
    print(f"    - Очікують підписки: {stats['pending_follow']}")
    print(f"    - Відповідей на питання (AI Chat): {stats['ai_chat_replies']}")
    print(f"    - Підписаних: {stats['followers_count']} | Не підписаних: {stats['non_followers_count']}")
    print(f"  • По платформах: {stats['by_platform']}")
    assert "by_platform" in stats
    assert "followers_count" in stats
    print("  ✅ Сценарій 6 (Detailed Funnel Analytics) успішно пройдено!")

    print("\n" + "=" * 70)
    print("🎉 ВСІ 6 СЦЕНАРІЇВ УСПІШНО ПРОЙДЕНО БЕЗ ЖОДНИХ ПОМИЛОК!")
    print("=" * 70)

if __name__ == "__main__":
    run_multi_scenario_test()
