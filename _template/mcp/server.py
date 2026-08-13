#!/usr/bin/env python3
"""Servidor MCP de ejemplo — core reusable.

JSON-RPC 2.0 sobre stdio con la stdlib nada más. Corre tal cual:

    printf '%s\\n' \\
      '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{}}}' \\
      '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \\
      | python3 _template/mcp/server.py

Para hacerlo tuyo: cambiá SERVER_NAME, importá tu lib y reemplazá las tools de
ejemplo. La capa JSON-RPC de abajo no hace falta tocarla.

Todo lo que sea específico de un proyecto (ids, presets, prompts) NO va acá:
va en `packs/<proyecto>/` y se carga por nombre. Ver `packs/README.md`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from service import Service, ServiceAuthError, ServiceError  # noqa: E402

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "example"
SERVER_VERSION = "0.1.0"

TOOLS: list[dict] = []
HANDLERS: dict[str, Callable[[dict], Any]] = {}


def tool(name: str, description: str, schema: dict, **annotations):
    """Registra una tool.

    La `description` la lee un modelo para decidir cuándo usarla: escribí para
    qué sirve y CUÁNDO conviene, no sólo qué hace. Marcá `readOnlyHint=True` en
    todo lo que no escriba ni gaste.
    """

    def deco(fn):
        TOOLS.append(
            {
                "name": name,
                "description": description,
                "inputSchema": {
                    "type": "object",
                    "properties": schema.get("properties", {}),
                    "required": schema.get("required", []),
                },
                "annotations": {"title": annotations.pop("title", name), **annotations},
            }
        )
        HANDLERS[name] = fn
        return fn

    return deco


# ---------------------------------------------------------------------- tools


@tool(
    "example_auth_status",
    "Estado de la sesión: es puramente local, no toca la red ni gasta nada. "
    "Usala SIEMPRE antes de la primera operación de una sesión de trabajo, y "
    "cada vez que otra tool falle por autenticación, para distinguir una cookie "
    "vencida de un problema real.",
    {"properties": {"cookies_path": {"type": "string", "description": "Ruta al JSON de cookies. Opcional."}}},
    title="Estado de sesión",
    readOnlyHint=True,
    openWorldHint=False,
)
def _auth_status(args: dict) -> dict:
    try:
        return Service(args.get("cookies_path")).auth_status()
    except ServiceAuthError as e:
        return {
            "valid": False,
            "problem": str(e),
            "action": "pedirle al usuario que reexporte las cookies",
        }


@tool(
    "example_ping",
    "Ejemplo de tool que sí sale a la red. Reemplazala por la primera operación "
    "real de tu servicio.",
    {"properties": {"cookies_path": {"type": "string"}}},
    title="Ping",
    readOnlyHint=True,
)
def _ping(args: dict) -> dict:
    return Service(args.get("cookies_path")).call("get", "/health")


# -------------------------------------------------------------------- JSON-RPC
# De acá para abajo es infraestructura: sirve igual para cualquier plugin.


def _result(rid, payload):
    return {"jsonrpc": "2.0", "id": rid, "result": payload}


def _text(rid, payload, is_error=False):
    body = {"content": [{"type": "text", "text": payload}]}
    if is_error:
        body["isError"] = True
    return _result(rid, body)


def handle(msg: dict) -> dict | None:
    method = msg.get("method")
    rid = msg.get("id")

    if method == "initialize":
        # Devolvemos la versión que pide el cliente: los hosts van de 2024-11-05
        # a 2025-11-25 y hardcodear una sola rompe con el resto.
        client_proto = (msg.get("params") or {}).get("protocolVersion")
        return _result(
            rid,
            {
                "protocolVersion": client_proto or PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )

    if method and method.startswith("notifications/"):
        return None  # las notificaciones no llevan respuesta

    if method == "ping":
        return _result(rid, {})

    if method == "tools/list":
        return _result(rid, {"tools": TOOLS})

    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        fn = HANDLERS.get(name)
        if fn is None:
            return _text(
                rid,
                f"No existe la tool {name!r}. Disponibles: {', '.join(sorted(HANDLERS))}",
                is_error=True,
            )
        try:
            return _text(
                rid,
                json.dumps(fn(params.get("arguments") or {}), indent=2, ensure_ascii=False),
            )
        except ServiceAuthError as e:
            # Un error de auth es del usuario, no del modelo: decilo con la
            # acción concreta y prohibí el reintento.
            return _text(
                rid,
                f"AUTENTICACIÓN: {e}\n\n"
                "No reintentes ni pruebes otras tools: pedile al usuario que "
                "reexporte las cookies.",
                is_error=True,
            )
        except ServiceError as e:
            return _text(rid, f"Error del servicio: {e}", is_error=True)
        except Exception as e:  # noqa: BLE001
            return _text(rid, f"{type(e).__name__}: {e}", is_error=True)

    return {
        "jsonrpc": "2.0",
        "id": rid,
        "error": {"code": -32601, "message": f"Método no soportado: {method}"},
    }


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
