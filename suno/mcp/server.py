#!/usr/bin/env python3
"""MCP server for Suno.

JSON-RPC 2.0 over stdio with just the stdlib (PEP 668: we don't want to force
`--break-system-packages` on the system Python).

**No tool in this server touches Suno's network, and it's deliberate.** Suno
sits behind Cloudflare, its ToS forbid automated access, and the browser's
cookie export doesn't include `__client`, so the token couldn't even be
renewed. Whatever Suno needs happens through the browser with the user's
session; this is where local diagnostics and download verification live.
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
    "Status of the Suno session: handle, plan, and how much time the token "
    "has left. It's purely local — reads the cookies JSON and decodes the "
    "JWT, without touching the network. Use it before sending the user to "
    "operate in the browser, to know whether they'll find the session "
    "expired. It also reports whether the session would be programmatically "
    "renewable (almost always not).",
    {"properties": {"cookies_path": {"type": "string", "description": "Path to the cookies JSON. Optional."}}},
    title="Session status",
    readOnlyHint=True,
    openWorldHint=False,
)
def _auth_status(args: dict) -> dict:
    st = suno.auth_status(args.get("cookies_path"))
    if not st["valid"]:
        st["action"] = (
            "The session expired. Ask the user to re-export cookies from "
            "suno.com, or simply open suno.com in Chrome (navigating renews "
            "it on the browser side, which is where we're going to operate)."
        )
    return st


@tool(
    "suno_inspect_multitrack",
    "Analyzes a Suno Studio 'Export → Multitrack' zip WITHOUT extracting it: "
    "what tracks it has, how big each one is, whether they're aligned, and "
    "which stems are missing. Local and cheap. Use it right after a download "
    "finishes, before telling the user it went well.",
    {
        "properties": {
            "zip_path": {"type": "string", "description": "Path to the exported .zip."}
        },
        "required": ["zip_path"],
    },
    title="Inspect multitrack",
    readOnlyHint=True,
    openWorldHint=False,
)
def _inspect(args: dict) -> dict:
    return suno.inspect_multitrack(args["zip_path"])


@tool(
    "suno_verify_stem",
    "Measures RMS energy below and above a cutoff (250 Hz by default) of an "
    "audio file, to verify that a stem contains what its name promises: the "
    "bass should dominate at low end, vocals at high end. Local, via ffmpeg. "
    "Never plays audio.",
    {
        "properties": {
            "path": {"type": "string", "description": "Path to the audio file."},
            "split_hz": {"type": "integer", "description": "Cutoff frequency. Default 250."},
        },
        "required": ["path"],
    },
    title="Verify stem",
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
                f"Tool {name!r} doesn't exist. Available: {', '.join(sorted(HANDLERS))}",
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
                f"AUTHENTICATION: {e}\n\n"
                "Suno has no programmatic renewal. Ask the user to "
                "re-export cookies from suno.com, or to open suno.com in "
                "Chrome if we're going to operate via browser.",
                is_error=True,
            )
        except SunoError as e:
            return _text(rid, f"Suno error: {e}", is_error=True)
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
