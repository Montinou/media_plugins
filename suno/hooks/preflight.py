#!/usr/bin/env python3
"""Precondición de autenticación de Suno, al arrancar la sesión.

Puramente local: lee el JSON de cookies y decodifica el JWT. No toca la red —
importante acá, porque cualquier request de script contra Suno es justo lo que
no queremos hacer.

Solo habla cuando hay algo que hacer.
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
    try:
        import suno
    except Exception:
        return 0

    try:
        st = suno.auth_status()
    except Exception:
        # Sin cookies no hay nada que avisar: quizá no se use Suno en esta sesión.
        return 0

    if st["valid"]:
        return 0

    emit(
        "[suno] PRECONDICIÓN NO CUMPLIDA: el token de sesión de Suno está "
        "vencido (no es renovable de forma programática).\n"
        "Si el usuario pide algo de Suno, primero pedile que abra "
        "https://suno.com/ en Chrome con la sesión iniciada — al navegar se "
        "renueva del lado del navegador, que es donde operamos. Si además hace "
        "falta diagnóstico local, que reexporte suno.com.cookies.json.\n"
        "Recordá: nunca armar un cliente HTTP contra Suno."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
