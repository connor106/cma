"""Command line entry: print a CMA for `/cma<address>`."""

from __future__ import annotations

import argparse
import sys
import traceback

from cma.engine import analyze
from cma.errors import CmaError
from cma.report import render_json, render_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pull sold and active comps within 1 mile of an address.",
    )
    parser.add_argument(
        "command",
        help="Slack-style command, for example '/cma428 Lawnview Ave, New Castle, Pennsylvania 16105'",
    )
    parser.add_argument("--json", action="store_true", help="Print the report as JSON")
    args = parser.parse_args(argv)
    try:
        report = analyze(args.command)
    except CmaError as exc:
        print(str(exc))
        return 1
    except Exception:
        traceback.print_exc(file=sys.stderr)
        print("The CMA failed unexpectedly. Try again in a few minutes.")
        return 1
    print(render_json(report) if args.json else render_text(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
