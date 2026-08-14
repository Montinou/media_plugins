#!/usr/bin/env python3
"""Suno authentication precondition, on session start.

Purely local: reads the cookies JSON and decodes the JWT. Doesn't touch the
network — important here, because any script request against Suno is exactly
what we don't want to do.

Only speaks up when there's something to act on.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))


def emit(context: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                }
            }
        )
    )


def main() -> int:
    try:
        import suno
    except Exception:
        return 0

    try:
        st = suno.auth_status()
    except Exception:
        # No cookies means nothing to warn about: maybe Suno won't be used this session.
        return 0

    if st["valid"]:
        return 0

    emit(
        "[suno] PRECONDITION NOT MET: the Suno session token is "
        "expired (not programmatically renewable).\n"
        "If the user asks for something from Suno, first ask them to open "
        "https://suno.com/ in Chrome with the session logged in — navigating "
        "renews it on the browser side, which is where we operate. If local "
        "diagnostics are also needed, have them re-export suno.com.cookies.json.\n"
        "Remember: never build an HTTP client against Suno."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
