#!/usr/bin/env python3
"""Precondición de autenticación de Flow Music, al arrancar la sesión.

Es puramente local: lee el JSON de cookies y decodifica el JWT. No toca la red,
así que no cuesta nada ni delata actividad. Solo habla cuando hay algo que
hacer — si la sesión está sana, se calla.
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
        from flowmusic import FlowMusic, FlowMusicAuthError
    except Exception:
        return 0  # el plugin no debe romper la sesión por un problema propio

    try:
        st = FlowMusic().auth_status()
    except FlowMusicAuthError:
        # Sin cookies no hay nada que avisar: el usuario quizá no use el plugin
        # en esta sesión. Las tools ya explican qué hacer si las invoca.
        return 0
    except Exception:
        return 0

    if st["valid"]:
        return 0

    if st["can_refresh"]:
        emit(
            "[flowmusic] El access_token de Flow Music está vencido, pero hay "
            "refresh_token: las tools lo renuevan solas en la primera llamada. "
            "No hace falta molestar al usuario."
        )
        return 0

    emit(
        "[flowmusic] PRECONDICIÓN NO CUMPLIDA: la sesión de Flow Music venció y "
        "no se puede renovar sola.\n"
        "Antes de usar cualquier tool `flowmusic_*`, pedile al usuario que "
        "reexporte las cookies de www.flowmusic.app (con la sesión iniciada) a "
        "`www.flowmusic.app.cookies.json` en la raíz del repo. No intentes "
        "operar ni reintentar hasta que confirme."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
