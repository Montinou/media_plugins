#!/usr/bin/env python3
"""Packs: the part of google-flow that belongs to each account.

The plugin is generic — its tools work with any account and any applet —
but three things are irreducibly specific to whoever uses it:

    projectId    the Flow project, which goes in every applet's URL
    appletIds    the identifiers of its tools
    vocabularies the valid values for those tools' dropdowns

A pack groups that into a directory, so the plugin doesn't ship anyone's
project hardcoded:

    <pack>/
    ├── pack.json          projectId, applets, and their controls
    ├── applets.md         notes on what each tool does
    └── recipes/*.json     ready-to-use recipes

`flow_scaffold_pack` generates one by reading the account: discovers the
project, lists the applets, downloads their code, and extracts the
vocabularies from `constants.ts`.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import flow_client

PACK_FILE = "pack.json"


# ------------------------------------------------------------------ location


def pack_dir() -> Path | None:
    """Active pack's directory, or None if none is configured."""
    env = os.environ.get("FLOW_PACK")
    if env:
        p = Path(env).expanduser()
        return p if (p / PACK_FILE).exists() else None
    # packs/<name> next to the lib, chosen via FLOW_PACK_NAME
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
    """Resolves the projectId: parameter, environment, pack. No made-up default."""
    if explicit:
        return explicit
    if os.environ.get("FLOW_PROJECT_ID"):
        return os.environ["FLOW_PROJECT_ID"]
    pack = load_pack()
    if pack and pack.get("projectId"):
        return pack["projectId"]
    raise RuntimeError(
        "don't know which Flow project to work with. Set FLOW_PROJECT_ID, or "
        "generate a pack with flow_scaffold_pack, or pass an explicit "
        "project_id. The id is in the URL: labs.google/fx/tools/flow/project/<projectId>/…"
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
            "no active pack: set FLOW_PACK or pass the full recipe."
        )
    f = (d / "recipes" / f"{name}.json") if not name.endswith(".json") else Path(name)
    if not f.exists():
        available = [r["name"] for r in list_recipes()]
        raise RuntimeError(
            f"recipe {name!r} doesn't exist in the pack. Available: {available}"
        )
    return json.loads(f.read_text())


def _matrix_size(recipe: dict) -> int:
    m = recipe.get("matrix") or {}
    n = 1
    for values in m.values():
        n *= max(1, len(values))
    return n if m else 1


# ----------------------------------------------------------------- discovery


def discover_project_id(headless: bool = True) -> str:
    """Discovers the projectId by opening Flow and seeing which project it lands on.

    There's no listing endpoint accessible with the bearer, but the app
    redirects to a project when you open it, and the id ends up in the URL.
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
            # if it didn't redirect, look for a link to a project on the page
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
            "couldn't discover the projectId. Open labs.google/fx/tools/flow, "
            "go into a project, and copy the id from the URL."
        )
    return found.group(1)


# ---------------------------------------------------------------- extraction


def extract_vocabulary(code_files: list[dict]) -> dict[str, Any]:
    """Pulls the lists and objects that feed the dropdowns out of `constants.ts`.

    Flow applets declare their options as arrays of strings or as objects
    whose keys are the visible labels. The code isn't executed: the literals
    are read directly, which is enough and doesn't run anything foreign.
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


# FieldDropdowns end with a chevron icon, and the icon's name varies between
# applets depending on which Material Symbols set the generator used.
CHEVRONS = {"keyboard_arrow_down", "expand_more", "arrow_drop_down"}

# Verbs applets use to name their main action, in the languages they tend to
# be written in. More reliable than the button's position.
ACTION_VERB = re.compile(
    r"^(generar|generate|forjar|forge|crear|create|compilar|compile|build|"
    r"render|renderizar|export|exportar|procesar|process|analizar|analyze)\b",
    re.I,
)


def inspect_live(applet_id: str, project_id: str, headless: bool = True) -> dict:
    """Real controls of the applet, read from the mounted UI.

    Deducing them from the JSX with regular expressions isn't reliable: prop
    order varies, there are wrapped components, and the button text is built
    at runtime. The mounted UI is the only source that doesn't lie.
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
            # "Label", "Value", chevron
            controls.append(
                {"type": "dropdown", "label": lines[0], "current": lines[-2]}
            )
            continue
        # The rest are actions. The first line is usually the Material
        # Symbols icon name (a token with no spaces), and the real text follows.
        label = lines[-1]
        if len(lines) == 1 and "_" in label and " " not in label:
            continue  # icon only, no text: not a nameable action
        actions.append({"label": label, "disabled": bool(b.get("disabled"))})

    for i in info.get("textInputs", []):
        if i.get("placeholder"):
            controls.append({"type": "text", "placeholder": i["placeholder"]})

    # The generate button is recognized by its verb, not by position or by
    # being enabled: several applets start disabled until an image is
    # uploaded, and taking "the last enabled one" would grab a toggle from a
    # segmented control.
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
    """Generates a full pack by reading the user's Flow account."""
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
        f"# Tools in pack `{name}`",
        "",
        "Generated with `flow_scaffold_pack`. Editable by hand: anything you",
        "add here isn't lost unless you regenerate over the same file.",
        "",
    ]

    for a in applets:
        applet_id = a["appletId"]
        try:
            data = flow_client.get_applet(applet_id)
        except Exception as e:
            notes.append(f"## {a.get('displayName')}\n\nCouldn't read the code: {e}\n")
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
                    f"> Couldn't inspect this applet's UI: {e}\n"
                    "> Fill in `generateButton` and `controls` by hand.\n"
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
            notes.append(f"Generate button: `{generate}`\n")
        else:
            notes.append(
                "**No generate button detected.** Fill in `generateButton` "
                "by hand in pack.json.\n"
            )
        if blocked:
            notes.append(
                "Actions disabled on open: "
                + ", ".join(f"`{b}`" for b in blocked)
                + ". They usually need a prior input, like an uploaded "
                "image, so this applet may not be automatable yet.\n"
            )
        if controls:
            notes.append("| Control | Values |")
            notes.append("|---|---|")
            for c in controls:
                if c["type"] == "dropdown":
                    opts = _options_for(c["label"], vocab, c.get("current"))
                    shown = " · ".join(opts[:12]) if opts else f"(current: {c.get('current')})"
                    notes.append(f"| `{c['label']}` | {shown} |")
                else:
                    notes.append(f"| _text_ | placeholder: `{c['placeholder']}` |")
            notes.append("")

        recipe = _starter_recipe(entries[slug])
        if recipe:
            (dest / "recipes" / f"{slug}.json").write_text(
                json.dumps(recipe, indent=2, ensure_ascii=False) + "\n"
            )

    pack = {
        "name": name,
        "description": f"Google Flow pack for the account with project {pid}",
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
        "next": "Review pack.json and adjust the recipes; then test with "
        "flow_dryrun_recipe before generating.",
    }


def _options_for(label: str, vocab: dict, current: str | None) -> list[str]:
    """Picks the constants.ts list that contains the dropdown's current value.

    Ties together what's visible in the UI (the label and the selected
    value) with what's declared in the code, without depending on the
    constant's name.
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
        "name": _slug(entry.get("displayName") or "recipe"),
        "appletId": entry["appletId"],
        "generateButton": entry["generateButton"],
        "generateTimeoutSec": 420,
        "controls": controls,
        "_comment": "Generated by flow_scaffold_pack with each dropdown's first "
        "value. Adjust the values and add 'matrix' to generate in batch.",
    }


def _slug(text: str) -> str:
    import unicodedata

    n = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", n.lower())).strip("-")
