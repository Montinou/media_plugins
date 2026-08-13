#!/usr/bin/env python3
"""Verifica que el plugin tenga todo lo que necesita.

    python3 _template/doctor.py

Revisa python, credenciales y el handshake del MCP, y explica qué hacer con
cada cosa que falte. No genera nada, no gasta créditos y no descarga nada.

Al adaptar el template, cambiá el nombre del título y agregá los chequeos de las
dependencias reales de tu plugin (ffmpeg, Chrome, playwright, lo que use).
"""
from __future__ import annotations

import json
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
    print(f"{HERE.name} doctor\n{'-' * 60}")
    print(f"\npython {sys.version.split()[0]} ({sys.executable})")
    check("python >= 3.9", sys.version_info >= (3, 9))

    print()
    sys.path.insert(0, str(HERE / "lib"))
    try:
        from service import SERVICE, Service, ServiceAuthError, find_cookies
    except Exception as e:  # noqa: BLE001
        check("importar lib/service.py", False, detail=str(e))
        return _summary()
    check("importar lib/service.py", True)

    try:
        path = find_cookies()
        check("credenciales", True, detail=str(path))
        mode = oct(path.stat().st_mode)[-3:]
        check(
            "permisos",
            mode == "600",
            detail=f"modo {mode}",
            fix=f"chmod 600 '{path}' — es una sesión completa.",
            warn=True,
        )
        st = Service().auth_status()
        check("sesión", bool(st.get("valid")), fix="Reexportá las cookies.")
    except ServiceAuthError as e:
        check(
            "credenciales",
            False,
            detail=str(e).split(".")[0],
            fix=f"Exportá las cookies de {SERVICE} a ~/.config/{SERVICE}/cookies.json",
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
