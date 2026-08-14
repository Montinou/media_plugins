#!/usr/bin/env python3
"""Flow Music authentication precondition, run at session start.

Purely local: reads the cookies JSON and decodes the JWT. Doesn't touch the
network, so it costs nothing and gives away no activity. Only speaks up when
there's something to do — if the session is healthy, it stays quiet.
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
        from flowmusic import FlowMusic, FlowMusicAuthError
    except Exception:
        return 0  # the plugin shouldn't break the session over its own problem

    try:
        st = FlowMusic().auth_status()
    except FlowMusicAuthError:
        # No cookies means there's nothing to warn about: the user may not
        # use the plugin in this session. The tools already explain what to
        # do if invoked.
        return 0
    except Exception:
        return 0

    if st["valid"]:
        return 0

    if st["can_refresh"]:
        emit(
            "[flowmusic] Flow Music's access_token has expired, but there's a "
            "refresh_token: the tools will renew it themselves on the next "
            "call. No need to bother the user."
        )
        return 0

    emit(
        "[flowmusic] PRECONDITION NOT MET: the Flow Music session expired and "
        "can't refresh itself.\n"
        "Before using any `flowmusic_*` tool, ask the user to re-export the "
        "cookies from www.flowmusic.app (while logged in) to "
        "`www.flowmusic.app.cookies.json` at the repo root. Don't try to "
        "operate or retry until they confirm."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
