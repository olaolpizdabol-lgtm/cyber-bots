"""Offline regression checks; never send messages or touch the working database."""
import asyncio
import ast
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core.database as db
from core.browser_lock import TimeoutLock
from services.lead_funnel import funnel_service as fs
from services.lead_funnel.platforms.base import PlatformComment, PlatformAccessError
from services.lead_funnel.intent_detector import CommentIntentResult
from services.lead_funnel.platforms.youtube import YouTubeFunnel


class FunnelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patch = patch.object(db, 'DB_PATH', Path(self.temp.name) / 'test.db')
        self.patch.start()
        self.addCleanup(self.patch.stop)
        db.init_db()
        self.service = fs.LeadFunnelService()
        self.handler = Mock()
        self.handler.reply_to_comment.return_value = (True, None)
        self.handler.send_direct_message.return_value = (True, None)
        self.handler.check_follower_status.return_value = (True, None)
        self.handler.reply_to_direct_message.return_value = (True, None)
        self.handler.fetch_direct_messages.return_value = []
        self.comment = PlatformComment('comment-1', 'post-1', None, 'user-1', 'visitor', 'GPT')
        self.handler.fetch_recent_unanswered_comments.return_value = [self.comment]
        self.service.platforms = {'instagram': self.handler, 'youtube': self.handler, 'facebook': self.handler, 'tiktok': self.handler}
        for name, value in [('notify_telegram_lead', Mock()), ('detect_comment_intent', Mock(return_value=CommentIntentResult('lead_magnet', 'GPT'))), ('time.sleep', Mock())]:
            patcher = patch('services.lead_funnel.funnel_service.' + name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def scan(self, platform='instagram'):
        return self.service.process_platform_comments(platform)

    def test_failed_reply_is_retryable_and_never_reported_as_delivered(self):
        self.handler.reply_to_comment.return_value = (False, 'offline')
        self.scan('youtube')
        self.assertEqual(db.get_lead_comment('youtube', 'comment-1')['status'], 'reply_failed')
        fs.notify_telegram_lead.assert_not_called()
        self.handler.reply_to_comment.return_value = (True, None)
        self.assertEqual(self.scan('youtube')['replies'], 1)
        self.assertEqual(self.handler.reply_to_comment.call_count, 2)

    def test_dm_is_not_resent_when_public_reply_fails(self):
        self.handler.reply_to_comment.return_value = (False, 'offline')
        self.scan()
        self.assertEqual(db.get_lead_comment('instagram', 'comment-1')['status'], 'sent_dm_reply_pending')
        self.handler.reply_to_comment.return_value = (True, None)
        self.scan()
        self.handler.send_direct_message.assert_called_once()
        self.assertEqual(db.get_lead_comment('instagram', 'comment-1')['status'], 'sent_dm')

    def test_successful_comment_is_not_repeated(self):
        self.scan(); self.scan()
        self.handler.reply_to_comment.assert_called_once()

    def test_same_user_can_ask_a_new_question(self):
        self.scan()
        self.comment.comment_id = 'comment-2'
        fs.detect_comment_intent.return_value = CommentIntentResult('question_chat', ai_reply_text='A useful answer')
        self.scan()
        self.assertEqual(self.handler.reply_to_comment.call_count, 2)
        self.handler.send_direct_message.assert_called_once()

    def test_one_failed_comment_does_not_abort_batch(self):
        self.handler.fetch_recent_unanswered_comments.return_value += [PlatformComment('comment-2', 'p', None, 'u2', 'other', 'GPT')]
        self.handler.reply_to_comment.side_effect = [RuntimeError('offline'), (True, None)]
        stats = self.scan('youtube')
        self.assertEqual((stats['errors'], stats['replies']), (1, 1))

    def test_question_replies_obey_batch_limit(self):
        fs.detect_comment_intent.return_value = CommentIntentResult('question_chat', ai_reply_text='Thanks')
        self.handler.fetch_recent_unanswered_comments.return_value *= 2
        stats = self.service.process_platform_comments('youtube', max_replies_batch=1)
        self.assertEqual(stats['processed'], 1)

    def test_bridge_does_not_waste_time_checking_followers(self):
        self.scan('youtube')
        self.handler.check_follower_status.assert_not_called()

    def test_busy_scan_does_not_start_another_worker(self):
        with self.service._platform_locks["instagram"]:
            self.assertEqual(self.scan()['busy'], 1)
        self.handler.fetch_recent_unanswered_comments.assert_not_called()

    def test_fetch_failure_is_visible(self):
        self.handler.fetch_recent_unanswered_comments.side_effect = RuntimeError('session expired')
        self.assertEqual(self.scan()['errors'], 1)
        self.assertEqual(self.service.last_scan['instagram']['errors'], 1)

    def test_scan_reports_known_access_failure_without_leaking_arbitrary_errors(self):
        self.handler.fetch_recent_unanswered_comments.side_effect = PlatformAccessError('Facebook browser session expired')
        self.scan('facebook')
        self.assertEqual(self.service.last_error['facebook'], 'Facebook browser session expired')
        self.handler.fetch_recent_unanswered_comments.side_effect = RuntimeError('private response body')
        self.scan('facebook')
        self.assertEqual(self.service.last_error['facebook'], 'RuntimeError')

    def test_browser_error_reports_only_safe_reason(self):
        from playwright.sync_api import Error
        exc = Error('Page.goto: net::ERR_CONNECTION_RESET at https://example.test/?private=value')
        self.assertEqual(fs.platform_error_reason(exc), 'net::ERR_CONNECTION_RESET')
        self.assertEqual(fs.platform_error_reason(Error('private response body')), 'Error')

    def test_facebook_crash_reports_container_oom_count_and_closes_browser(self):
        from services.lead_funnel.platforms.facebook import FacebookFunnel
        from playwright.sync_api import Error
        playwright = Mock(); browser = playwright.chromium.launch.return_value
        browser.new_page.return_value.goto.side_effect = Error('Page.goto: Page crashed')
        with patch('playwright.sync_api.sync_playwright') as runtime, patch('core.mem_guard.get_oom_kill_count', return_value=3), patch('core.mem_guard.get_free_memory_mb', return_value=500), patch('services.lead_funnel.platforms.facebook.FACEBOOK_STATE_FILE') as state:
            runtime.return_value.__enter__.return_value = playwright
            state.exists.return_value = True
            with self.assertRaisesRegex(PlatformAccessError, 'OOM kills=3, free memory=500 MB'):
                FacebookFunnel()._fetch_comments_via_browser()
        browser.close.assert_called_once()

    def test_manual_reply_is_not_proof_of_dm_delivery(self):
        db.save_lead_comment('instagram', 'old', 'p', 'u', 'visitor', 'Hi', 'question_chat', None, False, 'already_replied_manual')
        self.assertFalse(db.has_user_received_lead('instagram', 'visitor'))
        self.scan()
        self.handler.send_direct_message.assert_called_once()

    def test_upsert_preserves_identity_and_delivery_time(self):
        self.scan()
        before = db.get_lead_comment('instagram', 'comment-1')
        db.save_lead_comment('instagram', 'comment-1', 'p', 'u', 'visitor', 'GPT', 'lead_magnet', 'GPT', True, 'reply_failed')
        after = db.get_lead_comment('instagram', 'comment-1')
        self.assertEqual((before['id'], before['dm_sent_at']), (after['id'], after['dm_sent_at']))
        self.assertGreater(after['check_count'], before['check_count'])

    def inbox(self, platform='instagram'):
        self.handler.fetch_direct_messages.return_value = [PlatformComment('m1', 'thread1', None, 'u1', 'visitor', 'Hello')]
        return self.service.process_direct_messages(platform)

    def test_ordinary_inbox_message_gets_vault_once_when_following(self):
        fs.detect_comment_intent.return_value = CommentIntentResult('question_chat', ai_reply_text='Hello')
        self.assertEqual(self.inbox()['dms_sent'], 1)
        self.assertEqual(self.inbox()['dms_sent'], 0)
        self.handler.reply_to_direct_message.assert_called_once()
        self.assertIn('/vault/', self.handler.reply_to_direct_message.call_args.args[1])

    def test_nonfollower_inbox_never_gets_link_then_receives_after_follow(self):
        self.handler.check_follower_status.return_value = (False, None)
        self.assertEqual(self.inbox()['dms_sent'], 0)
        self.assertNotIn('https://', self.handler.reply_to_direct_message.call_args.args[1])
        self.assertFalse(db.has_user_received_lead('instagram', 'visitor'))
        self.handler.is_user_following.return_value = True
        self.assertEqual(self.service.recheck_pending_leads('instagram'), 1)
        self.assertIn('/vault/', self.handler.reply_to_direct_message.call_args.args[1])
        self.assertTrue(db.has_user_received_lead('instagram', 'visitor'))
        self.handler.send_direct_message.assert_not_called()

    def test_unknown_follow_is_not_access_or_not_following(self):
        self.handler.check_follower_status.return_value = (None, None)
        self.inbox()
        row = db.get_lead_comment('instagram', 'dm_m1')
        self.assertEqual(row['status'], 'pending_verification')
        self.assertNotIn('https://', self.handler.reply_to_direct_message.call_args.args[1])

    def test_missing_delivery_receipt_never_saved_as_sent_or_retried_blindly(self):
        self.handler.reply_to_direct_message.return_value = (False, 'delivery_unknown')
        self.inbox(); self.inbox()
        self.assertEqual(db.get_lead_comment('instagram', 'dm_m1')['status'], 'delivery_unknown')
        self.assertFalse(db.has_user_received_lead('instagram', 'visitor'))
        self.handler.reply_to_direct_message.assert_called_once()

    def test_failed_inbox_reply_can_retry(self):
        self.handler.reply_to_direct_message.return_value = (False, 'request_not_accepted')
        self.assertEqual(self.inbox()['errors'], 1)
        self.assertIsNone(db.get_lead_comment('instagram', 'dm_m1'))

    def test_facebook_all_comments_use_standard_link_without_ai_or_follow_gate(self):
        self.comment.text = 'ordinary question'
        self.scan('facebook')
        self.handler.check_follower_status.assert_not_called()
        self.handler.send_direct_message.assert_not_called()
        fs.detect_comment_intent.assert_not_called()
        self.assertIn('/vault/?from=facebook', self.handler.reply_to_comment.call_args.args[1])
        self.assertFalse(db.has_user_received_lead('facebook', 'visitor'))

    def test_facebook_inbox_has_no_follow_gate(self):
        self.assertEqual(self.inbox('facebook')['dms_sent'], 1)
        self.handler.check_follower_status.assert_not_called()
        fs.detect_comment_intent.assert_not_called()

    def test_independent_platform_can_scan_while_instagram_is_busy(self):
        with self.service._platform_locks['instagram']:
            self.assertEqual(self.scan('facebook')['replies'], 1)
            self.assertEqual(self.scan('instagram')['busy'], 1)

    def test_legacy_sent_status_is_not_verified_delivery(self):
        db.save_lead_comment('instagram', 'legacy', 'p', 'u', 'visitor', 'GPT', 'lead_magnet', None, True, 'sent_dm')
        self.assertFalse(db.has_user_received_lead('instagram', 'visitor'))

    def test_pending_does_not_expire_before_user_follows(self):
        db.save_lead_comment('instagram', 'old', 'p', 'u', 'visitor', 'GPT', 'lead_magnet', None, False, 'pending_follow')
        row = db.get_lead_comment('instagram', 'old')
        for _ in range(20): db.update_lead_status(row['id'], 'pending_follow')
        self.assertEqual(len(db.get_pending_follow_leads()), 1)

    def test_dm_failure_does_not_repeat_public_fallback(self):
        self.handler.send_direct_message.return_value = (False, 'temporary_error')
        self.scan(); self.scan()
        self.handler.reply_to_comment.assert_called_once()
        self.assertEqual(len(db.get_pending_follow_leads()), 1)

    def test_recheck_retries_temporary_dm_errors(self):
        self.handler.send_direct_message.return_value = (False, 'temporary_error')
        self.scan()
        self.handler.is_user_following.return_value = True
        self.handler.send_direct_message.return_value = (True, None)
        self.assertEqual(self.service.recheck_pending_leads(), 1)
        self.assertEqual(db.get_lead_comment('instagram', 'comment-1')['status'], 'converted')

    def test_recheck_continues_after_one_user_fails(self):
        for i in range(2):
            db.save_lead_comment('instagram', str(i), 'p', str(i), str(i), 'GPT', 'lead_magnet', 'GPT', False, 'pending_follow')
        self.handler.is_user_following.side_effect = [RuntimeError('unavailable'), True]
        self.assertEqual(self.service.recheck_pending_leads(), 1)



class LockTests(unittest.TestCase):
    def test_timeout_never_enters_critical_section(self):
        lock = TimeoutLock(default_timeout=0.001)
        with lock:
            with self.assertRaises(TimeoutError):
                with lock:
                    self.fail('entered without acquiring')
            self.assertTrue(lock.locked())
        self.assertFalse(lock.locked())

    def test_browser_pool_has_real_capacity_and_keeps_owners(self):
        lock = TimeoutLock(default_timeout=0.01, capacity=2)
        entered = threading.Event(); release = threading.Event()
        def second_browser():
            with lock:
                entered.set()
                release.wait(1)
        with lock:
            worker = threading.Thread(target=second_browser)
            worker.start()
            self.assertTrue(entered.wait(1))
            self.assertTrue(lock.locked())
            attempted = []
            third = threading.Thread(target=lambda: attempted.append(lock.acquire(blocking=False)))
            third.start(); third.join()
            self.assertEqual(attempted, [False])
            release.set(); worker.join()
            self.assertFalse(lock.locked())

    def test_other_thread_cannot_release_lock(self):
        lock = TimeoutLock()
        failures = []
        def attempt():
            try:
                lock.release()
            except RuntimeError:
                failures.append(True)
        with lock:
            worker = threading.Thread(target=attempt); worker.start(); worker.join()
            self.assertEqual(failures, [True])
            self.assertTrue(lock.locked())


class PlatformTests(unittest.TestCase):
    @patch('services.publishers.youtube.youtube_publisher._get_authenticated_service')
    def test_youtube_requires_channel_and_uses_top_comment_id(self, auth):
        service = auth.return_value
        service.channels.return_value.list.return_value.execute.return_value = {'items': [{'id': 'owner'}]}
        service.commentThreads.return_value.list.return_value.execute.return_value = {'items': [{'id': 'thread-id', 'snippet': {'videoId': 'video', 'topLevelComment': {'id': 'comment-id', 'snippet': {'authorDisplayName': 'Bohdan Visitor', 'authorChannelId': {'value': 'visitor'}, 'textDisplay': 'GPT'}}}}]}
        results = YouTubeFunnel().fetch_recent_unanswered_comments()
        self.assertEqual(results[0].comment_id, 'comment-id')
        self.assertEqual(service.commentThreads.return_value.list.call_args.kwargs['allThreadsRelatedToChannelId'], 'owner')

    @patch('services.publishers.youtube.youtube_publisher._get_authenticated_service', return_value=None)
    def test_youtube_missing_auth_is_failure(self, auth):
        self.assertEqual(YouTubeFunnel().reply_to_comment('c', 'text')[0], False)
        with self.assertRaises(RuntimeError):
            YouTubeFunnel().fetch_recent_unanswered_comments()

    def test_instagram_client_recovers_after_cooldown(self):
        from services.lead_funnel.platforms.instagram import InstagramFunnel
        client = InstagramFunnel()
        client._retry_after = 100
        with patch('services.lead_funnel.platforms.instagram.time.monotonic', return_value=99):
            self.assertIsNone(client._get_client())
        with patch('services.lead_funnel.platforms.instagram.time.monotonic', return_value=101), patch('services.lead_funnel.platforms.instagram.proxy_manager') as proxy, patch('services.lead_funnel.platforms.instagram.INSTAGRAM_SESSION_FILE', '/missing/test-session'):
            proxy.proxy_url = 'configured'
            proxy.is_proxy_alive.return_value = False
            self.assertIsNone(client._get_client())
            self.assertEqual(client._retry_after, 0)

    def test_platform_fallbacks_never_claim_delivery(self):
        from services.lead_funnel.platforms.instagram import InstagramFunnel
        from services.lead_funnel.platforms.facebook import FacebookFunnel
        from services.lead_funnel.platforms.tiktok import TikTokFunnel
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with patch('services.lead_funnel.platforms.instagram.DATA_DIR', folder), patch.object(InstagramFunnel, '_get_client', return_value=None):
                self.assertFalse(InstagramFunnel().reply_to_comment('c', 'text')[0])
            with patch('services.lead_funnel.platforms.facebook.FACEBOOK_STATE_FILE', folder / 'missing'), patch('services.lead_funnel.platforms.facebook.FACEBOOK_PAGE_TOKEN', ''):
                self.assertFalse(FacebookFunnel().reply_to_comment('c', 'text')[0])
            with patch('services.lead_funnel.platforms.tiktok.DATA_DIR', folder):
                self.assertFalse(TikTokFunnel().reply_to_comment('c', 'text')[0])

    def test_browser_session_is_not_loaded_as_instagrapi_settings(self):
        import json
        from services.lead_funnel.platforms.instagram import InstagramFunnel
        with tempfile.TemporaryDirectory() as temp:
            session = Path(temp) / 'session.json'
            session.write_text(json.dumps({'cookies': [{'name': 'sessionid', 'domain': '.instagram.com', 'value': 'test-only-invalid'}]}))
            with patch('services.lead_funnel.platforms.instagram.INSTAGRAM_SESSION_FILE', session), patch('services.lead_funnel.platforms.instagram.proxy_manager') as proxy, patch('instagrapi.Client') as client:
                proxy.proxy_url = ''
                self.assertIsNotNone(InstagramFunnel()._get_client())
                client.return_value.load_settings.assert_not_called()
                client.return_value.login_by_sessionid.assert_called_once_with('test-only-invalid')

    def test_instagram_followed_by_direction_and_unknown(self):
        from services.lead_funnel.platforms.instagram import InstagramFunnel
        handler = InstagramFunnel()
        client = Mock()
        with patch.object(handler, '_get_client', return_value=client), patch('services.lead_funnel.platforms.instagram.DATA_DIR', Path('/missing')):
            client.user_friendship_v1.return_value = SimpleNamespace(followed_by=False, following=True)
            self.assertIs(handler.check_follower_status('123', 'visitor')[0], False)
            client.user_friendship_v1.return_value = SimpleNamespace(followed_by=True, following=False)
            self.assertIs(handler.check_follower_status('123', 'visitor')[0], True)
            client.user_friendship_v1.side_effect = RuntimeError('unavailable')
            self.assertIsNone(handler.check_follower_status('123', 'visitor')[0])

    def test_instagram_direct_requires_receipt_and_accepts_request(self):
        from services.lead_funnel.platforms.instagram import InstagramFunnel
        handler = InstagramFunnel(); client = Mock(user_id='owner')
        message = PlatformComment('m', 't', None, 'u', 'visitor', 'GPT', pending_request=True)
        client.direct_thread.return_value = SimpleNamespace(users=[SimpleNamespace(pk='u')], messages=[])
        with patch.object(handler, '_get_client', return_value=client):
            client.direct_pending_approve.return_value = False
            self.assertEqual(handler.reply_to_direct_message(message, 'link'), (False, 'request_not_accepted'))
            client.direct_send.assert_not_called()
            client.direct_pending_approve.return_value = True
            client.direct_send.return_value = SimpleNamespace(id=None)
            self.assertEqual(handler.reply_to_direct_message(message, 'link'), (False, 'delivery_unknown'))
            client.direct_send.return_value = SimpleNamespace(id='confirmed')
            self.assertEqual(handler.reply_to_direct_message(message, 'link'), (True, None))

    def test_instagram_inbox_skips_own_messages_and_groups(self):
        from services.lead_funnel.platforms.instagram import InstagramFunnel
        handler = InstagramFunnel(); client = Mock()
        user = SimpleNamespace(pk='visitor', username='visitor')
        client.direct_threads.return_value = [SimpleNamespace(id='t1', users=[user], messages=[SimpleNamespace(id='own', user_id='owner', text='Hi')]), SimpleNamespace(id='t2', users=[user,user])]
        client.direct_pending_inbox.return_value = [SimpleNamespace(id='t3', users=[user], messages=[SimpleNamespace(id='m', user_id='visitor', text='hello')])]
        with patch.object(handler, '_get_client', return_value=client):
            messages = list(handler.fetch_direct_messages())
        self.assertEqual(len(messages), 1)
        self.assertTrue(messages[0].pending_request)

    def test_instagram_403_stops_requests_and_is_not_unknown_delivery(self):
        from services.lead_funnel.platforms.instagram import InstagramFunnel
        from instagrapi.exceptions import ClientForbiddenError
        handler = InstagramFunnel(); client = Mock()
        handler._client = client
        client.direct_send.side_effect = ClientForbiddenError('synthetic rejection', code=403)
        result = handler.send_direct_message('123', 'visitor', 'vault link')
        self.assertFalse(result[0])
        self.assertIn('HTTP 403', result[1])
        self.assertIsNone(handler._get_client())
        self.assertFalse(handler.send_direct_message('123', 'visitor', 'vault link')[0])
        client.direct_send.assert_called_once()

    def test_facebook_post_200_without_receipt_is_not_success(self):
        from services.lead_funnel.platforms.facebook import FacebookFunnel
        with patch('services.lead_funnel.platforms.facebook.requests.post') as post, patch('services.lead_funnel.platforms.facebook.FACEBOOK_PAGE_TOKEN', 'test-placeholder'):
            post.return_value.status_code = 200
            post.return_value.json.return_value = {}
            self.assertEqual(FacebookFunnel().reply_to_comment('123', 'link'), (False, 'delivery_unknown'))
            self.assertFalse(FacebookFunnel().reply_to_direct_message(PlatformComment('m','t',None,'u','v','hi'), 'link')[0])

    def test_report_runs_immediately_then_every_600_seconds_independent_of_scan(self):
        source = ast.parse(Path('main.py').read_text())
        main = next(n for n in source.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'main')
        reporter = next(n for n in main.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'lead_report_background_task')
        bot = SimpleNamespace(send_message=AsyncMock())
        sleeps = []
        async def sleep(seconds):
            self.assertEqual(bot.send_message.await_count, len(sleeps) + 1)
            sleeps.append(seconds)
            if len(sleeps) > 1:
                raise asyncio.CancelledError
        namespace = {'html': __import__('html'), 'asyncio': SimpleNamespace(sleep=sleep, to_thread=AsyncMock(return_value={'unconfirmed_delivery': 0})), 'ALLOWED_USER_IDS': [123], 'bot': bot, 'logger': Mock()}
        exec(compile(ast.Module(body=[reporter], type_ignores=[]), '<report>', 'exec'), namespace)
        async def run():
            with self.assertRaises(asyncio.CancelledError):
                await namespace['lead_report_background_task']()
        asyncio.run(run())
        self.assertEqual(sleeps, [600, 600])
        self.assertEqual(bot.send_message.await_count, 2)
        self.assertIn('Бот запущений', bot.send_message.await_args_list[0].args[1])
        self.assertIn('Звіт бота', bot.send_message.await_args_list[1].args[1])

    def test_report_recovers_from_database_and_recipient_failures(self):
        source = ast.parse(Path('main.py').read_text())
        main = next(n for n in source.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'main')
        reporter = next(n for n in main.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'lead_report_background_task')
        bot = SimpleNamespace(send_message=AsyncMock(side_effect=[RuntimeError('unavailable'), SimpleNamespace(message_id=10), SimpleNamespace(message_id=11), SimpleNamespace(message_id=12)]))
        sleeps = []
        async def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 2:
                raise asyncio.CancelledError
        logger = Mock()
        namespace = {'html': __import__('html'), 'asyncio': SimpleNamespace(sleep=sleep, to_thread=AsyncMock(side_effect=[RuntimeError('database unavailable'), {'unconfirmed_delivery': 0}])), 'ALLOWED_USER_IDS': [123, 456], 'bot': bot, 'logger': logger}
        exec(compile(ast.Module(body=[reporter], type_ignores=[]), '<report>', 'exec'), namespace)
        async def run():
            with self.assertRaises(asyncio.CancelledError):
                await namespace['lead_report_background_task']()
        asyncio.run(run())
        self.assertEqual(bot.send_message.await_count, 4)
        self.assertIn('статистику зібрати не вдалося', bot.send_message.await_args_list[1].args[1])
        self.assertIn('Звіт бота', bot.send_message.await_args_list[2].args[1])
        self.assertEqual(logger.warning.call_count, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
