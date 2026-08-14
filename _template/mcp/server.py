#!/usr/bin/env python3
"""Example MCP server — reusable core.

JSON-RPC 2.0 over stdio using only the stdlib. Runs as-is:

    printf '%s\\n' \\
      '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{}}}' \\
      '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \\
      | python3 _template/mcp/server.py

To make it yours: change SERVER_NAME, import your lib, and replace the
example tools. You don't need to touch the JSON-RPC layer below.

Anything project-specific (ids, presets, prompts) does NOT go here: it
goes in `packs/<project>/` and gets loaded by name. See `packs/README.md`.
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
    """Registers a tool.

    The `description` is read by a model to decide when to use it: write
    what it's for and WHEN it's appropriate, not just what it does. Mark
    `readOnlyHint=True` on anything that doesn't write or spend.
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
    "Session status: purely local, doesn't touch the network or spend "
    "anything. Use it ALWAYS before the first operation of a work session, "
    "and every time another tool fails on authentication, to tell an "
    "expired cookie apart from a real problem.",
    {"properties": {"cookies_path": {"type": "string", "description": "Path to the cookies JSON. Optional."}}},
    title="Session status",
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
            "action": "ask the user to re-export the cookies",
        }


@tool(
    "example_ping",
    "Example tool that does hit the network. Replace it with your "
    "service's first real operation.",
    {"properties": {"cookies_path": {"type": "string"}}},
    title="Ping",
    readOnlyHint=True,
)
def _ping(args: dict) -> dict:
    return Service(args.get("cookies_path")).call("get", "/health")


# -------------------------------------------------------------------- JSON-RPC
# Everything below this point is infrastructure: works the same for any plugin.


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
        # We return whatever version the client asks for: hosts range from
        # 2024-11-05 to 2025-11-25, and hardcoding one breaks with the rest.
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
        return None  # notifications don't get a response

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
        except ServiceAuthError as e:
            # An auth error belongs to the user, not the model: state the
            # concrete action and forbid retrying.
            return _text(
                rid,
                f"AUTHENTICATION: {e}\n\n"
                "Do not retry or try other tools: ask the user to "
                "re-export the cookies.",
                is_error=True,
            )
        except ServiceError as e:
            return _text(rid, f"Service error: {e}", is_error=True)
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
