#!/usr/bin/env python3
"""Checks that the suno plugin has everything it needs.

    python3 suno/doctor.py

Checks python, ffmpeg, credentials, and the MCP handshake. All local: this
plugin doesn't make requests to Suno, not even to diagnose.
"""
from __future__ import annotations

import json
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
    print(f"suno doctor\n{'-' * 60}")
    print(f"\npython {sys.version.split()[0]} ({sys.executable})")
    check("python >= 3.9", sys.version_info >= (3, 9))

    for binname, why in (("ffmpeg", "verifying stems"), ("ffprobe", "reading format")):
        p = shutil.which(binname)
        check(binname, bool(p), detail=p or "", fix=f"brew install ffmpeg — needed for {why}.", warn=True)

    print()
    sys.path.insert(0, str(HERE / "lib"))
    try:
        import suno
        from suno import SunoAuthError, find_cookies
    except Exception as e:  # noqa: BLE001
        check("import lib/suno.py", False, detail=str(e))
        return _summary()
    check("import lib/suno.py", True)

    try:
        path = find_cookies()
        check("Suno cookies", True, detail=str(path))
        mode = oct(path.stat().st_mode)[-3:]
        check(
            "cookie permissions",
            mode == "600",
            detail=f"mode {mode}",
            fix=f"chmod 600 '{path}' — it's a full session.",
            warn=True,
        )
    except SunoAuthError as e:
        check(
            "Suno cookies",
            False,
            detail=str(e).split(".")[0],
            fix="Export logged-in suno.com cookies to ~/.config/suno/cookies.json. "
            "Not required if you're only operating via browser.",
            warn=True,
        )
        return _summary()

    try:
        st = suno.auth_status()
        mins = st["expires_in_seconds"] // 60
        check(
            "session",
            st["valid"],
            detail=f"{st.get('handle')}, expires in {mins} min" if st["valid"] else "expired",
            fix="Open https://suno.com/ logged in on Chrome: it renews itself on "
            "the browser side, which is where we operate.",
            warn=True,
        )
        check(
            "programmatic renewal",
            False,
            detail=f"can_refresh={st['can_refresh']}, cf_clearance={st['has_cf_clearance']}",
            fix="Expected: without Clerk's __client there's no refresh, and without "
            "cf_clearance a script runs into Cloudflare. That's why we operate via browser.",
            warn=True,
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
        print(f"{len(problems)} missing: {', '.join(problems)}")
        return 1
    print("all good")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
