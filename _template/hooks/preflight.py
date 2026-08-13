#!/usr/bin/env python3
"""Precondición de autenticación al arrancar la sesión.

Puramente local: lee el JSON de cookies. No toca la red — un hook que sale a
internet en cada arranque es exactamente lo que no queremos.

Sólo habla cuando hay algo que hacer. Si la sesión está sana, se calla.
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
    # Ningún fallo del plugin debe romper el arranque de la sesión.
    try:
        from service import SERVICE, Service, ServiceAuthError
    except Exception:
        return 0

    try:
        st = Service().auth_status()
    except ServiceAuthError:
        # Sin cookies no hay nada que avisar: quizá el usuario no use este
        # plugin en esta sesión. Las tools ya explican qué hacer si lo invoca.
        return 0
    except Exception:
        return 0

    if st.get("valid"):
        return 0

    emit(
        f"[{SERVICE}] PRECONDICIÓN NO CUMPLIDA: la sesión no es válida.\n"
        f"Antes de usar cualquier tool de {SERVICE}, pedile al usuario que "
        f"reexporte las cookies con la sesión iniciada. No intentes operar ni "
        "reintentar hasta que confirme."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
