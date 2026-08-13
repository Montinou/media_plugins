#!/usr/bin/env python3
"""Servidor MCP para Google Flow Music.

JSON-RPC 2.0 sobre stdio con la stdlib nada más: el Python de Homebrew está
bajo PEP 668 e instalar el SDK oficial obligaría a `--break-system-packages`.

Convención de este marketplace:
la lib se resuelve desde el plugin, y los errores de autenticación se
devuelven como `isError` con instrucciones para el usuario — nunca se
reintenta contra el servicio.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import flowmusic  # noqa: E402
from flowmusic import FlowMusic, FlowMusicAuthError, FlowMusicError  # noqa: E402

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "flow-music"
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


def _client(args: dict) -> FlowMusic:
    return FlowMusic(
        args.get("cookies_path"),
        min_interval=float(os.environ.get("FLOWMUSIC_MIN_INTERVAL", "2.5")),
    )


def _default_outdir() -> Path:
    return Path(os.environ.get("FLOWMUSIC_OUT", Path.home() / "Downloads")).expanduser()


# ---------------------------------------------------------------------- tools


@tool(
    "flowmusic_auth_status",
    "Estado de la sesión de Flow Music: a quién pertenece, cuánto le queda y si "
    "puede renovarse sola. Es puramente local — no toca la red ni gasta nada. "
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
        st = _client(args).auth_status()
    except FlowMusicAuthError as e:
        return {"valid": False, "problem": str(e), "action": "pedirle al usuario que reexporte las cookies"}
    if not st["valid"] and st["can_refresh"]:
        st["action"] = "el token venció pero hay refresh_token: se renueva solo en la próxima llamada"
    elif not st["valid"]:
        st["action"] = "pedirle al usuario que reexporte las cookies de www.flowmusic.app"
    return st


@tool(
    "flowmusic_account",
    "Cuenta y saldo: usuario y créditos disponibles. El contador que muestra el "
    "sidebar de la web es el cupo diario gratis, NO el saldo — el saldo real es "
    "`credits_remaining`. Consultala antes de proponer generar música, para no "
    "sobreestimar ni subestimar lo que hay.",
    {"properties": {"cookies_path": {"type": "string"}}},
    title="Cuenta y créditos",
    readOnlyHint=True,
)
def _account(args: dict) -> dict:
    fm = _client(args)
    return {"user": fm.me(), "credits": fm.credits()}


@tool(
    "flowmusic_list_songs",
    "Canciones del usuario, las más recientes primero: id, título, tipo de "
    "operación y duración. Sirve para encontrar el clip_id de un tema antes de "
    "bajarlo o de separarle stems.",
    {
        "properties": {
            "limit": {"type": "integer", "description": "Máximo a devolver (default 20)."},
            "cookies_path": {"type": "string"},
        }
    },
    title="Listar canciones",
    readOnlyHint=True,
)
def _list_songs(args: dict) -> dict:
    fm = _client(args)
    limit = int(args.get("limit") or 20)
    songs = [
        {
            "clip_id": c["id"],
            "title": c.get("title"),
            "op_type": c.get("op_type"),
            "duration": c.get("duration"),
            "created_at": c.get("created_at"),
        }
        for c in fm.clips()
        if c.get("op_type") != "audio__split_stems"
    ]
    return {"count": len(songs[:limit]), "songs": songs[:limit]}


@tool(
    "flowmusic_list_stems",
    "Temas que YA tienen stems separados, con qué stems tiene cada uno. "
    "Flow Music no separa solo: si un tema no aparece acá, hay que abrir la web "
    "y correrle 'Split stems' primero (eso no lo puede hacer esta tool).",
    {"properties": {"cookies_path": {"type": "string"}}},
    title="Temas con stems",
    readOnlyHint=True,
)
def _list_stems(args: dict) -> dict:
    fm = _client(args)
    songs = fm.songs_with_stems()
    return {
        "count": len(songs),
        "songs": [
            {
                "source_clip_id": src,
                "title": i["title"],
                "stems": sorted(i["stems"], key=lambda s: flowmusic.STEM_ORDER.get(s, 9)),
            }
            for src, i in songs.items()
        ],
        "note": "Si falta un tema, correle 'Split stems' en la UI de Flow Music.",
    }


@tool(
    "flowmusic_stem_urls",
    "URLs de descarga de los stems de un tema, SIN bajar nada. Barato y sin "
    "efectos: úsala para mostrarle al usuario qué se va a bajar antes de "
    "gastar ancho de banda, o para verificar que el bass está disponible.",
    {
        "properties": {
            "song": {"type": "string", "description": "source_clip_id o parte del título."},
            "cookies_path": {"type": "string"},
        },
        "required": ["song"],
    },
    title="URLs de stems",
    readOnlyHint=True,
)
def _stem_urls(args: dict) -> dict:
    return _client(args).stem_urls(args["song"])


@tool(
    "flowmusic_download_stems",
    "Baja los stems de un tema a disco, el de bass incluido. Escribe archivos: "
    "confirmá el destino con el usuario si no es el default. Los stems vienen en "
    "m4a (AAC) — es lo único que entrega el servicio para stems, no hay WAV.",
    {
        "properties": {
            "song": {"type": "string", "description": "source_clip_id o parte del título."},
            "outdir": {"type": "string", "description": "Carpeta destino. Default: ~/Downloads."},
            "cookies_path": {"type": "string"},
        },
        "required": ["song"],
    },
    title="Descargar stems",
    readOnlyHint=False,
    destructiveHint=False,
    openWorldHint=True,
)
def _download_stems(args: dict) -> dict:
    fm = _client(args)
    outdir = args.get("outdir") or _default_outdir()
    return fm.download_stems(args["song"], outdir)


@tool(
    "flowmusic_download_song",
    "Baja la mezcla completa de una canción. Intenta WAV (sin pérdida) y cae a "
    "m4a si no hay. Escribe un archivo en disco.",
    {
        "properties": {
            "clip_id": {"type": "string"},
            "outdir": {"type": "string", "description": "Default: ~/Downloads."},
            "wav": {"type": "boolean", "description": "Preferir WAV. Default true."},
            "cookies_path": {"type": "string"},
        },
        "required": ["clip_id"],
    },
    title="Descargar canción",
    readOnlyHint=False,
    destructiveHint=False,
    openWorldHint=True,
)
def _download_song(args: dict) -> dict:
    fm = _client(args)
    outdir = args.get("outdir") or _default_outdir()
    return fm.download_song(args["clip_id"], outdir, wav=args.get("wav", True))


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
            payload = fn(params.get("arguments") or {})
            return _text(rid, json.dumps(payload, indent=2, ensure_ascii=False))
        except FlowMusicAuthError as e:
            return _text(
                rid,
                f"AUTENTICACIÓN: {e}\n\n"
                "No reintentes ni pruebes otras tools: pedile al usuario que "
                "reexporte las cookies de www.flowmusic.app con la sesión "
                "iniciada y las deje en la raíz del repo como "
                "www.flowmusic.app.cookies.json.",
                is_error=True,
            )
        except FlowMusicError as e:
            return _text(rid, f"Error de Flow Music: {e}", is_error=True)
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
