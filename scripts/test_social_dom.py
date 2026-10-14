"""Offline DOM checks against anonymized Facebook HTML captured on 2026-10-14."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright
from services.lead_funnel.platforms.facebook import FacebookFunnel


class FacebookDOMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.page.route('**/*', lambda route: route.abort())
        self.page.set_content((Path(__file__).parent / 'fixtures/facebook_comments.html').read_text())
        self.addCleanup(self.page.close)

    def test_real_comment_structure_keeps_author_text_and_id_separate(self):
        rows = FacebookFunnel._read_comment_rows(self.page)
        self.assertEqual([(r['id'], r['username'], r['text']) for r in rows], [
            ('100', 'Visitor 1', 'Gpt'), ('101', 'Visitor 2', 'Gpt'),
            ('102', 'Visitor 3', 'How about face changing')])

    def test_multiple_reply_editors_cannot_redirect_to_another_comment(self):
        for cid in ('100', '101'):
            row = self.page.locator(f'a[href$="comment_id={cid}"]').locator('xpath=ancestor::div[@role="article"][1]')
            row.locator('xpath=..').evaluate("el => el.insertAdjacentHTML('beforeend', '<div role=\"textbox\" aria-label=\"Reply as Bohdan GPT\" contenteditable=\"true\"></div>')")
        target = self.page.locator('a[href$="comment_id=101"]').locator('xpath=ancestor::div[@role="article"][1]').locator('xpath=..')
        target.get_by_role('textbox', name='Reply as Bohdan GPT').fill('test reply')
        self.assertEqual(self.page.get_by_role('textbox').all_text_contents(), ['', 'test reply'])
        # Text inside an editor is never a persisted outgoing reply.
        self.assertEqual(target.locator('[role="article"][aria-label^="Comment by Bohdan GPT "]').get_by_text('test reply', exact=True).count(), 0)

    def test_identity_restriction_is_failure_not_empty_inbox(self):
        self.page.set_content('<h4>Confirm your identity to send messages</h4>')
        with self.assertRaisesRegex(RuntimeError, 'identity confirmation'):
            FacebookFunnel._check_restrictions(self.page)

    def test_own_reply_is_not_a_new_customer_comment(self):
        row = self.page.locator('[role="article"]').first
        row.locator('xpath=..').evaluate("el => el.insertAdjacentHTML('beforeend', '<div role=\"article\" aria-label=\"Comment by Bohdan GPT 1 minute ago\"><div role=\"button\">Bohdan GPT</div><a href=\"https://www.facebook.com/reel/123/?comment_id=200\">1m</a>vault link</div>')")
        rows = FacebookFunnel._read_comment_rows(self.page)
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0]['replied'])
        self.assertFalse(rows[1]['replied'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
