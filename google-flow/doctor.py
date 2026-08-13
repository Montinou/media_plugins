#!/usr/bin/env python3
"""Verifica que el plugin tenga todo lo que necesita para funcionar.

    python3 google-flow/doctor.py

Revisa dependencias, Chrome, credenciales y el handshake del MCP, y explica qué
hacer con cada cosa que falte. No genera nada ni gasta créditos.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OK, FAIL, WARN = "  ok  ", " falta", " aviso"
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
            check(f"módulo {mod}", True)
        except ImportError:
            check(
                f"módulo {mod}",
                False,
                "no instalado",
                f"pip install {pkg}  (si PEP 668 lo bloquea: pipx o un venv)",
            )

    chrome = Path("/Applications/Google Chrome.app")
    check(
        "Google Chrome",
        chrome.exists(),
        str(chrome) if chrome.exists() else "",
        "instalar Chrome: el driver usa channel='chrome'",
    )

    print()
    sys.path.insert(0, str(HERE / "lib"))
    try:
        import flow_client

        check("bibliotecas en lib/", True)
    except Exception as e:
        check("bibliotecas en lib/", False, str(e)[:80])
        return _summary()

    cookies = flow_client.COOKIE_PATH
    if cookies.exists():
        mode = oct(cookies.stat().st_mode)[-3:]
        check("cookies de labs.google", True, str(cookies))
        check(
            "permisos de las cookies",
            mode == "600",
            f"modo {mode}",
            f"chmod 600 {cookies}",
            warn=True,
        )
    else:
        check(
            "cookies de labs.google",
            False,
            f"no están en {cookies}",
            "exportar las cookies de labs.google desde el navegador a esa ruta",
        )
        return _summary()

    try:
        info = flow_client.session_info()
        check(
            "sesión de Flow",
            bool(info.get("access_token")),
            f"{info.get('user', {}).get('email')} · vence {info.get('expires')}",
            "la cookie venció: reexportarla desde el navegador",
        )
        credits = flow_client.sandbox("GET", "credits").get("credits")
        check("créditos", True, f"{credits} disponibles")
    except Exception as e:
        check("sesión de Flow", False, str(e)[:100], "reexportar las cookies")

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
        "servidor MCP",
        bool(tools),
        f"{len(tools)} tools" if tools else proc.stderr.strip()[-200:],
        "revisar el error de arriba",
    )

    return _summary()


def _summary() -> int:
    print(f"\n{'-' * 60}")
    if problems:
        print(f"{len(problems)} problema(s): {', '.join(problems)}")
        return 1
    print("todo en orden")
    return 0


if __name__ == "__main__":
    sys.exit(main())
