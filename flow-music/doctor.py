#!/usr/bin/env python3
"""Verifies that the flow-music plugin has everything it needs.

    python3 flow-music/doctor.py

Checks python, ffmpeg, credentials, and the MCP handshake, and explains what
to do about anything missing. Doesn't generate anything, spend credits, or
download anything.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OK, FAIL, WARN = "  ok  ", " fail ", " warn "
problems: list[str] = []


def check(label: str, ok: bool, detail: str = "", fix: str = "", warn: bool = False):
    tag = OK if ok else (WARN if warn else FAIL)
    print(f"[{tag}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        if fix:
            print(f"          → {fix}")
        if not warn:
            problems.append(label)


def main() -> int:
    print(f"flow-music doctor\n{'-' * 60}")
    print(f"\npython {sys.version.split()[0]} ({sys.executable})")
    check(
        "python >= 3.9",
        sys.version_info >= (3, 9),
        fix="The server uses modern type syntax.",
    )

    ffmpeg = shutil.which("ffmpeg")
    check(
        "ffmpeg",
        bool(ffmpeg),
        detail=ffmpeg or "",
        fix="brew install ffmpeg — only needed to verify downloaded stems.",
        warn=True,
    )

    print()
    sys.path.insert(0, str(HERE / "lib"))
    try:
        from flowmusic import FlowMusic, FlowMusicAuthError, find_cookies
    except Exception as e:  # noqa: BLE001
        check("import lib/flowmusic.py", False, detail=str(e))
        return _summary()
    check("import lib/flowmusic.py", True)

    try:
        path = find_cookies()
        check("Flow Music cookies", True, detail=str(path))
        mode = oct(path.stat().st_mode)[-3:]
        check(
            "cookie permissions",
            mode == "600",
            detail=f"mode {mode}",
            fix=f"chmod 600 '{path}' — it's a full session.",
            warn=True,
        )
    except FlowMusicAuthError as e:
        check(
            "Flow Music cookies",
            False,
            detail=str(e).split(".")[0],
            fix="Export the cookies from www.flowmusic.app while logged in to "
            "~/.config/flowmusic/cookies.json",
        )
        return _summary()

    try:
        st = FlowMusic().auth_status()
        mins = st["expires_in_seconds"] // 60
        if st["valid"]:
            check("session", True, detail=f"{st['email']}, expires in {mins} min")
        elif st["can_refresh"]:
            check(
                "session",
                True,
                detail="token expired but self-renewable (has refresh_token)",
            )
        else:
            check(
                "session",
                False,
                detail="expired and no refresh_token",
                fix="Re-export the cookies from www.flowmusic.app.",
            )
    except Exception as e:  # noqa: BLE001
        check("session", False, detail=str(e))

    print()
    try:
        proc = subprocess.run(
            [sys.executable, str(HERE / "mcp" / "server.py")],
            input='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{}}}\n'
            '{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n',
            capture_output=True,
            text=True,
            timeout=30,
        )
        lines = [json.loads(x) for x in proc.stdout.splitlines() if x.strip()]
        tools = next((m["result"]["tools"] for m in lines if "tools" in m.get("result", {})), [])
        check("MCP handshake", bool(tools), detail=f"{len(tools)} tools")
        for t in tools:
            print(f"            · {t['name']}")
    except Exception as e:  # noqa: BLE001
        check("MCP handshake", False, detail=str(e))

    return _summary()


def _summary() -> int:
    print(f"\n{'-' * 60}")
    if problems:
        print(f"missing {len(problems)}: {', '.join(problems)}")
        return 1
    print("all good")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
