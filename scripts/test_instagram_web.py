"""Offline checks for Instagram web recipients, follow direction and server receipts."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from services.lead_funnel.platforms.instagram import InstagramFunnel
from services.lead_funnel.platforms.instagram_web import InstagramWeb


class InstagramWebTests(unittest.TestCase):
    def setUp(self):
        self.handler = InstagramFunnel()
        self.web = Mock(owner_id='owner')
        self.thread = {'thread_key': 'key', 'thread_fbid': 'send-id', 'users': [{'pk': '123', 'username': 'visitor'}], 'system_folder': 'INBOX'}
        self.web.thread.return_value = self.thread
        self.web.messages.return_value = []
        self.patch = patch('services.lead_funnel.platforms.instagram_web.instagram_web')
        self.connection = self.patch.start()
        self.connection.return_value.__enter__.return_value = self.web
        self.addCleanup(self.patch.stop)

    def send(self):
        return self.handler._send_web_message('vault', '123', 'visitor', 'key')

    def test_follower_direction_and_recipient_must_match(self):
        web = InstagramWeb(None, {}, {}, 'owner'); web.query = Mock()
        for followed, following in [(True, False), (False, True)]:
            web.query.return_value = {'user': {'username': 'visitor', 'friendship_status': {'followed_by': followed, 'following': following}}}
            self.assertIs(web.following('123', 'visitor'), followed)
        web.query.return_value = {'user': {'username': 'another', 'friendship_status': {'followed_by': True}}}
        self.assertIsNone(web.following('123', 'visitor'))

    def test_rejected_mobile_session_cannot_fall_through_to_a_web_send(self):
        self.handler._retry_after = float('inf')
        self.assertEqual(self.send(), (False, 'authorization_paused'))
        self.connection.assert_not_called()

    def test_wrong_recipient_never_submits(self):
        self.thread['users'][0]['pk'] = '456'
        self.assertEqual(self.send(), (False, 'recipient_mismatch'))
        self.web.send_text.assert_not_called()

    def test_pending_request_requires_acceptance_before_send(self):
        self.thread['system_folder'] = 'PENDING'; self.web.accept_request.return_value = False
        self.assertEqual(self.send(), (False, 'request_not_accepted'))
        self.web.send_text.assert_not_called()

    def test_existing_own_message_is_not_repeated(self):
        self.web.messages.return_value = [{'text_body': 'vault'}]; self.web.is_own_message.return_value = True
        self.assertEqual(self.send(), (True, None))
        self.web.send_text.assert_not_called()

    def test_send_requires_receipt_and_correct_readback(self):
        self.web.send_text.return_value = None
        self.assertEqual(self.send(), (False, 'delivery_unknown'))
        self.web.send_text.return_value = 'mid.server'
        self.web.messages.side_effect = [[], [{'message_id': 'mid.another', 'text_body': 'vault'}]]
        self.web.is_own_message.return_value = True
        self.assertEqual(self.send(), (False, 'delivery_unknown'))
        self.web.messages.side_effect = [[], [{'message_id': 'mid.server', 'text_body': 'vault'}]]
        self.assertEqual(self.send(), (True, None))

    def test_new_conversation_receipt_without_inbox_readback_is_unknown(self):
        self.web.inbox.return_value = []
        self.web.send_text.return_value = 'mid.server'
        result = self.handler._send_web_message('vault', '123', 'visitor')
        self.assertEqual(result, (False, 'delivery_unknown'))
        self.web.send_text.assert_called_once_with('vault', thread=None, recipient='123')

    def test_restricted_account_backoff_does_not_open_more_browsers(self):
        self.patch.stop()
        from services.lead_funnel.platforms import instagram_web as module
        from services.lead_funnel.platforms.base import PlatformAccessError
        with patch.object(module, '_auth_retry_after', float('inf')), patch('playwright.sync_api.sync_playwright') as browser:
            with self.assertRaisesRegex(PlatformAccessError, 'account verification'):
                with module.instagram_web():
                    self.fail('Restricted session must not be used')
            browser.assert_not_called()

    def test_comment_requires_owned_post_and_parent_receipt(self):
        self.web.api.return_value = {'items': [{'user': {'pk': 'another-owner'}}]}
        self.assertEqual(self.handler._reply_web_comment('100', 'follow first', '200'), (False, 'post_owner_mismatch'))
        self.web.create_comment.assert_not_called()
        self.web.api.return_value = {'items': [{'user': {'pk': 'owner'}}]}
        self.web.comments.return_value = [{'pk': '100', 'user': {'pk': '123', 'username': 'visitor'}}]
        self.web.child_comments.side_effect = [[], [{'pk': '300', 'user': {'pk': 'owner'}, 'text': 'follow first', 'parent_comment_id': '101'}]]
        self.web.create_comment.return_value = {'pk': '300', 'user': {'pk': 'owner'}}
        self.assertEqual(self.handler._reply_web_comment('100', 'follow first', '200'), (False, 'delivery_unknown'))
        self.web.child_comments.side_effect = [[], [{'pk': '300', 'user': {'pk': 'owner'}, 'text': 'follow first', 'parent_comment_id': '100'}]]
        self.assertEqual(self.handler._reply_web_comment('100', 'follow first', '200'), (True, None))

    def test_comment_cursor_is_encoded_and_repeated_cursor_stops(self):
        web = InstagramWeb(None, {}, {}, 'owner'); web.api = Mock()
        cursor = '{"token":"a+b&c="}'
        web.api.side_effect = [{'comments': [{'pk': '100'}], 'has_more_headload_comments': True, 'next_min_id': cursor},
            {'comments': [{'pk': '101'}], 'has_more_headload_comments': True, 'next_min_id': cursor}]
        self.assertEqual([c['pk'] for c in web.comments('200')], ['100', '101'])
        self.assertIn('min_id=%7B%22token%22%3A%22a%2Bb%26c%3D%22%7D', web.api.call_args.args[0])
        self.assertEqual(web.api.call_count, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
