#!/usr/bin/env python3
"""MCP server for Google Labs Flow.

Speaks JSON-RPC 2.0 over stdio with no external dependencies: Homebrew's
Python is under PEP 668, so installing the official SDK would force
`--break-system-packages` on the system interpreter. MCP's stdio transport is
newline-delimited JSON, and that's implemented directly here.

The Flow libraries (flow_client, flow_driver, flow_upscale, flow_api) are
resolved from the repo; see `_resolve_lib`.
"""
from __future__ import annotations


import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "google-flow"
SERVER_VERSION = "0.1.0"


# --------------------------------------------------------------- lib resolution


def _resolve_lib() -> Path:
    """Locates the Flow libraries.

    The plugin is self-contained: `lib/` lives next to `mcp/`. The other two
    options exist for development — pointing to a different checkout without
    reinstalling, or running the server from a repo that has the libs under
    `lib/`.
    """
    candidates = []
    if os.environ.get("FLOW_LIB"):
        candidates.append(Path(os.environ["FLOW_LIB"]))
    candidates.append(Path(__file__).resolve().parent.parent / "lib")
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root:
        candidates.append(Path(root).resolve() / "lib")
        candidates.append(Path(root).resolve().parents[1] / "tools" / "flow")
    candidates.append(Path.cwd() / "tools" / "flow")

    for c in candidates:
        if (c / "flow_client.py").exists():
            return c
    raise RuntimeError(
        "Can't find the Flow libraries (flow_client.py). Tried: "
        + ", ".join(str(c) for c in candidates)
        + ". Set FLOW_LIB to the right path."
    )


LIB = _resolve_lib()
sys.path.insert(0, str(LIB))

import flow_client  # noqa: E402
import flow_driver  # noqa: E402
import flow_packs  # noqa: E402
import flow_upscale  # noqa: E402


# ------------------------------------------------------------------- registry

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


def _out_dir(sub: str) -> Path:
    base = Path(os.environ.get("FLOW_OUT", Path.cwd() / "flow-out"))
    d = base / sub
    d.mkdir(parents=True, exist_ok=True)
    return d



def _resolve_recipe(args: dict) -> dict:
    """Accepts the recipe inline or the name of one from the active pack."""
    if args.get("recipe"):
        return args["recipe"]
    if args.get("recipe_name"):
        return flow_packs.load_recipe(args["recipe_name"])
    raise ValueError(
        "need either 'recipe' (object) or 'recipe_name' (from the pack). "
        "Pack recipes are listed by flow_pack_info."
    )


# --------------------------------------------------------------------- tools


@tool(
    "flow_session_status",
    "Google Labs Flow session status: user, expiration, and available credits. "
    "Use this first when any other tool fails with an auth error, to tell an "
    "expired cookie apart from another problem. Generates nothing and spends "
    "no credits.",
    {"properties": {}},
    title="Flow session status",
    readOnlyHint=True,
    openWorldHint=True,
)
def _session_status(args: dict) -> dict:
    info = flow_client.session_info()
    out = {
        "user": info.get("user", {}).get("email"),
        "name": info.get("user", {}).get("name"),
        "sessionExpires": info.get("expires"),
        "hasBearer": bool(info.get("access_token")),
    }
    try:
        c = flow_client.sandbox("GET", "credits")
        out["credits"] = c.get("credits")
        out["tier"] = c.get("userPaygateTier")
    except Exception as e:
        out["creditsError"] = str(e)[:200]
    return out


@tool(
    "flow_list_applets",
    "Lists the tools ('applets') available in Google Labs Flow, with their "
    "appletId, version, and description. Includes your own, community ones, "
    "and official ones. Returns the appletId the other tools need. To see a "
    "specific one's code, use flow_get_applet_code.",
    {
        "properties": {
            "filter": {
                "type": "string",
                "description": "Substring to filter by name or description, "
                "case-insensitive. E.g.: 'sprite'.",
            },
            "mine_only": {
                "type": "boolean",
                "description": "Only your own applets, excluding community "
                "ones (whose id starts with 'community-'). Default false.",
            },
        }
    },
    title="List Flow applets",
    readOnlyHint=True,
    openWorldHint=True,
)
def _list_applets(args: dict) -> dict:
    applets = flow_client.list_applets()
    if args.get("mine_only"):
        applets = [a for a in applets if not a["appletId"].startswith("community-")]
    f = (args.get("filter") or "").lower()
    if f:
        applets = [
            a
            for a in applets
            if f in a.get("displayName", "").lower()
            or f in a.get("description", "").lower()
        ]
    return {
        "count": len(applets),
        "applets": [
            {
                "appletId": a["appletId"],
                "displayName": a.get("displayName"),
                "description": a.get("description"),
                "currentVersionId": a.get("currentVersionId"),
                "updateTime": a.get("updateTime"),
                "favorited": a.get("isFavorited", False),
            }
            for a in applets
        ],
    }


@tool(
    "flow_get_applet_code",
    "Downloads a Flow applet's source code and saves it to "
    "flow-applets/<appletId>/ (or FLOW_APPLETS). Returns the files and, if it "
    "exists, the content of constants.ts, which is where the valid dropdown "
    "values needed for writing recipes live. To find out what controls the UI "
    "exposes, use flow_inspect_controls.",
    {
        "properties": {
            "applet_id": {
                "type": "string",
                "description": "appletId (UUID) obtained from flow_list_applets.",
            },
            "include_source": {
                "type": "boolean",
                "description": "Include each file's full content in the "
                "response in addition to writing them to disk. Default "
                "false, because the code often exceeds 20k characters.",
            },
        },
        "required": ["applet_id"],
    },
    title="Applet source code",
    readOnlyHint=False,
    openWorldHint=True,
)
def _get_applet_code(args: dict) -> dict:
    applet_id = args["applet_id"]
    data = flow_client.get_applet(applet_id)
    dest = Path(
        os.environ.get("FLOW_APPLETS", Path.cwd() / "flow-applets")
    ) / applet_id
    dest.mkdir(parents=True, exist_ok=True)

    files = data.get("codeFiles") or []
    written = []
    constants = None
    for f in files:
        p = dest / f["name"]
        p.parent.mkdir(parents=True, exist_ok=True)
        content = f.get("content", "")
        p.write_text(content)
        written.append({"name": f["name"], "bytes": len(content)})
        if f["name"].endswith("constants.ts"):
            constants = content

    out: dict[str, Any] = {
        "appletId": applet_id,
        "savedTo": str(dest),
        "files": written,
    }
    if constants:
        out["constants"] = constants[:20000]
    if args.get("include_source"):
        out["source"] = {f["name"]: f.get("content", "") for f in files}
    return out


@tool(
    "flow_inspect_controls",
    "Opens an applet in a browser and returns the real inventory of its "
    "controls: each button's text and each field's placeholder. It's the "
    "source of truth for a recipe's 'label', 'placeholder', and "
    "'generateButton' fields. Takes about a minute because the applet "
    "compiles in the browser. Generates nothing and spends no credits.",
    {
        "properties": {
            "applet_id": {
                "type": "string",
                "description": "appletId (UUID) obtained from flow_list_applets.",
            }
        },
        "required": ["applet_id"],
    },
    title="Inspect controls",
    readOnlyHint=True,
    openWorldHint=True,
)
def _inspect_controls(args: dict) -> dict:
    with flow_driver.FlowDriver(headless=True) as drv:
        drv.open(args["applet_id"])
        return drv.describe()


@tool(
    "flow_dryrun_recipe",
    "Applies all of a recipe's controls on the applet WITHOUT firing the "
    "generation, and returns each control's final state. Verifies that "
    "labels and values exist and are selectable, at zero cost. Run this "
    "before flow_batch_generate on any new recipe.",
    {
        "properties": {
            "recipe": {
                "type": "object",
                "description": "Full recipe. See the flow-assets skill's "
                "recipe reference for the schema.",
            },
            "recipe_name": {
                "type": "string",
                "description": "Alternative to 'recipe': name of a recipe "
                "from the active pack, listed by flow_pack_info.",
            },
        },
    },
    title="Dry-run a recipe (no cost)",
    readOnlyHint=True,
    openWorldHint=True,
)
def _dryrun(args: dict) -> dict:
    recipe = _resolve_recipe(args)
    with flow_driver.FlowDriver(headless=True) as drv:
        drv.open(
            recipe["appletId"],
            timeout=recipe.get("loadTimeoutMs", 90000),
            project_id=recipe.get("projectId"),
        )
        flow_driver.apply_controls(drv, recipe)
        return {
            "ok": True,
            "controls": [t for t in drv._button_texts() if t],
            "note": "No generation was fired.",
        }


@tool(
    "flow_generate",
    "Generates ONE image by running an applet with the recipe's controls, "
    "and saves it as a PNG. Returns the path, the dimensions, the mediaId, "
    "and the credit cost measured before/after. For several variants use "
    "flow_batch_generate, which reuses a single browser session.",
    {
        "properties": {
            "recipe": {
                "type": "object",
                "description": "Recipe with appletId, generateButton, and controls.",
            },
            "recipe_name": {
                "type": "string",
                "description": "Alternative to 'recipe': name of a recipe "
                "from the active pack.",
            },
            "out_dir": {
                "type": "string",
                "description": "Destination folder. Default work/flow-mcp/single.",
            },
        },
    },
    title="Generate one image",
    readOnlyHint=False,
    openWorldHint=True,
)
def _generate(args: dict) -> dict:
    recipe = _resolve_recipe(args)
    out = Path(args["out_dir"]) if args.get("out_dir") else _out_dir("single")
    meta = flow_driver.run_recipe(recipe, out, headless=True)
    return {
        "file": str(out / meta["file"]),
        "width": meta["width"],
        "height": meta["height"],
        "mediaId": meta["mediaId"],
        "credits": meta["credits"],
    }


@tool(
    "flow_batch_generate",
    "Generates every combination of the cartesian product of a recipe's "
    "'matrix' field, reusing a single browser session and pausing between "
    "items. Skips variants whose PNG already exists, so an interrupted run "
    "resumes by calling it again. Use 'limit' for short batches.",
    {
        "properties": {
            "recipe": {
                "type": "object",
                "description": "Recipe with 'matrix': an object mapping "
                "each dropdown label to the list of values to sweep.",
            },
            "recipe_name": {
                "type": "string",
                "description": "Alternative to 'recipe': name of a recipe "
                "from the active pack.",
            },
            "out_dir": {
                "type": "string",
                "description": "Destination folder. Default work/flow-mcp/batch.",
            },
            "limit": {
                "type": "integer",
                "description": "Stop after the first N variants. Worth "
                "starting with 2 or 3 to validate before a long batch.",
                "minimum": 1,
            },
        },
    },
    title="Generate in batch",
    readOnlyHint=False,
    openWorldHint=True,
)
def _batch(args: dict) -> dict:
    recipe = _resolve_recipe(args)
    out = Path(args["out_dir"]) if args.get("out_dir") else _out_dir("batch")
    results = flow_driver.run_batch(
        recipe, out, headless=True, limit=args.get("limit")
    )
    ok = [r for r in results if "error" not in r]
    return {
        "outDir": str(out),
        "generated": len(ok),
        "failed": len(results) - len(ok),
        "results": results,
        "manifest": str(out / "batch-manifest.json"),
    }


@tool(
    "flow_upscale_local",
    "Enlarges PNGs locally with no cost and no network. With filter "
    "'nearest' and an integer factor it preserves pixel art's sharp edges; "
    "'lanczos' is for painted art. It's the right choice for sprites: "
    "Flow's generative upscaler would soften them. Accepts a file or a folder.",
    {
        "properties": {
            "src": {
                "type": "string",
                "description": "Path to a PNG or to a folder with PNGs.",
            },
            "factor": {
                "type": "integer",
                "description": "Integer scale factor. Default 2.",
                "minimum": 2,
                "maximum": 8,
            },
            "filter": {
                "type": "string",
                "enum": ["nearest", "lanczos", "bicubic"],
                "description": "nearest for pixel art (default), lanczos "
                "for painted or photographic art.",
            },
            "suffix": {
                "type": "string",
                "description": "Output file suffix. Default '@2x'.",
            },
        },
        "required": ["src"],
    },
    title="Local upscale (no cost)",
    readOnlyHint=False,
    openWorldHint=False,
)
def _upscale_local(args: dict) -> dict:
    src = Path(args["src"])
    factor = args.get("factor", 2)
    filt = args.get("filter", "nearest")
    suffix = args.get("suffix", f"@{factor}x")
    files = sorted(src.glob("*.png")) if src.is_dir() else [src]
    if not files:
        raise ValueError(f"no PNGs in {src}")
    done = []
    for f in files:
        if f.stem.endswith(suffix):
            continue  # don't re-scale previous outputs
        dest = f.parent / f"{f.stem}{suffix}.png"
        w, h, nw, nh = flow_upscale.upscale(f, dest, factor=factor, filt=filt)
        done.append({"src": str(f), "out": str(dest), "from": f"{w}x{h}", "to": f"{nw}x{nh}"})
    return {"filter": filt, "factor": factor, "count": len(done), "files": done}


@tool(
    "flow_upscale_native",
    "Sends an already-generated image to Flow's 2K/4K upscaler, identified "
    "by its mediaId. SPENDS CREDITS and requires a real Chrome via cdp_url: "
    "reCAPTCHA tokens from an automated browser get rejected with 403. For "
    "pixel art use flow_upscale_local, which gives a better result and "
    "costs nothing.",
    {
        "properties": {
            "media_id": {
                "type": "string",
                "description": "UUID returned as mediaId by flow_generate.",
            },
            "resolution": {
                "type": "string",
                "enum": ["2K", "4K"],
                "description": "Target resolution. Default 2K.",
            },
            "cdp_url": {
                "type": "string",
                "description": "Endpoint of a real Chrome, e.g. "
                "http://localhost:9222. Without this the call gets a 403.",
            },
        },
        "required": ["media_id", "cdp_url"],
    },
    title="Native 2K/4K upscale (costs credits)",
    readOnlyHint=False,
    openWorldHint=True,
)
def _upscale_native(args: dict) -> dict:
    import flow_api

    before = flow_api.credits_now()
    with flow_api.FlowPageAPI(cdp=args["cdp_url"]) as api:
        res = api.upsample(args["media_id"], args.get("resolution", "2K"))
    after = flow_api.credits_now()
    return {
        "response": res,
        "credits": {
            "before": before,
            "after": after,
            "cost": (before - after) if None not in (before, after) else None,
        },
    }



@tool(
    "flow_pack_info",
    "Describes the active pack: Flow project, registered tools with their "
    "controls and vocabularies, and available recipes. A pack is the part "
    "specific to each account (projectId, appletIds, dropdown values); the "
    "rest of the plugin is generic. If there's no pack, explains how to "
    "generate one.",
    {"properties": {}},
    title="Active pack",
    readOnlyHint=True,
    openWorldHint=False,
)
def _pack_info(args: dict) -> dict:
    pack = flow_packs.load_pack()
    if pack is None:
        return {
            "pack": None,
            "note": "No active pack. Generate one with flow_scaffold_pack, "
            "or point FLOW_PACK at a directory that has pack.json. Without "
            "a pack, tools that open an applet need an explicit project_id.",
        }
    applets = {
        slug: {
            "appletId": a["appletId"],
            "displayName": a.get("displayName"),
            "generateButton": a.get("generateButton"),
            "controls": a.get("controls"),
            "vocabulary": a.get("vocabulary"),
        }
        for slug, a in (pack.get("applets") or {}).items()
    }
    return {
        "name": pack.get("name"),
        "projectId": pack.get("projectId"),
        "dir": pack.get("_dir"),
        "applets": applets,
        "recipes": flow_packs.list_recipes(),
    }


@tool(
    "flow_scaffold_pack",
    "Generates a pack for the current account: discovers the Flow project, "
    "lists your own tools, downloads their code, and extracts each "
    "dropdown's valid values from constants.ts, leaving pack.json, "
    "applets.md, and one starter recipe per tool. It's the starting point "
    "for using the plugin with a new account. Generates no images and "
    "spends no credits.",
    {
        "properties": {
            "dest": {
                "type": "string",
                "description": "Directory to write the pack to. Created if "
                "it doesn't exist. E.g.: ./my-pack or "
                "~/.config/google-flow/packs/mine.",
            },
            "name": {
                "type": "string",
                "description": "Pack name, to identify it.",
            },
            "project_id": {
                "type": "string",
                "description": "Flow projectId. If omitted it's discovered "
                "by opening the app in a browser.",
            },
            "filter": {
                "type": "string",
                "description": "Include only tools whose name or "
                "description contains this substring.",
            },
            "include_community": {
                "type": "boolean",
                "description": "Also include community applets. Default "
                "false: a pack describes your own tools.",
            },
        },
        "required": ["dest", "name"],
    },
    title="Generate a pack for this account",
    readOnlyHint=False,
    openWorldHint=True,
)
def _scaffold_pack(args: dict) -> dict:
    return flow_packs.scaffold(
        dest=Path(args["dest"]).expanduser(),
        name=args["name"],
        project_id_value=args.get("project_id"),
        applet_filter=args.get("filter"),
        mine_only=not args.get("include_community", False),
        headless=True,
    )


# ---------------------------------------------------------------- JSON-RPC


def _result(rid, payload):
    return {"jsonrpc": "2.0", "id": rid, "result": payload}


def _error(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


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

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None  # notifications carry no response

    if method == "ping":
        return _result(rid, {})

    if method == "tools/list":
        return _result(rid, {"tools": TOOLS})

    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        fn = HANDLERS.get(name)
        if fn is None:
            return _result(
                rid,
                {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": f"No such tool {name!r}. "
                            f"Available: {', '.join(sorted(HANDLERS))}",
                        }
                    ],
                },
            )
        try:
            payload = fn(params.get("arguments") or {})
            return _result(
                rid,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(payload, indent=2, ensure_ascii=False),
                        }
                    ]
                },
            )
        except flow_client.FlowAuthError as e:
            return _result(
                rid,
                {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": f"Invalid Flow session: {e}\n"
                            "Re-export the labs.google cookies to "
                            "labs.google.cookies.json at the repo root.",
                        }
                    ],
                },
            )
        except Exception as e:
            return _result(
                rid,
                {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": f"{type(e).__name__}: {e}\n\n"
                            + traceback.format_exc()[-1500:],
                        }
                    ],
                },
            )

    if rid is None:
        return None
    return _error(rid, -32601, f"unsupported method: {method}")


def main() -> None:
    # Isolate the protocol descriptors before a subprocess exists. Playwright
    # launches a Node process that inherits stdin and stdout: if it shares
    # them, it eats the protocol's lines (the server stops responding after
    # the first tool that opens a browser) and pollutes stdout.
    proto_in_fd = os.dup(0)
    proto_out_fd = os.dup(1)

    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)  # children inherit /dev/null, not the protocol channel
    os.close(devnull)
    os.dup2(2, 1)  # whatever a child writes to stdout goes to stderr

    stdin = os.fdopen(proto_in_fd, "r", encoding="utf-8")
    protocol_out = os.fdopen(proto_out_fd, "w", encoding="utf-8")
    sys.stdout = sys.stderr  # and whatever this process prints, too

    for line in iter(stdin.readline, ""):
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        try:
            response = handle(msg)
        except Exception as e:  # never bring down the transport
            response = _error(msg.get("id"), -32603, f"{type(e).__name__}: {e}")
        if response is not None:
            protocol_out.write(json.dumps(response, ensure_ascii=False) + "\n")
            protocol_out.flush()


if __name__ == "__main__":
    main()
