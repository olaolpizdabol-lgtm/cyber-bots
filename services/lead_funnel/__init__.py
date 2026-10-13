"""
🎯 Lead Funnel Package
"""
from services.lead_funnel.funnel_service import lead_funnel_service, LeadFunnelService
from services.lead_funnel.intent_detector import detect_comment_intent, CommentIntentResult

__all__ = ["lead_funnel_service", "LeadFunnelService", "detect_comment_intent", "CommentIntentResult"]
