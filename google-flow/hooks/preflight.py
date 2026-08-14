#!/usr/bin/env python3
"""Google Flow session precondition, run at session start.

Purely local: reads the cookies JSON and checks the session deadline the
NextAuth cookie carries. It never touches the network, so it costs nothing and
gives away no activity. It only speaks up when there is something to do — a
healthy session stays quiet.

The check exists because the failure it prevents is expensive to diagnose:
`/api/auth/session` keeps handing out an access_token after the session
expires, so the first symptom is an opaque 401 from googleapis in the middle
of a batch, long after the credentials could have been refreshed.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
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
        import flow_client
    except Exception:
        return 0  # the plugin's libs aren't reachable; nothing useful to say

    path = flow_client.COOKIE_PATH
    if not path.exists():
        emit(
            "Google Flow: no cookies found at "
            f"{path}. The google-flow tools will fail until labs.google cookies "
            "are exported there (any filename with those words works). "
            "Check with the plugin's doctor.py — it spends nothing."
        )
        return 0

    try:
        raw = json.loads(path.read_text())
    except Exception:
        emit(f"Google Flow: {path} isn't readable as JSON. Re-export the cookies.")
        return 0

    session = next(
        (c for c in raw if c.get("name") == "__Secure-next-auth.session-token"), None
    )
    if session is None:
        emit(
            f"Google Flow: {path} has no __Secure-next-auth.session-token. "
            "It's probably an export from the wrong site or an incomplete one."
        )
        return 0

    expires = session.get("expirationDate") or session.get("expires")
    if isinstance(expires, (int, float)) and expires > 0:
        left = datetime.fromtimestamp(expires, timezone.utc) - datetime.now(timezone.utc)
        hours = left.total_seconds() / 3600
        if hours <= 0:
            emit(
                f"Google Flow: the session expired {abs(int(hours))}h ago. "
                f"Re-export the labs.google cookies to {path.parent}/ before "
                "generating anything — every tool will fail with a 401 that "
                "doesn't name the cause."
            )
        elif hours < 2:
            emit(
                f"Google Flow: the session expires in about {hours:.1f}h. "
                "Long batches may not finish; consider refreshing the cookies first."
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
