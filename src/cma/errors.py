"""User-facing errors. The message is safe to post back to Slack."""


class CmaError(Exception):
    """The analysis could not be completed. ``str(exc)`` is the reply."""
