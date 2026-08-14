#!/usr/bin/env python3
"""Verifies the plugin has everything it needs.

    python3 _template/doctor.py

Checks python, credentials, and the MCP handshake, and explains what to do
about anything missing. Generates nothing, spends no credits, and downloads
nothing.

When adapting the template, change the title name and add checks for your
plugin's real dependencies (ffmpeg, Chrome, playwright, whatever it uses).
"""
from __future__ import annotations

import json
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
    print(f"{HERE.name} doctor\n{'-' * 60}")
    print(f"\npython {sys.version.split()[0]} ({sys.executable})")
    check("python >= 3.9", sys.version_info >= (3, 9))

    print()
    sys.path.insert(0, str(HERE / "lib"))
    try:
        from service import SERVICE, Service, ServiceAuthError, find_cookies
    except Exception as e:  # noqa: BLE001
        check("import lib/service.py", False, detail=str(e))
        return _summary()
    check("import lib/service.py", True)

    try:
        path = find_cookies()
        check("credentials", True, detail=str(path))
        mode = oct(path.stat().st_mode)[-3:]
        check(
            "permissions",
            mode == "600",
            detail=f"mode {mode}",
            fix=f"chmod 600 '{path}' — it's a full session.",
            warn=True,
        )
        st = Service().auth_status()
        check("session", bool(st.get("valid")), fix="Re-export the cookies.")
    except ServiceAuthError as e:
        check(
            "credentials",
            False,
            detail=str(e).split(".")[0],
            fix=f"Export {SERVICE}'s cookies to ~/.config/{SERVICE}/cookies.json",
            warn=True,
        )

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
