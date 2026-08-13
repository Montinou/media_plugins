#!/usr/bin/env python3
"""Verifica que el plugin suno tenga todo lo que necesita.

    python3 suno/doctor.py

Revisa python, ffmpeg, credenciales y el handshake del MCP. Todo local: este
plugin no le hace requests a Suno, ni siquiera para diagnosticar.
"""
from __future__ import annotations

import json
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
    print(f"suno doctor\n{'-' * 60}")
    print(f"\npython {sys.version.split()[0]} ({sys.executable})")
    check("python >= 3.9", sys.version_info >= (3, 9))

    for binname, why in (("ffmpeg", "verificar stems"), ("ffprobe", "leer formato")):
        p = shutil.which(binname)
        check(binname, bool(p), detail=p or "", fix=f"brew install ffmpeg — hace falta para {why}.", warn=True)

    print()
    sys.path.insert(0, str(HERE / "lib"))
    try:
        import suno
        from suno import SunoAuthError, find_cookies
    except Exception as e:  # noqa: BLE001
        check("importar lib/suno.py", False, detail=str(e))
        return _summary()
    check("importar lib/suno.py", True)

    try:
        path = find_cookies()
        check("cookies de Suno", True, detail=str(path))
        mode = oct(path.stat().st_mode)[-3:]
        check(
            "permisos de las cookies",
            mode == "600",
            detail=f"modo {mode}",
            fix=f"chmod 600 '{path}' — es una sesión completa.",
            warn=True,
        )
    except SunoAuthError as e:
        check(
            "cookies de Suno",
            False,
            detail=str(e).split(".")[0],
            fix="Exportá las cookies de suno.com logueado a ~/.config/suno/cookies.json. "
            "Para operar sólo por navegador no son imprescindibles.",
            warn=True,
        )
        return _summary()

    try:
        st = suno.auth_status()
        mins = st["expires_in_seconds"] // 60
        check(
            "sesión",
            st["valid"],
            detail=f"{st.get('handle')}, vence en {mins} min" if st["valid"] else "vencida",
            fix="Abrí https://suno.com/ logueado en Chrome: se renueva sola del "
            "lado del navegador, que es donde operamos.",
            warn=True,
        )
        check(
            "renovación programática",
            False,
            detail=f"can_refresh={st['can_refresh']}, cf_clearance={st['has_cf_clearance']}",
            fix="Esperado: sin __client de Clerk no hay refresh, y sin cf_clearance "
            "un script choca con Cloudflare. Por eso se opera por navegador.",
            warn=True,
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
