#!/usr/bin/env python3
"""Auth precondition check at session startup.

Purely local: reads the cookies JSON. Doesn't touch the network — a hook
that reaches out to the internet on every startup is exactly what we don't
want.

Only speaks up when there's something to do. If the session is healthy, it
stays quiet.
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
    # No plugin failure should ever break session startup.
    try:
        from service import SERVICE, Service, ServiceAuthError
    except Exception:
        return 0

    try:
        st = Service().auth_status()
    except ServiceAuthError:
        # No cookies, nothing to warn about: the user may not be using this
        # plugin in this session. The tools already explain what to do if
        # invoked.
        return 0
    except Exception:
        return 0

    if st.get("valid"):
        return 0

    emit(
        f"[{SERVICE}] PRECONDITION NOT MET: the session is not valid.\n"
        f"Before using any {SERVICE} tool, ask the user to re-export the "
        f"cookies with the session logged in. Do not try to operate or "
        "retry until they confirm."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
