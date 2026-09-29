"""Slack listener for `/cma<address>` messages in the grokbot channel.

Socket Mode keeps the bot outbound-only: no public request URL. Invite the app
to the grokbot channel and it replies in a thread.
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


def channel_allowed(channel_id: str) -> bool:
    """Honor CMA_SLACK_CHANNEL_ID when set. Empty means every channel the bot is in."""
    allowed = os.environ.get("CMA_SLACK_CHANNEL_ID", "").strip()
    return not allowed or channel_id == allowed


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

    def post_cma(text: str, say, thread_ts: str) -> None:
        say(text="Pulling sold and active comps within 1 mile…", thread_ts=thread_ts)
        try:
            say(text=build_reply(text), thread_ts=thread_ts)
        except Exception:
            traceback.print_exc()
            say(text="The CMA failed unexpectedly. Try again in a few minutes.", thread_ts=thread_ts)

    @app.event("message")
    def on_message(event, say, logger):
        if event.get("bot_id") or event.get("subtype"):
            return
        text = event.get("text") or ""
        if not message_is_cma(text) or not channel_allowed(event.get("channel") or ""):
            return
        thread_ts = event.get("thread_ts") or event.get("ts")
        logger.info("cma command in %s", event.get("channel"))
        post_cma(text, say, thread_ts)

    @app.command("/cma")
    def on_slash(ack, command, respond):
        ack()
        if not channel_allowed(command.get("channel_id") or ""):
            respond("This command is limited to the grokbot channel.")
            return
        address = (command.get("text") or "").strip()
        respond(build_reply(f"/cma {address}"))

    SocketModeHandler(app, app_token).start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
