#!/usr/bin/env python3
"""Packs: la parte de google-flow que es de cada cuenta.

El plugin es genérico —las tools funcionan con cualquier cuenta y cualquier
applet— pero tres cosas son irreductiblemente propias de quien lo usa:

    projectId    el proyecto de Flow, que va en la URL de cada applet
    appletIds    los identificadores de sus herramientas
    vocabularios los valores válidos de los dropdowns de esas herramientas

Un pack agrupa eso en un directorio, para que el plugin no traiga hardcodeado
el proyecto de nadie:

    <pack>/
    ├── pack.json          projectId, applets y sus controles
    ├── applets.md         notas sobre qué hace cada herramienta
    └── recipes/*.json     recetas listas para usar

`flow_scaffold_pack` genera uno leyendo la cuenta: descubre el proyecto, lista
los applets, baja su código y extrae los vocabularios de `constants.ts`.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import flow_client

PACK_FILE = "pack.json"


# ------------------------------------------------------------------ ubicación


def pack_dir() -> Path | None:
    """Directorio del pack activo, o None si no hay ninguno configurado."""
    env = os.environ.get("FLOW_PACK")
    if env:
        p = Path(env).expanduser()
        return p if (p / PACK_FILE).exists() else None
    # packs/<nombre> junto a la lib, elegido por FLOW_PACK_NAME
    name = os.environ.get("FLOW_PACK_NAME")
    if name:
        p = Path(__file__).resolve().parent.parent / "packs" / name
        return p if (p / PACK_FILE).exists() else None
    return None


def load_pack() -> dict | None:
    d = pack_dir()
    if d is None:
        return None
    data = json.loads((d / PACK_FILE).read_text())
    data["_dir"] = str(d)
    return data


def project_id(explicit: str | None = None) -> str:
    """Resuelve el projectId: parámetro, entorno, pack. Sin default inventado."""
    if explicit:
        return explicit
    if os.environ.get("FLOW_PROJECT_ID"):
        return os.environ["FLOW_PROJECT_ID"]
    pack = load_pack()
    if pack and pack.get("projectId"):
        return pack["projectId"]
    raise RuntimeError(
        "no sé con qué proyecto de Flow trabajar. Definí FLOW_PROJECT_ID, o "
        "generá un pack con flow_scaffold_pack, o pasá project_id explícito. "
        "El id está en la URL: labs.google/fx/tools/flow/project/<projectId>/…"
    )


def list_recipes() -> list[dict]:
    d = pack_dir()
    if d is None:
        return []
    out = []
    for f in sorted((d / "recipes").glob("*.json")):
        try:
            r = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        out.append(
            {
                "name": f.stem,
                "path": str(f),
                "appletId": r.get("appletId"),
                "hasMatrix": bool(r.get("matrix")),
                "variants": _matrix_size(r),
            }
        )
    return out


def load_recipe(name: str) -> dict:
    d = pack_dir()
    if d is None:
        raise RuntimeError(
            "no hay pack activo: definí FLOW_PACK o pasá la receta completa."
        )
    f = (d / "recipes" / f"{name}.json") if not name.endswith(".json") else Path(name)
    if not f.exists():
        available = [r["name"] for r in list_recipes()]
        raise RuntimeError(
            f"no existe la receta {name!r} en el pack. Disponibles: {available}"
        )
    return json.loads(f.read_text())


def _matrix_size(recipe: dict) -> int:
    m = recipe.get("matrix") or {}
    n = 1
    for values in m.values():
        n *= max(1, len(values))
    return n if m else 1


# ----------------------------------------------------------------- descubrir


def discover_project_id(headless: bool = True) -> str:
    """Descubre el projectId abriendo Flow y viendo a qué proyecto entra.

    No hay endpoint de listado accesible con el bearer, pero la app redirige a
    un proyecto al abrirla, y el id queda en la URL.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=headless)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        ctx.add_cookies(flow_client.load_cookies_for_playwright())
        page = ctx.new_page()
        page.goto(
            "https://labs.google/fx/tools/flow",
            wait_until="networkidle",
            timeout=90000,
        )
        page.wait_for_timeout(4000)
        found = re.search(r"/project/([0-9a-f-]{36})", page.url)
        if not found:
            # si no redirigió, buscar un link a un proyecto en la página
            href = page.evaluate(
                "() => { const a = Array.from(document.querySelectorAll('a'))"
                ".find(a => /\\/project\\/[0-9a-f-]{36}/.test(a.href));"
                " return a ? a.href : null; }"
            )
            if href:
                found = re.search(r"/project/([0-9a-f-]{36})", href)
        browser.close()

    if not found:
        raise RuntimeError(
            "no pude descubrir el projectId. Abrí labs.google/fx/tools/flow, "
            "entrá a un proyecto y copiá el id de la URL."
        )
    return found.group(1)


# ---------------------------------------------------------------- extracción


def extract_vocabulary(code_files: list[dict]) -> dict[str, Any]:
    """Saca de `constants.ts` las listas y objetos que alimentan los dropdowns.

    Los applets de Flow declaran sus opciones como arrays de strings o como
    objetos cuyas claves son las etiquetas visibles. No se ejecuta el código:
    se leen los literales, que es suficiente y no corre nada ajeno.
    """
    vocab: dict[str, Any] = {}
    for f in code_files:
        if not f.get("name", "").endswith("constants.ts"):
            continue
        src = f.get("content", "")
        for m in re.finditer(
            r"export\s+const\s+(\w+)\s*[:=][^=]*?=?\s*(\[|\{)", src
        ):
            name, opener = m.group(1), m.group(2)
            body = _balanced(src, m.end() - 1, opener)
            if body is None:
                continue
            if opener == "[":
                items = re.findall(r"['\"]([^'\"]+)['\"]", body)
                if items and all(len(i) < 80 for i in items):
                    vocab[name] = items
            else:
                keys = re.findall(r"^\s*['\"]?([^'\":\n]+?)['\"]?\s*:", body, re.M)
                keys = [k.strip() for k in keys if k.strip() and len(k) < 80]
                if keys:
                    vocab[name] = keys
    return vocab


def _balanced(src: str, start: int, opener: str) -> str | None:
    closer = "]" if opener == "[" else "}"
    depth = 0
    for i in range(start, min(len(src), start + 200000)):
        if src[i] == opener:
            depth += 1
        elif src[i] == closer:
            depth -= 1
            if depth == 0:
                return src[start + 1 : i]
    return None


# Los FieldDropdown cierran con un icono de chevron, y el nombre del icono
# varía entre applets según qué set de Material Symbols usó el generador.
CHEVRONS = {"keyboard_arrow_down", "expand_more", "arrow_drop_down"}

# Verbos con los que los applets nombran su acción principal, en los idiomas en
# que se los suele escribir. Es más confiable que la posición del botón.
ACTION_VERB = re.compile(
    r"^(generar|generate|forjar|forge|crear|create|compilar|compile|build|"
    r"render|renderizar|export|exportar|procesar|process|analizar|analyze)\b",
    re.I,
)


def inspect_live(applet_id: str, project_id: str, headless: bool = True) -> dict:
    """Controles reales del applet, leídos de la UI montada.

    Deducirlos del JSX con expresiones regulares no es confiable: el orden de
    los props varía, hay componentes envueltos, y el texto del botón se arma en
    runtime. La UI montada es la única fuente que no miente.
    """
    import flow_driver

    with flow_driver.FlowDriver(headless=headless) as drv:
        drv.open(applet_id, project_id=project_id)
        info = drv.describe()

    controls: list[dict] = []
    actions: list[dict] = []

    for b in info.get("buttons", []):
        lines = [ln.strip() for ln in (b.get("text") or "").split("\n") if ln.strip()]
        if not lines:
            continue
        if lines[-1] in CHEVRONS and len(lines) >= 3:
            # "Label", "Valor", chevron
            controls.append(
                {"type": "dropdown", "label": lines[0], "current": lines[-2]}
            )
            continue
        # El resto son acciones. La primera línea suele ser el nombre del icono
        # de Material Symbols (un token sin espacios), y el texto real va después.
        label = lines[-1]
        if len(lines) == 1 and "_" in label and " " not in label:
            continue  # sólo icono, sin texto: no es una acción nombrable
        actions.append({"label": label, "disabled": bool(b.get("disabled"))})

    for i in info.get("textInputs", []):
        if i.get("placeholder"):
            controls.append({"type": "text", "placeholder": i["placeholder"]})

    # El botón de generar se reconoce por el verbo, no por la posición ni por
    # estar habilitado: en varios applets arranca deshabilitado hasta que se
    # sube una imagen, y quedarse con "la última habilitada" agarra un toggle
    # de un segmented control.
    generate = None
    for a in actions:
        if ACTION_VERB.match(a["label"]):
            generate = a["label"]
    if generate is None:
        enabled = [a for a in actions if not a["disabled"]]
        generate = enabled[-1]["label"] if enabled else None
    blocked = [a["label"] for a in actions if a["disabled"]]

    return {
        "controls": controls,
        "generateButton": generate,
        "actions": [a["label"] for a in actions],
        "disabledActions": blocked,
    }


# ---------------------------------------------------------------- scaffolding


def scaffold(
    dest: Path,
    name: str,
    project_id_value: str | None = None,
    applet_filter: str | None = None,
    mine_only: bool = True,
    headless: bool = True,
    inspect_ui: bool = True,
) -> dict:
    """Genera un pack completo leyendo la cuenta de Flow del usuario."""
    dest = Path(dest).expanduser()
    (dest / "recipes").mkdir(parents=True, exist_ok=True)

    pid = project_id_value or os.environ.get("FLOW_PROJECT_ID")
    discovered = False
    if not pid:
        pid = discover_project_id(headless=headless)
        discovered = True

    applets = flow_client.list_applets()
    if mine_only:
        applets = [a for a in applets if not a["appletId"].startswith("community-")]
    if applet_filter:
        f = applet_filter.lower()
        applets = [
            a
            for a in applets
            if f in a.get("displayName", "").lower()
            or f in a.get("description", "").lower()
        ]

    entries: dict[str, Any] = {}
    notes: list[str] = [
        f"# Herramientas del pack `{name}`",
        "",
        "Generado con `flow_scaffold_pack`. Editable a mano: lo que agregues acá",
        "no se pierde salvo que vuelvas a generar sobre el mismo archivo.",
        "",
    ]

    for a in applets:
        applet_id = a["appletId"]
        try:
            data = flow_client.get_applet(applet_id)
        except Exception as e:
            notes.append(f"## {a.get('displayName')}\n\nNo pude leer el código: {e}\n")
            continue
        files = data.get("codeFiles") or []
        vocab = extract_vocabulary(files)

        controls, generate = [], None
        extra_actions, blocked = [], []
        if inspect_ui:
            try:
                live = inspect_live(applet_id, pid, headless=headless)
                controls, generate = live["controls"], live["generateButton"]
                extra_actions = live.get("actions") or []
                blocked = live.get("disabledActions") or []
            except Exception as e:
                notes.append(
                    f"> No pude inspeccionar la UI de este applet: {e}\n"
                    "> Completá `generateButton` y `controls` a mano.\n"
                )

        slug = _slug(a.get("displayName") or applet_id)
        entries[slug] = {
            "actions": extra_actions,
            "disabledActions": blocked,
            "appletId": applet_id,
            "displayName": a.get("displayName"),
            "description": a.get("description"),
            "generateButton": generate,
            "controls": controls,
            "vocabulary": vocab,
        }

        notes.append(f"## {a.get('displayName')}\n")
        notes.append(f"`{applet_id}`\n")
        if a.get("description"):
            notes.append(f"{a['description']}\n")
        if generate:
            notes.append(f"Botón de generar: `{generate}`\n")
        else:
            notes.append(
                "**Sin botón de generar detectado.** Completá `generateButton` "
                "a mano en pack.json.\n"
            )
        if blocked:
            notes.append(
                "Acciones deshabilitadas al abrir: "
                + ", ".join(f"`{b}`" for b in blocked)
                + ". Suelen necesitar un insumo previo, como una imagen "
                "subida, así que este applet puede no ser automatizable todavía.\n"
            )
        if controls:
            notes.append("| Control | Valores |")
            notes.append("|---|---|")
            for c in controls:
                if c["type"] == "dropdown":
                    opts = _options_for(c["label"], vocab, c.get("current"))
                    shown = " · ".join(opts[:12]) if opts else f"(actual: {c.get('current')})"
                    notes.append(f"| `{c['label']}` | {shown} |")
                else:
                    notes.append(f"| _texto_ | placeholder: `{c['placeholder']}` |")
            notes.append("")

        recipe = _starter_recipe(entries[slug])
        if recipe:
            (dest / "recipes" / f"{slug}.json").write_text(
                json.dumps(recipe, indent=2, ensure_ascii=False) + "\n"
            )

    pack = {
        "name": name,
        "description": f"Pack de Google Flow para la cuenta con proyecto {pid}",
        "projectId": pid,
        "applets": entries,
    }
    (dest / PACK_FILE).write_text(json.dumps(pack, indent=2, ensure_ascii=False) + "\n")
    (dest / "applets.md").write_text("\n".join(notes))

    return {
        "packDir": str(dest),
        "projectId": pid,
        "projectIdDiscovered": discovered,
        "applets": len(entries),
        "recipes": [p.name for p in sorted((dest / "recipes").glob("*.json"))],
        "next": "Revisá pack.json y ajustá las recetas; después probá con "
        "flow_dryrun_recipe antes de generar.",
    }


def _options_for(label: str, vocab: dict, current: str | None) -> list[str]:
    """Elige la lista de constants.ts que contiene el valor actual del dropdown.

    Une lo que se ve en la UI (el label y el valor seleccionado) con lo que
    está declarado en el código, sin depender de cómo se llame la constante.
    """
    if current:
        for values in vocab.values():
            if isinstance(values, list) and current in values:
                return values
    return []


def _starter_recipe(entry: dict) -> dict | None:
    if not entry.get("generateButton"):
        return None
    controls = []
    for c in entry.get("controls", []):
        if c["type"] == "dropdown":
            value = c.get("current") or None
            if value:
                controls.append(
                    {"type": "dropdown", "label": c["label"], "value": value}
                )
    return {
        "name": _slug(entry.get("displayName") or "receta"),
        "appletId": entry["appletId"],
        "generateButton": entry["generateButton"],
        "generateTimeoutSec": 420,
        "controls": controls,
        "_comment": "Generada por flow_scaffold_pack con el primer valor de cada "
        "dropdown. Ajustá los valores y agregá 'matrix' para generar en batch.",
    }


def _slug(text: str) -> str:
    import unicodedata

    n = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", n.lower())).strip("-")
