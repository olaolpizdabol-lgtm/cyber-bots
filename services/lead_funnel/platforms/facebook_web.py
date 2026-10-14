"""Business Suite requests in Chromium without rendering its memory-heavy SPA."""
import json
import re
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode

from core.browser_lock import BROWSER_LOCK, CHROME_DOCKER_ARGS
from .base import PlatformAccessError

# shortcut: Business Suite document IDs observed on 2026-10-14; refresh after Meta changes these queries.
LIST_QUERY = ("BizInboxCommentThreadListContainerQuery", "28655553327402876")
DETAIL_QUERY = ("BizInboxPostDetailViewWrapperQuery", "28929232363375473")
CREATE_COMMENT = ("useCometUFICreateCommentMutation", "28728724973421052")
DETAIL_VARIABLES = json.loads(Path(__file__).with_name("facebook_query.json").read_text())


def graphql_chunks(text):
    decoder = json.JSONDecoder()
    text = text.lstrip().removeprefix("for (;;);")
    chunks = []
    while text.strip():
        try:
            value, end = decoder.raw_decode(text.lstrip())
        except ValueError:
            raise PlatformAccessError("Facebook returned an invalid query response") from None
        if value.get("error") or value.get("errors"):
            raise PlatformAccessError("Facebook rejected the Business Suite query; check session and Page access")
        chunks.append(value)
        text = text.lstrip()[end:]
    return chunks


def walk_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_nodes(child)


def merge_node(target, source):
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge_node(target[key], value)
        elif value is not None and (value or key not in target):
            target[key] = value


def comment_nodes(chunks):
    comments = {}
    for node in walk_nodes(chunks):
        if node.get("id") and (node.get("__typename") == "Comment" or
                (node.get("legacy_fbid") and node.get("author") and node.get("body"))):
            merge_node(comments.setdefault(node["id"], {}), node)
    return comments


def own_reply(parent, comments, owner_ids, text=None):
    for reply in comments.values():
        if (reply.get("comment_direct_parent") or {}).get("id") != parent["id"]:
            continue
        if (reply.get("author") or {}).get("id") not in owner_ids:
            continue
        if reply.get("legacy_fbid") and (text is None or (reply.get("body") or {}).get("text") == text):
            return reply["legacy_fbid"]
    # A collapsed own reply proves that the comment was answered, but not its text/delivery.
    if text is None:
        reply = (parent.get("inline_replies_expander_renderer") or {}).get("interesting_reply") or {}
        if (reply.get("author") or {}).get("id") in owner_ids:
            return reply.get("id")
    return None


class FacebookWeb:
    def __init__(self, page, fields, page_id):
        self.page = page
        self.fields = fields
        self.page_id = page_id

    def query(self, operation, variables):
        name, doc_id = operation
        body = urlencode({**self.fields, "av": self.page_id, "__a": "1",
            "fb_api_caller_class": "RelayModern", "fb_api_req_friendly_name": name,
            "doc_id": doc_id, "variables": json.dumps(variables)})
        response = self.page.evaluate("""async data => {
            const response = await fetch('/api/graphql/', {method: 'POST', credentials: 'include',
                headers: {'content-type': 'application/x-www-form-urlencoded',
                    'x-fb-friendly-name': data.name, 'x-fb-lsd': data.lsd}, body: data.body,
                signal: AbortSignal.timeout(25000)});
            return {status: response.status, text: await response.text()};
        }""", {"name": name, "lsd": self.fields["lsd"], "body": body})
        if response["status"] != 200:
            raise PlatformAccessError(f"Facebook Business Suite query unavailable (HTTP {response['status']})")
        return graphql_chunks(response["text"])

    def posts(self, limit):
        posts, cursor = [], None
        while len(posts) < limit:
            response = self.query(LIST_QUERY, {"pageID": self.page_id, "count": min(20, limit - len(posts)),
                "cursor": cursor, "filterType": None, "filterIsReadStatus": None, "filterOwnerID": None,
                "filterStatus": "TODO", "platformFilter": "FACEBOOK",
                "isHighlightedComment": False, "isStarsComment": False})
            connection = next((n["business_comm_items"] for n in walk_nodes(response)
                if isinstance(n.get("business_comm_items"), dict)), None)
            if connection is None:
                raise PlatformAccessError("Facebook comment inbox schema changed")
            posts.extend(edge["node"]["id"] for edge in connection.get("edges", [])
                if edge.get("node", {}).get("comm_type") == "FB_PAGE_POST")
            info = connection.get("page_info") or {}
            if not info.get("has_next_page") or not info.get("end_cursor") or info["end_cursor"] == cursor:
                break
            cursor = info["end_cursor"]
        return list(dict.fromkeys(posts))[:limit]

    def comments(self, post_id, focus=None):
        return comment_nodes(self.query(DETAIL_QUERY, {**DETAIL_VARIABLES,
            "commItemID": post_id, "focusCommentID": focus}))

    def create_reply(self, parent, text):
        variables = {"feedLocation": "BUSINESS_COMMENT_INBOX_TAB", "feedbackSource": 107,
            "groupID": None, "inviteShortLinkKey": None, "renderLocation": None,
            "scale": 1, "useDefaultActor": False, "focusCommentID": None,
            "translationType": "ORIGINAL", "canUseNicknameOnComet": False,
            "__relay_internal__pv__groups_comet_use_glvrelayprovider": False,
            "__relay_internal__pv__CometUFICommentActionLinksRewriteEnabledrelayprovider": True,
            "__relay_internal__pv__CometUFICommentAvatarStickerAnimatedImagerelayprovider": False,
            "__relay_internal__pv__IsWorkUserrelayprovider": False,
            "__relay_internal__pv__CometUFICommentAutoTranslationTyperelayprovider": "ORIGINAL",
            "input": {"client_mutation_id": "1", "attachments": None,
                "feedback_id": parent["feedback"]["id"], "formatting_style": None,
                "message": {"text": text, "ranges": []},
                "reply_comment_parent_fbid": parent["id"], "reply_target_clicked": True,
                "vod_video_timestamp": 0, "is_tracking_encrypted": True,
                "tracking": [], "feedback_source": "BUSINESS_COMMENT_INBOX_TAB",
                "idempotence_token": str(uuid.uuid4()), "session_id": str(uuid.uuid4())}}
        return self.query(CREATE_COMMENT, variables)


@contextmanager
def facebook_web(state_file, page_id):
    if not state_file.exists():
        raise PlatformAccessError("Facebook browser session missing")
    from playwright.sync_api import sync_playwright
    with BROWSER_LOCK, sync_playwright() as runtime:
        browser = runtime.chromium.launch(channel="chromium", headless=True, args=CHROME_DOCKER_ARGS)
        try:
            context = browser.new_context(storage_state=str(state_file), locale="en-US")
            page = context.new_page()
            page.goto("https://business.facebook.com/robots.txt", wait_until="domcontentloaded", timeout=25000)
            response = page.evaluate("""async pageID => {
                const response = await fetch('/latest/inbox/facebook?asset_id=' + pageID,
                    {signal: AbortSignal.timeout(25000)});
                return {status: response.status, text: await response.text(), url: response.url};
            }""", page_id)
            if response["status"] != 200 or "login" in response["url"]:
                raise PlatformAccessError("Facebook browser session expired")
            modules = {}
            for name in ("DTSGInitialData", "LSD", "CurrentUserInitialData", "BusinessUnifiedNavigationContext"):
                match = re.search(r'\["' + name + r'",\[\],(\{.*?\}),\d+\]', response["text"])
                if match:
                    modules[name] = json.loads(match.group(1))
            fields = {"fb_dtsg": modules.get("DTSGInitialData", {}).get("token"),
                "lsd": modules.get("LSD", {}).get("token"),
                "__user": modules.get("CurrentUserInitialData", {}).get("USER_ID")}
            cookie_owner = next((c["value"] for c in context.cookies() if c["name"] == "c_user"), None)
            if not all(fields.values()) or fields["__user"] != cookie_owner:
                raise PlatformAccessError("Facebook session needs a new login in Chrome Bohdan")
            fields["jazoest"] = "2" + str(sum(map(ord, fields["fb_dtsg"])))
            business = modules.get("BusinessUnifiedNavigationContext", {}).get("businessID")
            if business:
                fields["__bid"] = business
            yield FacebookWeb(page, fields, page_id)
        except Exception as exc:
            if "Page crashed" in str(exc):
                from core.mem_guard import get_oom_kill_count
                raise PlatformAccessError(f"Facebook browser crashed; container OOM kills={get_oom_kill_count()}") from None
            raise
        finally:
            try:
                browser.close()
            except Exception:
                pass
