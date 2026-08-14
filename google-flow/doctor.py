#!/usr/bin/env python3
"""Checks that the plugin has everything it needs to work.

    python3 google-flow/doctor.py

Checks dependencies, Chrome, credentials, and the MCP handshake, and explains
what to do about anything missing. Generates nothing and spends no credits.
"""
from __future__ import annotations

import json
import os
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
    print(f"google-flow doctor\n{'-' * 60}")

    print(f"\npython {sys.version.split()[0]} ({sys.executable})")
    for mod, pkg in [("playwright", "playwright"), ("requests", "requests"), ("PIL", "pillow")]:
        try:
            __import__(mod)
            check(f"module {mod}", True)
        except ImportError:
            check(
                f"module {mod}",
                False,
                "not installed",
                f"pip install {pkg}  (if PEP 668 blocks it: pipx or a venv)",
            )

    chrome = Path("/Applications/Google Chrome.app")
    check(
        "Google Chrome",
        chrome.exists(),
        str(chrome) if chrome.exists() else "",
        "install Chrome: the driver uses channel='chrome'",
    )

    print()
    sys.path.insert(0, str(HERE / "lib"))
    try:
        import flow_client

        check("libraries in lib/", True)
    except Exception as e:
        check("libraries in lib/", False, str(e)[:80])
        return _summary()

    cookies = flow_client.COOKIE_PATH
    if cookies.exists():
        mode = oct(cookies.stat().st_mode)[-3:]
        check("labs.google cookies", True, str(cookies))
        check(
            "cookie file permissions",
            mode == "600",
            f"mode {mode}",
            f"chmod 600 {cookies}",
            warn=True,
        )
    else:
        check(
            "labs.google cookies",
            False,
            f"not found at {cookies}",
            "export the labs.google cookies from the browser to that path",
        )
        return _summary()

    try:
        info = flow_client.session_info()
        user = info.get("user", {}).get("email")
        # session_info() no valida el vencimiento; access_token() sí, y es lo
        # que usan todas las tools. Se chequea acá para que el doctor falle en
        # el mismo lugar donde fallaría el trabajo real.
        flow_client.access_token(force_refresh=True)
        check("Flow session", True, f"{user} · expires {info.get('expires')}")
        credits = flow_client.sandbox("GET", "credits").get("credits")
        check("credits", True, f"{credits} available")
    except flow_client.FlowAuthError as e:
        check("Flow session", False, str(e)[:110], "re-export the cookies")
    except Exception as e:
        check("Flow session", False, str(e)[:110], "re-export the cookies")

    print()
    handshake = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "doctor", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    proc = subprocess.run(
        [sys.executable, str(HERE / "mcp" / "server.py")],
        input="\n".join(json.dumps(m) for m in handshake) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
    )
    tools = []
    for line in proc.stdout.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == 2:
            tools = msg.get("result", {}).get("tools", [])
    check(
        "MCP server",
        bool(tools),
        f"{len(tools)} tools" if tools else proc.stderr.strip()[-200:],
        "check the error above",
    )

    return _summary()


def _summary() -> int:
    print(f"\n{'-' * 60}")
    if problems:
        print(f"{len(problems)} problem(s): {', '.join(problems)}")
        return 1
    print("everything's in order")
    return 0


if __name__ == "__main__":
    sys.exit(main())
