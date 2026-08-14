#!/usr/bin/env python3
"""Servidor MCP para Google Labs Flow.

Habla JSON-RPC 2.0 sobre stdio sin dependencias externas: el Python de Homebrew
está bajo PEP 668, así que instalar el SDK oficial obligaría a
`--break-system-packages` sobre el intérprete del sistema. El transporte stdio
de MCP es JSON delimitado por saltos de línea, y eso se implementa acá directo.

Las bibliotecas de Flow (flow_client, flow_driver, flow_upscale, flow_api) se
resuelven desde el repo; ver `_resolve_lib`.
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


# --------------------------------------------------------------- resolución lib


def _resolve_lib() -> Path:
    """Ubica las bibliotecas de Flow.

    El plugin es autocontenido: `lib/` vive al lado de `mcp/`. Las otras dos
    opciones existen para desarrollo — apuntar a un checkout distinto sin
    reinstalar, o correr el server desde un repo que tenga las libs en
    `tools/flow`.
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
        "No encuentro las bibliotecas de Flow (flow_client.py). Probé: "
        + ", ".join(str(c) for c in candidates)
        + ". Definí FLOW_LIB con la ruta correcta."
    )


LIB = _resolve_lib()
sys.path.insert(0, str(LIB))

import flow_client  # noqa: E402
import flow_driver  # noqa: E402
import flow_packs  # noqa: E402
import flow_upscale  # noqa: E402


# ------------------------------------------------------------------- registro

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
    """Acepta la receta inline o el nombre de una del pack activo."""
    if args.get("recipe"):
        return args["recipe"]
    if args.get("recipe_name"):
        return flow_packs.load_recipe(args["recipe_name"])
    raise ValueError(
        "hace falta 'recipe' (objeto) o 'recipe_name' (del pack). "
        "Las recetas del pack se listan con flow_pack_info."
    )


# --------------------------------------------------------------------- tools


@tool(
    "flow_session_status",
    "Estado de la sesión de Google Labs Flow: usuario, vencimiento y créditos "
    "disponibles. Úsese primero cuando cualquier otra tool falle con error de "
    "autenticación, para distinguir una cookie vencida de otro problema. No "
    "genera nada ni gasta créditos.",
    {"properties": {}},
    title="Estado de sesión Flow",
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
    "Lista las herramientas ('applets') disponibles en Google Labs Flow, con su "
    "appletId, versión y descripción. Incluye las propias, las de la comunidad y "
    "las oficiales. Devuelve el appletId que necesitan las demás tools. Para ver "
    "el código de una en particular, usar flow_get_applet_code.",
    {
        "properties": {
            "filter": {
                "type": "string",
                "description": "Subcadena para filtrar por nombre o descripción, "
                "sin distinguir mayúsculas. Ej: 'sprite'.",
            },
            "mine_only": {
                "type": "boolean",
                "description": "Sólo applets propios, excluyendo los de la "
                "comunidad (cuyo id empieza con 'community-'). Default false.",
            },
        }
    },
    title="Listar applets de Flow",
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
    "Descarga el código fuente de un applet de Flow y lo guarda en "
    "flow-applets/<appletId>/ (o FLOW_APPLETS). Devuelve los archivos y, si existe, el "
    "contenido de constants.ts, que es donde viven los valores válidos de los "
    "dropdowns necesarios para escribir recetas. Para saber qué controles expone "
    "la UI, usar flow_inspect_controls.",
    {
        "properties": {
            "applet_id": {
                "type": "string",
                "description": "appletId (UUID) obtenido de flow_list_applets.",
            },
            "include_source": {
                "type": "boolean",
                "description": "Incluir el contenido completo de cada archivo en "
                "la respuesta además de escribirlos a disco. Default false, "
                "porque el código suele superar los 20k caracteres.",
            },
        },
        "required": ["applet_id"],
    },
    title="Código fuente de un applet",
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
    "Abre un applet en un browser y devuelve el inventario real de sus controles: "
    "texto de cada botón y placeholder de cada campo. Es la fuente de verdad para "
    "los campos 'label', 'placeholder' y 'generateButton' de una receta. Tarda "
    "cerca de un minuto porque el applet se compila en el browser. No genera nada "
    "ni gasta créditos.",
    {
        "properties": {
            "applet_id": {
                "type": "string",
                "description": "appletId (UUID) obtenido de flow_list_applets.",
            }
        },
        "required": ["applet_id"],
    },
    title="Inspeccionar controles",
    readOnlyHint=True,
    openWorldHint=True,
)
def _inspect_controls(args: dict) -> dict:
    with flow_driver.FlowDriver(headless=True) as drv:
        drv.open(args["applet_id"])
        return drv.describe()


@tool(
    "flow_dryrun_recipe",
    "Aplica todos los controles de una receta en el applet SIN disparar la "
    "generación, y devuelve el estado final de cada control. Verifica que labels "
    "y valores existan y sean seleccionables, con costo cero. Correr esto antes "
    "de flow_batch_generate sobre cualquier receta nueva.",
    {
        "properties": {
            "recipe": {
                "type": "object",
                "description": "Receta completa. Ver la referencia de recetas del "
                "skill flow-assets para el esquema.",
            },
            "recipe_name": {
                "type": "string",
                "description": "Alternativa a 'recipe': nombre de una receta del "
                "pack activo, listadas por flow_pack_info.",
            },
        },
    },
    title="Dryrun de receta (sin costo)",
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
            "note": "No se disparó ninguna generación.",
        }


@tool(
    "flow_generate",
    "Genera UNA imagen ejecutando un applet con los controles de la receta, y la "
    "guarda como PNG. Devuelve la ruta, las dimensiones, el mediaId y el costo en "
    "créditos medido antes/después. Para varias variantes usar "
    "flow_batch_generate, que reutiliza una sola sesión de browser.",
    {
        "properties": {
            "recipe": {
                "type": "object",
                "description": "Receta con appletId, generateButton y controls.",
            },
            "recipe_name": {
                "type": "string",
                "description": "Alternativa a 'recipe': nombre de una receta del "
                "pack activo.",
            },
            "out_dir": {
                "type": "string",
                "description": "Carpeta destino. Default work/flow-mcp/single.",
            },
        },
    },
    title="Generar una imagen",
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
    "Genera todas las combinaciones del producto cartesiano del campo 'matrix' de "
    "una receta, reutilizando una sola sesión de browser y pausando entre ítems. "
    "Saltea las variantes cuyo PNG ya existe, así que una corrida interrumpida se "
    "retoma volviéndola a llamar. Usar 'limit' para tandas cortas.",
    {
        "properties": {
            "recipe": {
                "type": "object",
                "description": "Receta con 'matrix': un objeto que mapea cada "
                "label de dropdown a la lista de valores a recorrer.",
            },
            "recipe_name": {
                "type": "string",
                "description": "Alternativa a 'recipe': nombre de una receta del "
                "pack activo.",
            },
            "out_dir": {
                "type": "string",
                "description": "Carpeta destino. Default work/flow-mcp/batch.",
            },
            "limit": {
                "type": "integer",
                "description": "Cortar en las primeras N variantes. Conviene "
                "empezar con 2 o 3 para validar antes de una tanda larga.",
                "minimum": 1,
            },
        },
    },
    title="Generar en batch",
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
    "Agranda PNGs localmente sin costo ni red. Con filter 'nearest' y factor "
    "entero preserva los bordes duros del pixel art; 'lanczos' es para arte "
    "pintado. Es la opción correcta para sprites: el upscaler generativo de Flow "
    "los suavizaría. Acepta un archivo o una carpeta.",
    {
        "properties": {
            "src": {
                "type": "string",
                "description": "Ruta a un PNG o a una carpeta con PNGs.",
            },
            "factor": {
                "type": "integer",
                "description": "Factor entero de escala. Default 2.",
                "minimum": 2,
                "maximum": 8,
            },
            "filter": {
                "type": "string",
                "enum": ["nearest", "lanczos", "bicubic"],
                "description": "nearest para pixel art (default), lanczos para "
                "arte pintado o fotográfico.",
            },
            "suffix": {
                "type": "string",
                "description": "Sufijo del archivo de salida. Default '@2x'.",
            },
        },
        "required": ["src"],
    },
    title="Upscale local (sin costo)",
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
        raise ValueError(f"sin PNGs en {src}")
    done = []
    for f in files:
        if f.stem.endswith(suffix):
            continue  # no re-escalar salidas previas
        dest = f.parent / f"{f.stem}{suffix}.png"
        w, h, nw, nh = flow_upscale.upscale(f, dest, factor=factor, filt=filt)
        done.append({"src": str(f), "out": str(dest), "from": f"{w}x{h}", "to": f"{nw}x{nh}"})
    return {"filter": filt, "factor": factor, "count": len(done), "files": done}


@tool(
    "flow_upscale_native",
    "Manda una imagen ya generada al upscaler 2K/4K de Flow, identificada por su "
    "mediaId. CONSUME CRÉDITOS y exige un Chrome real vía cdp_url: los tokens de "
    "reCAPTCHA de un browser automatizado son rechazados con 403. Para pixel art "
    "usar flow_upscale_local, que da mejor resultado y no cuesta.",
    {
        "properties": {
            "media_id": {
                "type": "string",
                "description": "UUID devuelto como mediaId por flow_generate.",
            },
            "resolution": {
                "type": "string",
                "enum": ["2K", "4K"],
                "description": "Resolución destino. Default 2K.",
            },
            "cdp_url": {
                "type": "string",
                "description": "Endpoint de un Chrome real, ej. "
                "http://localhost:9222. Sin esto la llamada da 403.",
            },
        },
        "required": ["media_id", "cdp_url"],
    },
    title="Upscale 2K/4K nativo (con costo)",
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
    "Describe el pack activo: proyecto de Flow, herramientas registradas con sus "
    "controles y vocabularios, y recetas disponibles. Un pack es la parte propia "
    "de cada cuenta (projectId, appletIds, valores de dropdown); el resto del "
    "plugin es genérico. Si no hay pack, explica cómo generar uno.",
    {"properties": {}},
    title="Pack activo",
    readOnlyHint=True,
    openWorldHint=False,
)
def _pack_info(args: dict) -> dict:
    pack = flow_packs.load_pack()
    if pack is None:
        return {
            "pack": None,
            "note": "No hay pack activo. Generá uno con flow_scaffold_pack, o "
            "apuntá FLOW_PACK a un directorio que tenga pack.json. Sin pack, "
            "las tools que abren un applet necesitan project_id explícito.",
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
    "Genera un pack para la cuenta actual: descubre el proyecto de Flow, lista "
    "las herramientas propias, baja su código y extrae de constants.ts los "
    "valores válidos de cada dropdown, dejando pack.json, applets.md y una "
    "receta inicial por herramienta. Es el punto de partida para usar el plugin "
    "con una cuenta nueva. No genera imágenes ni gasta créditos.",
    {
        "properties": {
            "dest": {
                "type": "string",
                "description": "Directorio donde escribir el pack. Se crea si no "
                "existe. Ej: ./mi-pack o ~/.config/google-flow/packs/mio.",
            },
            "name": {
                "type": "string",
                "description": "Nombre del pack, para identificarlo.",
            },
            "project_id": {
                "type": "string",
                "description": "projectId de Flow. Si se omite se descubre "
                "abriendo la app en un browser.",
            },
            "filter": {
                "type": "string",
                "description": "Incluir sólo las herramientas cuyo nombre o "
                "descripción contenga esta subcadena.",
            },
            "include_community": {
                "type": "boolean",
                "description": "Incluir también applets de la comunidad. Default "
                "false: un pack describe las herramientas propias.",
            },
        },
        "required": ["dest", "name"],
    },
    title="Generar un pack para esta cuenta",
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
            return _result(
                rid,
                {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": f"No existe la tool {name!r}. "
                            f"Disponibles: {', '.join(sorted(HANDLERS))}",
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
                            "text": f"Sesión de Flow inválida: {e}\n"
                            "Reexportá las cookies de labs.google a "
                            "labs.google.cookies.json en la raíz del repo.",
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
    return _error(rid, -32601, f"método no soportado: {method}")


def main() -> None:
    # Aislar los descriptores del protocolo antes de que exista un subproceso.
    # Playwright lanza un proceso Node que hereda stdin y stdout: si los
    # comparte, se come las líneas del protocolo (el server deja de responder
    # después de la primera tool que abre browser) y ensucia stdout.
    proto_in_fd = os.dup(0)
    proto_out_fd = os.dup(1)

    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)  # los hijos heredan /dev/null, no el canal del protocolo
    os.close(devnull)
    os.dup2(2, 1)  # lo que un hijo escriba a stdout va a stderr

    stdin = os.fdopen(proto_in_fd, "r", encoding="utf-8")
    protocol_out = os.fdopen(proto_out_fd, "w", encoding="utf-8")
    sys.stdout = sys.stderr  # y lo que imprima este proceso, también

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
        except Exception as e:  # nunca tirar el transporte
            response = _error(msg.get("id"), -32603, f"{type(e).__name__}: {e}")
        if response is not None:
            protocol_out.write(json.dumps(response, ensure_ascii=False) + "\n")
            protocol_out.flush()


if __name__ == "__main__":
    main()
