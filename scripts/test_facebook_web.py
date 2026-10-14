"""Offline checks for server receipts and collapsed Business Suite replies."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from services.lead_funnel.platforms.facebook_web import graphql_chunks, comment_nodes, own_reply
from services.lead_funnel.platforms.facebook import FacebookFunnel, FACEBOOK_PROFILE_ID
from services.lead_funnel.platforms.base import PlatformAccessError


class FacebookWebTests(unittest.TestCase):
    def setUp(self):
        self.parent = {'__typename': 'Comment', 'id': 'parent-node', 'legacy_fbid': '100',
            'author': {'id': 'visitor'}, 'depth': 0, 'body': {'text': 'GPT'},
            'feedback': {'id': 'feedback-node', 'viewer_actor': {'id': FACEBOOK_PROFILE_ID}}}
        # Mutation nodes omit __typename; query nodes can arrive in separate chunks.
        self.reply = {'id': 'reply-node', 'legacy_fbid': '200', 'author': {'id': FACEBOOK_PROFILE_ID},
            'body': {'text': 'vault link'}, 'comment_direct_parent': {'id': 'parent-node'}}

    def test_incremental_response_preserves_parent_body_and_collapsed_reply(self):
        partial = {'__typename': 'Comment', 'id': 'parent-node',
            'inline_replies_expander_renderer': {'interesting_reply': {'id': 'reply-node', 'author': {'id': FACEBOOK_PROFILE_ID}}}}
        raw = 'for (;;);' + json.dumps({'data': self.parent}) + '\n' + json.dumps({'data': partial})
        comments = comment_nodes(graphql_chunks(raw))
        parent = comments['parent-node']
        self.assertEqual(parent['body']['text'], 'GPT')
        self.assertTrue(own_reply(parent, comments, {FACEBOOK_PROFILE_ID}))
        self.assertIsNone(own_reply(parent, comments, {FACEBOOK_PROFILE_ID}, 'vault link'))

    def test_mutation_without_typename_has_a_receipt(self):
        comments = comment_nodes([{'data': {'comment_create': {'feedback_comment_edge': {'node': self.reply}}}}])
        self.assertEqual(own_reply(self.parent, comments, {FACEBOOK_PROFILE_ID}, 'vault link'), '200')
        self.reply['comment_direct_parent']['id'] = 'another-parent'
        comments = comment_nodes([self.reply])
        self.assertIsNone(own_reply(self.parent, comments, {FACEBOOK_PROFILE_ID}, 'vault link'))

    def test_nested_partial_does_not_mutate_the_response_being_traversed(self):
        node = {'__typename': 'Comment', 'id': 'parent', 'feedback': {
            'partial': {'__typename': 'Comment', 'id': 'parent', 'feedback': {'extra': 1}}, 'id': 'feedback'}}
        before = json.dumps(node)
        result = comment_nodes([node])
        self.assertEqual(result['parent']['feedback']['extra'], 1)
        self.assertEqual(json.dumps(node), before)

    def test_errors_are_not_empty_successful_scans(self):
        for raw in ['for (;;);{"error":1357054}', '{"errors":[{"message":"private diagnostic"}]}', '<html>login</html>']:
            with self.assertRaises(PlatformAccessError):
                graphql_chunks(raw)

    def send(self, web):
        with patch('services.lead_funnel.platforms.facebook.FACEBOOK_PAGE_TOKEN', ''), patch('services.lead_funnel.platforms.facebook_web.facebook_web') as connection:
            connection.return_value.__enter__.return_value = web
            return FacebookFunnel().reply_to_comment('100', 'vault link', '300')

    def test_send_requires_owned_actor_and_persisted_readback(self):
        web = Mock(); web.comments.side_effect = [comment_nodes([self.parent]), comment_nodes([self.parent, self.reply])]
        web.create_reply.return_value = [self.reply]
        self.assertEqual(self.send(web), (True, None))
        web.create_reply.assert_called_once()
        web = Mock(); web.comments.side_effect = [comment_nodes([self.parent]), comment_nodes([self.parent])]
        web.create_reply.return_value = [self.reply]
        self.assertEqual(self.send(web), (False, 'delivery_unknown'))
        self.parent['feedback']['viewer_actor']['id'] = 'another-page'
        web = Mock(); web.comments.return_value = comment_nodes([self.parent])
        self.assertEqual(self.send(web), (False, 'page_actor_mismatch'))
        web.create_reply.assert_not_called()

    def test_existing_exact_reply_is_not_sent_twice(self):
        web = Mock(); web.comments.return_value = comment_nodes([self.parent, self.reply])
        self.assertEqual(self.send(web), (True, None))
        web.create_reply.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
