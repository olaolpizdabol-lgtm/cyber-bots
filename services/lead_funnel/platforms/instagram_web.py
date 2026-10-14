"""Instagram's web requests use web cookies, without an emulated mobile login."""
import json
import re
import secrets
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode

from config import DATA_DIR, INSTAGRAM_USERNAME
from core.browser_lock import BROWSER_LOCK, CHROME_DOCKER_ARGS
from .base import PlatformAccessError
from .facebook_web import graphql_chunks, walk_nodes

# shortcut: Web query documents observed on 2026-10-14; refresh them when Instagram changes its client.
QUERIES = json.loads(Path(__file__).with_name("instagram_queries.json").read_text())
SEND_TEXT = "26911679871773184"


class InstagramWeb:
    def __init__(self, page, fields, headers, owner_id):
        self.page, self.fields, self.headers, self.owner_id = page, fields, headers, owner_id

    def request(self, path, data=None):
        response = self.page.evaluate("""async data => {
            const response = await fetch(data.path, {method: data.body === null ? 'GET' : 'POST',
                credentials: 'include', headers: data.headers, body: data.body,
                signal: AbortSignal.timeout(25000)});
            return {status: response.status, text: await response.text()};
        }""", {"path": path, "headers": self.headers,
            "body": urlencode(data) if data is not None else None})
        if response["status"] != 200:
            raise PlatformAccessError(f"Instagram web request unavailable (HTTP {response['status']})")
        return response["text"]

    def api(self, path, data=None):
        try:
            response = json.loads(self.request("/api/v1/" + path, data))
        except ValueError:
            raise PlatformAccessError("Instagram web API returned an invalid response") from None
        if response.get("status") != "ok":
            raise PlatformAccessError("Instagram web API rejected the request; check login and account restrictions")
        return response

    def query(self, name, variables, doc_id=None):
        query = QUERIES.get(name, {})
        fields = {**self.fields, "__a": "1", "__user": "0", "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": name, "doc_id": doc_id or query["doc_id"],
            "variables": json.dumps({**query.get("variables", {}), **variables})}
        try:
            chunks = graphql_chunks(self.request("/api/graphql", fields))
        except PlatformAccessError as exc:
            if str(exc).startswith("Facebook "):
                raise PlatformAccessError("Instagram rejected the web query; check session and account access") from None
            raise
        if not chunks or not isinstance(chunks[0].get("data"), dict):
            raise PlatformAccessError("Instagram web query returned no data")
        return chunks[0]["data"]

    def posts(self, limit):
        data = self.query("PolarisProfilePostsQuery", {"username": INSTAGRAM_USERNAME or "bohdan.gpt",
            "data": {**QUERIES["PolarisProfilePostsQuery"]["variables"]["data"], "count": limit}})
        connection = data.get("xdt_api__v1__feed__user_timeline_graphql_connection")
        if connection is None:
            raise PlatformAccessError("Instagram post query schema changed")
        return [edge["node"] for edge in connection.get("edges", [])]

    def comments(self, media_id):
        response = self.api(f"media/{media_id}/comments/?can_support_threading=true&permalink_enabled=false")
        comments = {str(c["pk"]): c for c in response.get("comments", [])}
        cursor, seen = response.get("next_min_id"), set()
        while response.get("has_more_headload_comments") and cursor and cursor not in seen:
            seen.add(cursor)
            response = self.api(f"media/{media_id}/comments/?" + urlencode(
                {"can_support_threading": "true", "permalink_enabled": "false", "min_id": cursor}))
            comments.update({str(c["pk"]): c for c in response.get("comments", [])})
            cursor = response.get("next_min_id")
        return list(comments.values())

    def child_comments(self, media_id, parent_id):
        comments, cursor, seen = {}, None, set()
        while True:
            data = self.query("PolarisPostChildCommentsQuery", {
                "media_id": str(media_id), "parent_comment_id": str(parent_id), "after": cursor})
            connection = data.get("xdt_api__v1__media__media_id__comments__parent_comment_id__child_comments__connection")
            if connection is None:
                raise PlatformAccessError("Instagram reply query schema changed")
            comments.update({str(edge["node"]["pk"]): edge["node"] for edge in connection.get("edges", [])})
            info = connection.get("page_info") or {}
            cursor = info.get("end_cursor")
            if not info.get("has_next_page") or not cursor or cursor in seen:
                break
            seen.add(cursor)
        return list(comments.values())

    def create_comment(self, media_id, parent_id, text):
        response = self.query("PolarisPostCommentInputRevampedMutation", {"connections": [],
            "data": {"comment_text": text, "media_id": str(media_id),
                "replied_to_comment_id": int(parent_id)}}, "27261905640092552")
        return (response.get("xig_comment_create") or {}).get("comment_dict")

    def follower_id(self, username):
        result = self.api(f"friendships/{self.owner_id}/followers/?" + urlencode(
            {"count": 12, "query": username, "search_surface": "follow_list_page"}))
        matches = [u for u in result.get("users", []) if u.get("username", "").lower() == username.lower()]
        return str(matches[0]["pk"]) if len(matches) == 1 else None

    def following(self, user_id, username):
        if str(user_id).isdigit():
            user = self.query("PolarisProfilePageContentQuery", {"id": str(user_id)}).get("user") or {}
            if user.get("username", "").lower() != username.lower():
                return None
            value = (user.get("friendship_status") or {}).get("followed_by")
            return value if isinstance(value, bool) else None
        result = self.api(f"friendships/{self.owner_id}/followers/?" + urlencode(
            {"count": 12, "query": username, "search_surface": "follow_list_page"}))
        if any(u.get("username", "").lower() == username.lower() for u in result.get("users", [])):
            return True
        if result.get("has_more") is False and not result.get("should_limit_list_of_followers"):
            return False
        return None

    def inbox(self):
        threads = {}
        for name in ("PolarisDirectInboxQuery", "PolarisDirectMessageRequestQuery"):
            variables = {"device_id_for_iris_subscription": str(uuid.uuid4())}
            if name == "PolarisDirectMessageRequestQuery":
                variables["__relay_internal__pv__IGD30DayAgoTimestampMsrelayprovider"] = str(int((time.time() - 30 * 86400) * 1000))
            data = self.query(name, variables)
            for node in walk_nodes(data):
                thread = node.get("as_ig_direct_thread")
                if thread and thread.get("thread_key"):
                    threads[thread["thread_key"]] = thread
        return list(threads.values())

    def thread(self, thread_key):
        data = self.query("IGDThreadDetailQuery", {"thread_fbid": str(thread_key)})
        thread = (data.get("get_slide_thread_nullable") or {}).get("as_ig_direct_thread")
        if not thread or str(thread.get("viewer_id")) != self.owner_id or thread.get("is_group"):
            raise PlatformAccessError("Instagram thread unavailable or recipient ambiguous")
        return thread

    @staticmethod
    def messages(thread):
        return [edge["node"] for edge in (thread.get("slide_messages") or {}).get("edges", [])]

    def is_own_message(self, message):
        sender = ((message.get("sender") or {}).get("user_dict") or {})
        return sender.get("username") == (INSTAGRAM_USERNAME or "bohdan.gpt")

    def accept_request(self, thread):
        response = self.query("useIGDirectAcceptMessageRequestMutation", {
            "thread_fbid": thread["thread_fbid"], "ig_inbox_folder": "PRIMARY",
            "offline_threading_id": str((int(time.time() * 1000) << 22) | secrets.randbits(22))}, "36571001125823973")
        if not response.get("ig_direct_accept_message_request"):
            return False
        verified = self.thread(thread["thread_key"])
        return verified.get("system_folder") == "INBOX"

    def send_text(self, text, thread=None, recipient=None):
        data = self.query("IGDirectTextSendMutation", {
            "ig_thread_igid": thread["thread_fbid"] if thread else None,
            "offline_threading_id": str((int(time.time() * 1000) << 22) | secrets.randbits(22)),
            "recipient_igids": [str(recipient)] if recipient else None,
            "replied_to_client_context": None, "replied_to_item_id": None, "reply_to_message_id": None,
            "sampled": None, "text": {"sensitive_string_value": text},
            "mentions": [], "mentioned_user_ids": [], "commands": None,
            "forwarded_from_thread_id": None, "is_forwarded_from_own_message": None,
            "send_attribution": "igd_web_chat_tab:in_thread"}, SEND_TEXT)
        return (data.get("xig_direct_text_send_with_slide_messaging_response") or {}).get("message_id")


@contextmanager
def instagram_web():
    state = DATA_DIR / "instagram_state.json"
    if not state.exists():
        raise PlatformAccessError("Instagram browser session missing")
    from playwright.sync_api import sync_playwright
    with BROWSER_LOCK, sync_playwright() as runtime:
        browser = runtime.chromium.launch(channel="chromium", headless=True, args=CHROME_DOCKER_ARGS)
        try:
            context = browser.new_context(storage_state=str(state), locale="en-US")
            page = context.new_page()
            page.goto("https://www.instagram.com/robots.txt", wait_until="domcontentloaded", timeout=25000)
            response = page.evaluate("""async () => {
                const response = await fetch('/direct/inbox/', {signal: AbortSignal.timeout(25000)});
                return {status: response.status, url: response.url, text: await response.text()};
            }""")
            if response["status"] != 200 or "login" in response["url"]:
                raise PlatformAccessError("Instagram session needs a new login in Chrome Bohdan")
            modules = {}
            for name in ("DTSGInitialData", "LSD", "PolarisViewer"):
                match = re.search(r'\["' + name + r'",\[\],(\{.*?\}),\d+\]', response["text"])
                if match:
                    modules[name] = json.loads(match.group(1))
            cookies = {c["name"]: c["value"] for c in context.cookies()
                if c["domain"].lstrip(".") in ("instagram.com", "www.instagram.com")}
            viewer = modules.get("PolarisViewer", {}).get("data") or {}
            if (not viewer.get("id") or viewer["id"] != cookies.get("ds_user_id")
                    or viewer.get("username") != (INSTAGRAM_USERNAME or "bohdan.gpt")):
                raise PlatformAccessError("Instagram session needs a new login in Chrome Bohdan")
            fields = {"fb_dtsg": modules.get("DTSGInitialData", {}).get("token"),
                "lsd": modules.get("LSD", {}).get("token")}
            if not all(fields.values()) or not cookies.get("csrftoken"):
                raise PlatformAccessError("Instagram session bootstrap unavailable")
            fields["jazoest"] = "2" + str(sum(map(ord, fields["fb_dtsg"])))
            headers = {"content-type": "application/x-www-form-urlencoded",
                "x-csrftoken": cookies["csrftoken"], "x-fb-lsd": fields["lsd"],
                "x-ig-app-id": "936619743392459", "x-requested-with": "XMLHttpRequest"}
            yield InstagramWeb(page, fields, headers, viewer["id"])
        finally:
            try:
                browser.close()
            except Exception:
                pass
