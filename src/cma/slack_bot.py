"""Slack listener for `/cma<address>` messages in the grokbot channel.

Socket Mode keeps the bot outbound-only: no public request URL. The command
runs only in #grokbot. Messages in #deals are ignored.
"""

from __future__ import annotations

import os
import re
import sys
import traceback

from cma.engine import analyze
from cma.errors import CmaError
from cma.report import render_text

_COMMAND = re.compile(r"(?:^|\s)/cma(?:\s+|:|(?=\d))", re.IGNORECASE)
DEFAULT_CHANNEL = "grokbot"
BLOCKED_CHANNELS = frozenset({"deals"})


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def message_is_cma(text: str | None) -> bool:
    if not text:
        return False
    without_mentions = re.sub(r"<@[A-Z0-9]+>", " ", text)
    return _COMMAND.search(without_mentions) is not None


def normalize_channel_name(name: str | None) -> str:
    if not name:
        return ""
    return name.strip().lstrip("#").lower()


def channel_allowed(channel_id: str, channel_name: str | None = None) -> bool:
    """Allow #grokbot only. #deals never runs a CMA, even if an ID is pinned to it.

    A configured ``CMA_SLACK_CHANNEL_ID`` is accepted only when the channel name
    is unknown. A known name must be the grokbot channel.
    """
    name = normalize_channel_name(channel_name)
    if name in BLOCKED_CHANNELS:
        return False
    allowed_name = normalize_channel_name(os.environ.get("CMA_SLACK_CHANNEL", DEFAULT_CHANNEL) or DEFAULT_CHANNEL)
    if allowed_name in BLOCKED_CHANNELS:
        allowed_name = DEFAULT_CHANNEL
    if name:
        return name == allowed_name
    pinned = os.environ.get("CMA_SLACK_CHANNEL_ID", "").strip()
    return bool(pinned) and channel_id == pinned


def lookup_channel_name(client, channel_id: str, cache: dict[str, str]) -> str | None:
    """Resolve a Slack channel ID to its name. Failures stay unresolved."""
    if not channel_id:
        return None
    cached = cache.get(channel_id)
    if cached:
        return cached
    try:
        response = client.conversations_info(channel=channel_id)
        name = (response.get("channel") or {}).get("name") or ""
    except Exception:
        return None
    if not name:
        return None
    cache[channel_id] = name
    return name


def build_reply(text: str) -> str:
    try:
        return render_text(analyze(text))
    except CmaError as exc:
        return str(exc)


def main() -> int:
    load_dotenv()
    try:
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler
    except ImportError:
        print("Install the Slack extra first: pip install -e '.[slack]'", file=sys.stderr)
        return 1
    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    app_token = os.environ.get("SLACK_APP_TOKEN")
    if not bot_token or not app_token:
        print("Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN. See .env.example.", file=sys.stderr)
        return 1

    app = App(token=bot_token)
    channel_names: dict[str, str] = {}

    def post_cma(text: str, say, thread_ts: str) -> None:
        say(text="Pulling sold and active comps within 1 mile…", thread_ts=thread_ts)
        try:
            say(text=build_reply(text), thread_ts=thread_ts)
        except Exception:
            traceback.print_exc()
            say(text="The CMA failed unexpectedly. Try again in a few minutes.", thread_ts=thread_ts)

    @app.event("message")
    def on_message(event, say, client, logger):
        if event.get("bot_id") or event.get("subtype"):
            return
        channel_id = event.get("channel") or ""
        text = event.get("text") or ""
        if not message_is_cma(text):
            return
        channel_name = lookup_channel_name(client, channel_id, channel_names)
        if not channel_allowed(channel_id, channel_name):
            logger.info("ignoring /cma in channel %s (%s)", channel_name or "unknown", channel_id)
            return
        thread_ts = event.get("thread_ts") or event.get("ts")
        logger.info("cma command in #%s", channel_name or channel_id)
        post_cma(text, say, thread_ts)

    @app.command("/cma")
    def on_slash(ack, command, respond):
        ack()
        channel_id = command.get("channel_id") or ""
        channel_name = command.get("channel_name") or lookup_channel_name(app.client, channel_id, channel_names)
        if not channel_allowed(channel_id, channel_name):
            respond("This command only runs in #grokbot.")
            return
        address = (command.get("text") or "").strip()
        respond(build_reply(f"/cma {address}"))

    SocketModeHandler(app, app_token).start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
