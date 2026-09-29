"""Parse a grokbot Slack message into a street address."""

from __future__ import annotations

import re

from cma.errors import CmaError

# `/cma` may be glued to the street number (`/cma428 Lawnview Ave, ...`),
# separated by a space, or separated by a colon.
_COMMAND = re.compile(r"^\s*/cma(?:\s+|:|(?=\d))(.+?)\s*$", re.IGNORECASE)
_MENTION = re.compile(r"<@[A-Z0-9]+>")


def parse_command(text: str) -> str:
    """Return the address from a `/cma...` message.

    Raises ``CmaError`` when the text is not a CMA command or has no address.
    """
    if not text or not text.strip():
        raise CmaError(
            "Send an address after /cma, for example "
            "`/cma428 Lawnview Ave, New Castle, Pennsylvania 16105`."
        )
    cleaned = _MENTION.sub(" ", text).strip()
    cleaned = cleaned.strip("`*_ ")
    match = _COMMAND.match(cleaned)
    if match is None:
        raise CmaError(
            "Send an address after /cma, for example "
            "`/cma428 Lawnview Ave, New Castle, Pennsylvania 16105`."
        )
    address = match.group(1).strip().strip("`").strip()
    address = re.sub(r"\s+", " ", address)
    if len(address) < 8 or not re.search(r"\d", address):
        raise CmaError(
            "That doesn't look like a street address. Include the number, street, city, and state, "
            "for example `/cma428 Lawnview Ave, New Castle, Pennsylvania 16105`."
        )
    if len(address) > 200:
        raise CmaError("That address is too long. Send just the street, city, and state.")
    return address
