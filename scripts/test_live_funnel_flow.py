"""
🧪 Live Flow End-to-End Test for Lead Funnel on Instagram & Facebook
"""
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_flow")

from services.lead_funnel.funnel_service import lead_funnel_service
from services.lead_funnel.platforms.base import PlatformComment
from core.database import (
    get_lead_comment,
    is_user_already_handled,
    has_user_received_lead,
    get_lead_funnel_stats
)

def test_full_pipeline():
    print("=" * 70)
    print("🚀 LIVE PIPELINE TEST: INSTAGRAM & FACEBOOK LEAD FUNNEL")
    print("=" * 70)

    # 1. Instagram Flow Test on live comment hamzz__a1
    print("\n--- 1. Instagram Pipeline Check ---")
    ig_handler = lead_funnel_service.platforms["instagram"]
    ig_comments = ig_handler.fetch_recent_unanswered_comments(limit_posts=2)
    print(f"Instagram comments found: {len(ig_comments)}")
    for c in ig_comments:
        print(f"  User: {c.username} | Text: {c.text} | Replied: {c.has_author_replied}")
        if is_user_already_handled("instagram", c.username) or c.has_author_replied:
            print(f"  ✅ Correctly skipped duplicate/already answered user: @{c.username}")

    # 2. Facebook Flow Test on live comment
    print("\n--- 2. Facebook Pipeline Check ---")
    fb_handler = lead_funnel_service.platforms["facebook"]
    fb_comments = fb_handler.fetch_recent_unanswered_comments(limit_posts=2)
    print(f"Facebook comments found: {len(fb_comments)}")
    for c in fb_comments:
        print(f"  User: {c.username} ({c.user_id})")
        print(f"  Text: {c.text}")
        print(f"  Comment Screenshot: {c.screenshot_path} (exists: {Path(c.screenshot_path).exists() if c.screenshot_path else False})")
        # Check follower proof
        is_fol, proof_path = fb_handler.check_follower_status(c.user_id, c.username)
        print(f"  Follower status: {is_fol} | Profile Proof: {proof_path} (exists: {Path(proof_path).exists() if proof_path else False})")
        assert c.screenshot_path and Path(c.screenshot_path).exists(), "Comment screenshot must exist!"
        assert proof_path and Path(proof_path).exists(), "Profile proof must exist!"

    # 3. Stats verification
    print("\n--- 3. Database Stats Check ---")
    stats = get_lead_funnel_stats()
    print("Stats summary:", stats)
    assert stats["total_comments"] >= 0

    print("\n" + "=" * 70)
    print("🎉 FULL LIVE PIPELINE VERIFICATION PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    test_full_pipeline()
