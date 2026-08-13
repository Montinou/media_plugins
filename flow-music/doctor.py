#!/usr/bin/env python3
"""Verifica que el plugin flow-music tenga todo lo que necesita.

    python3 flow-music/doctor.py

Revisa python, ffmpeg, credenciales y el handshake del MCP, y explica qué hacer
con cada cosa que falte. No genera nada, no gasta créditos y no descarga nada.
"""
from __future__ import annotations

import json
import os
import shutil
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
    print(f"flow-music doctor\n{'-' * 60}")
    print(f"\npython {sys.version.split()[0]} ({sys.executable})")
    check(
        "python >= 3.9",
        sys.version_info >= (3, 9),
        fix="El servidor usa sintaxis moderna de tipos.",
    )

    ffmpeg = shutil.which("ffmpeg")
    check(
        "ffmpeg",
        bool(ffmpeg),
        detail=ffmpeg or "",
        fix="brew install ffmpeg — solo hace falta para verificar stems descargados.",
        warn=True,
    )

    print()
    sys.path.insert(0, str(HERE / "lib"))
    try:
        from flowmusic import FlowMusic, FlowMusicAuthError, find_cookies
    except Exception as e:  # noqa: BLE001
        check("importar lib/flowmusic.py", False, detail=str(e))
        return _summary()
    check("importar lib/flowmusic.py", True)

    try:
        path = find_cookies()
        check("cookies de Flow Music", True, detail=str(path))
        mode = oct(path.stat().st_mode)[-3:]
        check(
            "permisos de las cookies",
            mode == "600",
            detail=f"modo {mode}",
            fix=f"chmod 600 '{path}' — es una sesión completa.",
            warn=True,
        )
    except FlowMusicAuthError as e:
        check(
            "cookies de Flow Music",
            False,
            detail=str(e).split(".")[0],
            fix="Exportá las cookies de www.flowmusic.app logueado a "
            "~/.config/flowmusic/cookies.json",
        )
        return _summary()

    try:
        st = FlowMusic().auth_status()
        mins = st["expires_in_seconds"] // 60
        if st["valid"]:
            check("sesión", True, detail=f"{st['email']}, vence en {mins} min")
        elif st["can_refresh"]:
            check(
                "sesión",
                True,
                detail="token vencido pero renovable solo (hay refresh_token)",
            )
        else:
            check(
                "sesión",
                False,
                detail="vencida y sin refresh_token",
                fix="Reexportá las cookies de www.flowmusic.app.",
            )
    except Exception as e:  # noqa: BLE001
        check("sesión", False, detail=str(e))

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
        check("handshake del MCP", bool(tools), detail=f"{len(tools)} tools")
        for t in tools:
            print(f"            · {t['name']}")
    except Exception as e:  # noqa: BLE001
        check("handshake del MCP", False, detail=str(e))

    return _summary()


def _summary() -> int:
    print(f"\n{'-' * 60}")
    if problems:
        print(f"faltan {len(problems)}: {', '.join(problems)}")
        return 1
    print("todo en orden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
