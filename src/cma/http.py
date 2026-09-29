"""Small HTTP GET helper with one retry on transient failures."""

from __future__ import annotations

import time
import urllib.error
import urllib.request

from cma.errors import CmaError

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)


def http_get(url: str, timeout: float = 30.0) -> str:
    """GET ``url`` and return the body as text.

    Retries once on a timeout, connection error, or 429/5xx response.
    """
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in {429, 500, 502, 503, 504} and attempt == 0:
                time.sleep(1.0)
                continue
            if exc.code in {403, 429}:
                raise CmaError(
                    "The listing service blocked the request. Try again in a few minutes."
                ) from exc
            raise CmaError(
                f"The listing service returned an error ({exc.code}). Try again in a few minutes."
            ) from exc
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(1.0)
                continue
            raise CmaError("Couldn't reach the listing service. Try again in a few minutes.") from exc
    raise CmaError("Couldn't reach the listing service. Try again in a few minutes.") from last_error
