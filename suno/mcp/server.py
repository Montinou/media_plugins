#!/usr/bin/env python3
"""Servidor MCP para Suno.

JSON-RPC 2.0 sobre stdio con la stdlib nada más (PEP 668: no queremos forzar
`--break-system-packages` en el Python del sistema).

**Ninguna tool de este server toca la red de Suno, y es deliberado.** Suno está
detrás de Cloudflare, sus ToS prohíben el acceso automatizado, y el export de
cookies del navegador no incluye `__client`, así que ni siquiera se podría
renovar el token. Lo que Suno necesita se hace por navegador con la sesión del
usuario; acá vive el diagnóstico local y la verificación de lo descargado.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import suno  # noqa: E402
from suno import SunoAuthError, SunoError  # noqa: E402

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "suno"
SERVER_VERSION = "0.1.0"

TOOLS: list[dict] = []
HANDLERS: dict[str, Callable[[dict], Any]] = {}


def tool(name: str, description: str, schema: dict, **annotations):
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
    "suno_auth_status",
    "Estado de la sesión de Suno: handle, plan y cuánto le queda al token. Es "
    "puramente local — lee el JSON de cookies y decodifica el JWT, sin tocar la "
    "red. Usala antes de mandar al usuario a operar en el navegador, para saber "
    "si va a encontrarse la sesión caída. También reporta si la sesión sería "
    "renovable de forma programática (casi siempre no).",
    {"properties": {"cookies_path": {"type": "string", "description": "Ruta al JSON de cookies. Opcional."}}},
    title="Estado de sesión",
    readOnlyHint=True,
    openWorldHint=False,
)
def _auth_status(args: dict) -> dict:
    st = suno.auth_status(args.get("cookies_path"))
    if not st["valid"]:
        st["action"] = (
            "La sesión venció. Pedile al usuario que reexporte las cookies de "
            "suno.com, o simplemente que abra suno.com en Chrome (al navegar se "
            "renueva sola del lado del navegador, que es donde vamos a operar)."
        )
    return st


@tool(
    "suno_inspect_multitrack",
    "Analiza un zip de 'Export → Multitrack' de Suno Studio SIN extraerlo: qué "
    "tracks trae, cuánto pesa cada uno, si están alineados y qué stems faltan. "
    "Es local y barato. Usala apenas termina una descarga, antes de decirle al "
    "usuario que salió bien.",
    {
        "properties": {
            "zip_path": {"type": "string", "description": "Ruta al .zip exportado."}
        },
        "required": ["zip_path"],
    },
    title="Inspeccionar multitrack",
    readOnlyHint=True,
    openWorldHint=False,
)
def _inspect(args: dict) -> dict:
    return suno.inspect_multitrack(args["zip_path"])


@tool(
    "suno_verify_stem",
    "Mide la energía RMS por debajo y por encima de un corte (250 Hz por "
    "defecto) de un archivo de audio, para verificar que un stem contenga lo que "
    "su nombre promete: el bass debe dominar en graves, las voces en agudos. "
    "Local, vía ffmpeg. Nunca reproduce audio.",
    {
        "properties": {
            "path": {"type": "string", "description": "Ruta al archivo de audio."},
            "split_hz": {"type": "integer", "description": "Frecuencia de corte. Default 250."},
        },
        "required": ["path"],
    },
    title="Verificar stem",
    readOnlyHint=True,
    openWorldHint=False,
)
def _verify(args: dict) -> dict:
    return suno.band_energy(args["path"], int(args.get("split_hz") or 250))


# -------------------------------------------------------------------- JSON-RPC


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
        return None

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
        except SunoAuthError as e:
            return _text(
                rid,
                f"AUTENTICACIÓN: {e}\n\n"
                "En Suno no hay renovación programática. Pedile al usuario que "
                "reexporte las cookies de suno.com, o que abra suno.com en "
                "Chrome si vamos a operar por navegador.",
                is_error=True,
            )
        except SunoError as e:
            return _text(rid, f"Error de Suno: {e}", is_error=True)
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
