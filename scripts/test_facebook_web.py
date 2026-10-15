"""Offline checks for server receipts and collapsed Business Suite replies."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from services.lead_funnel.platforms.facebook_web import FacebookWeb, COMMENTS_QUERY, graphql_chunks, comment_nodes, own_reply
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

    def test_existing_different_reply_is_terminal_without_sending(self):
        self.reply['body']['text'] = 'An earlier reply'
        web = Mock(); web.comments.return_value = comment_nodes([self.parent, self.reply])
        self.assertEqual(self.send(web), (False, 'already_replied_manual'))
        web.create_reply.assert_not_called()

    def page(self, nodes, cursor=None):
        return [{'data': {'feedback': {'id': 'post-feedback',
            'comment_rendering_instance_for_feed_location': {
                'selected_intent': {'intent_token': 'newest-comments'},
                'comments': {'edges': [{'node': node} for node in nodes],
                    'page_info': {'has_next_page': cursor is not None, 'end_cursor': cursor}}}}}}]

    def test_comments_load_every_page_merge_duplicates_and_keep_sort_intent(self):
        web = FacebookWeb(None, {}, 'page')
        partial = {'__typename': 'Comment', 'id': 'parent-node', 'extra': 'from next page'}
        web.query = Mock(side_effect=[self.page([self.parent], 'c1'),
            self.page([partial, self.reply], 'c2'), self.page([self.reply])])
        comments = web.comments('post')
        self.assertEqual(set(comments), {'parent-node', 'reply-node'})
        self.assertEqual(comments['parent-node']['extra'], 'from next page')
        self.assertEqual(comments['parent-node']['body']['text'], 'GPT')
        self.assertTrue(own_reply(self.parent, comments, {FACEBOOK_PROFILE_ID}))
        for call, cursor in zip(web.query.call_args_list[1:], ['c1', 'c2']):
            self.assertEqual(call.args[0], COMMENTS_QUERY)
            self.assertEqual(call.args[1]['commentsAfterCursor'], cursor)
            self.assertEqual(call.args[1]['commentsIntentToken'], 'newest-comments')
            self.assertEqual(call.args[1]['id'], 'post-feedback')

    def test_focused_verification_does_not_rescan_all_comments(self):
        web = FacebookWeb(None, {}, 'page')
        web.query = Mock(return_value=self.page([self.parent, self.reply], 'more'))
        self.assertEqual(len(web.comments('post', '200')), 2)
        web.query.assert_called_once()

    def test_broken_pagination_is_visible_instead_of_a_partial_success(self):
        for pages in [[self.page([self.parent], 'same'), self.page([], 'same')],
                      [self.page([self.parent], 'more'), [{'data': {}}]]]:
            web = FacebookWeb(None, {}, 'page')
            web.query = Mock(side_effect=pages)
            with self.assertRaisesRegex(PlatformAccessError, 'pagination'):
                web.comments('post')
            self.assertEqual(web.query.call_count, 2)

    def test_comments_without_explicit_depth_are_not_dropped(self):
        parent_no_depth = {
            '__typename': 'Comment', 'id': 'parent-no-depth', 'legacy_fbid': '101',
            'author': {'id': 'visitor2', 'name': 'Visitor 2'}, 'body': {'text': 'GPT'},
            'feedback': {'id': 'fb-2'}
        }
        web = Mock()
        web.posts.return_value = ['post-1']
        web.comments.return_value = {'parent-no-depth': parent_no_depth}
        with patch('services.lead_funnel.platforms.facebook_web.facebook_web') as connection:
            connection.return_value.__enter__.return_value = web
            results = FacebookFunnel()._fetch_comments_via_browser()
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].comment_id, '101')
            self.assertEqual(results[0].text, 'GPT')


if __name__ == '__main__':
    unittest.main(verbosity=2)
