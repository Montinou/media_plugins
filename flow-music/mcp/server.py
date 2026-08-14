#!/usr/bin/env python3
"""MCP server for Google Flow Music.

JSON-RPC 2.0 over stdio using only the stdlib: Homebrew's Python is under
PEP 668, and installing the official SDK would force `--break-system-packages`.

Convention for this marketplace:
the lib is resolved from the plugin, and authentication errors are
returned as `isError` with instructions for the user — never retried
against the service.
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
    "Flow Music session status: who it belongs to, how much time is left, and "
    "whether it can refresh itself. Purely local — doesn't touch the network "
    "or spend anything. ALWAYS use it before the first operation of a work "
    "session, and every time another tool fails on authentication, to "
    "distinguish an expired cookie from a real problem.",
    {"properties": {"cookies_path": {"type": "string", "description": "Path to the cookies JSON. Optional."}}},
    title="Session status",
    readOnlyHint=True,
    openWorldHint=False,
)
def _auth_status(args: dict) -> dict:
    try:
        st = _client(args).auth_status()
    except FlowMusicAuthError as e:
        return {"valid": False, "problem": str(e), "action": "ask the user to re-export the cookies"}
    if not st["valid"] and st["can_refresh"]:
        st["action"] = "the token expired but there's a refresh_token: it renews itself on the next call"
    elif not st["valid"]:
        st["action"] = "ask the user to re-export the cookies from www.flowmusic.app"
    return st


@tool(
    "flowmusic_account",
    "Account and balance: user and available credits. The counter shown in "
    "the web sidebar is the free daily quota, NOT the balance — the real "
    "balance is `credits_remaining`. Check it before proposing to generate "
    "music, so you don't overestimate or underestimate what's available.",
    {"properties": {"cookies_path": {"type": "string"}}},
    title="Account and credits",
    readOnlyHint=True,
)
def _account(args: dict) -> dict:
    fm = _client(args)
    return {"user": fm.me(), "credits": fm.credits()}


@tool(
    "flowmusic_list_songs",
    "User's songs, most recent first: id, title, operation type, and "
    "duration. Useful for finding a track's clip_id before downloading it or "
    "splitting its stems.",
    {
        "properties": {
            "limit": {"type": "integer", "description": "Maximum to return (default 20)."},
            "cookies_path": {"type": "string"},
        }
    },
    title="List songs",
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
    "Tracks that ALREADY have separated stems, with which stems each one "
    "has. Flow Music doesn't separate on its own: if a track doesn't show up "
    "here, you have to open the web and run 'Split stems' on it first (this "
    "tool can't do that).",
    {"properties": {"cookies_path": {"type": "string"}}},
    title="Tracks with stems",
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
        "note": "If a track is missing, run 'Split stems' on it in the Flow Music UI.",
    }


@tool(
    "flowmusic_stem_urls",
    "Download URLs for a track's stems, WITHOUT downloading anything. Cheap "
    "and with no side effects: use it to show the user what's about to be "
    "downloaded before spending bandwidth, or to verify that the bass is "
    "available.",
    {
        "properties": {
            "song": {"type": "string", "description": "source_clip_id or part of the title."},
            "cookies_path": {"type": "string"},
        },
        "required": ["song"],
    },
    title="Stem URLs",
    readOnlyHint=True,
)
def _stem_urls(args: dict) -> dict:
    return _client(args).stem_urls(args["song"])


@tool(
    "flowmusic_download_stems",
    "Downloads a track's stems to disk, bass included. Writes files: confirm "
    "the destination with the user if it isn't the default. Stems come in "
    "m4a (AAC) — that's the only format the service delivers for stems, "
    "there's no WAV.",
    {
        "properties": {
            "song": {"type": "string", "description": "source_clip_id or part of the title."},
            "outdir": {"type": "string", "description": "Destination folder. Default: ~/Downloads."},
            "cookies_path": {"type": "string"},
        },
        "required": ["song"],
    },
    title="Download stems",
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
    "Downloads a song's complete mix. Tries WAV (lossless) and falls back to "
    "m4a if unavailable. Writes a file to disk.",
    {
        "properties": {
            "clip_id": {"type": "string"},
            "outdir": {"type": "string", "description": "Default: ~/Downloads."},
            "wav": {"type": "boolean", "description": "Prefer WAV. Default true."},
            "cookies_path": {"type": "string"},
        },
        "required": ["clip_id"],
    },
    title="Download song",
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
                f"Tool {name!r} doesn't exist. Available: {', '.join(sorted(HANDLERS))}",
                is_error=True,
            )
        try:
            payload = fn(params.get("arguments") or {})
            return _text(rid, json.dumps(payload, indent=2, ensure_ascii=False))
        except FlowMusicAuthError as e:
            return _text(
                rid,
                f"AUTHENTICATION: {e}\n\n"
                "Don't retry or try other tools: ask the user to re-export the "
                "cookies from www.flowmusic.app while logged in and leave them "
                "at the repo root as www.flowmusic.app.cookies.json.",
                is_error=True,
            )
        except FlowMusicError as e:
            return _text(rid, f"Flow Music error: {e}", is_error=True)
        except Exception as e:  # noqa: BLE001
            return _text(rid, f"{type(e).__name__}: {e}", is_error=True)

    return {
        "jsonrpc": "2.0",
        "id": rid,
        "error": {"code": -32601, "message": f"Unsupported method: {method}"},
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
