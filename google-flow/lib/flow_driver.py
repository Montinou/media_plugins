#!/usr/bin/env python3
"""Driver de ejecución para applets de Google Labs Flow.

Conduce un applet dentro de su iframe (same-origin) con Playwright: setea los
controles, dispara la generación y captura el resultado.

El upscale es un paso aparte: 2K/4K nativo vive en flow_api.py (necesita un
Chrome real por reCAPTCHA) y el upscale local sin costo, en flow_upscale.py.

No replica el protocolo de generación — que está detrás de reCAPTCHA — sino
que usa la tool tal cual está publicada. Eso lo hace inmune a cambios internos
del payload y respeta la lógica de prompts que vive en cada applet.

Uso:
    python3 tools/flow/flow_driver.py inspect <appletId>
    python3 tools/flow/flow_driver.py run <recipe.json> [-o dir]
    python3 tools/flow/flow_driver.py batch <recipe.json> [--limit N] [-o dir]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Frame, sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from flow_client import (  # noqa: E402
    PROJECT_ID,
    load_cookies_for_playwright,
    sandbox,
)


def credits_balance() -> int | None:
    """Saldo de créditos. Se consulta antes y después para medir el costo real."""
    try:
        return sandbox("GET", "credits").get("credits")
    except Exception:
        return None

OUT_ROOT = Path(os.environ.get("FLOW_OUT", Path.cwd() / "flow-out"))
APPLET_FRAME_TITLE = "Flow App"

# Ritmo deliberadamente humano. Google Labs no publica límites de uso, así que
# el driver se mueve despacio a propósito: es preferible una corrida lenta a que
# nos marquen la cuenta como automatizada.
PACE_MS = 900          # pausa entre interacciones con controles
PACE_RUN_S = 20        # pausa mínima entre ejecuciones consecutivas en batch
POLL_RESULT_S = 4      # cada cuánto se mira si ya salió la imagen



def applet_url(applet_id: str, project_id: str | None = None) -> str:
    import flow_packs

    pid = flow_packs.project_id(project_id)
    return f"https://labs.google/fx/tools/flow/project/{pid}/tool/{applet_id}"


class FlowDriver:
    """Sesión de browser apuntada a un applet."""

    def __init__(self, headless: bool = True, slow_mo: int = 0):
        self.headless = headless
        self.slow_mo = slow_mo
        self._pw = None
        self.browser = None
        self.page = None
        self.network: list[dict] = []

    def __enter__(self):
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(
            channel="chrome", headless=self.headless, slow_mo=self.slow_mo
        )
        ctx = self.browser.new_context(viewport={"width": 1600, "height": 1000})
        ctx.add_cookies(load_cookies_for_playwright())
        self.page = ctx.new_page()
        self.page.on("response", self._on_response)
        return self

    def __exit__(self, *exc):
        if self.browser:
            self.browser.close()
        if self._pw:
            self._pw.stop()

    def _on_response(self, res):
        if "aisandbox-pa" not in res.url and "labs.google" not in res.url:
            return
        entry = {"url": res.url, "status": res.status}
        ct = res.headers.get("content-type", "")
        if "json" in ct and res.status < 400:
            try:
                entry["body"] = res.text()[:200000]
            except Exception:
                pass
        self.network.append(entry)

    # ---------------------------------------------------------------- montaje

    def open(
        self, applet_id: str, timeout: int = 90000, project_id: str | None = None
    ) -> Frame:
        url = applet_url(applet_id, project_id)
        self.page.goto(url, wait_until="networkidle", timeout=timeout)
        return self.wait_for_applet()

    def wait_for_applet(self, timeout: float = 90.0) -> Frame:
        """El applet se compila con esbuild.wasm en el browser; hay que esperarlo.

        No alcanza con que el iframe exista y tenga contenido: React monta los
        controles después, y actuar en esa ventana da "no encontré un control
        con label X" con una lista de botones vacía. Por eso la condición de
        montado es que haya botones renderizados.
        """
        deadline = time.time() + timeout
        last_seen = "ningún iframe con título 'Flow App'"
        while time.time() < deadline:
            for fr in self.page.frames:
                if "recaptcha" in fr.url:
                    continue
                try:
                    if fr.title() != APPLET_FRAME_TITLE:
                        continue
                    buttons = fr.evaluate(
                        "() => document.querySelectorAll('button').length"
                    )
                    if buttons > 0:
                        self.frame = fr
                        return fr
                    last_seen = "el iframe montó pero todavía sin controles"
                except Exception:
                    continue
            self.page.wait_for_timeout(1000)
        raise TimeoutError(
            f"el applet no montó en {timeout}s ({last_seen})"
        )

    # --------------------------------------------------------------- controles

    def describe(self) -> dict:
        """Inventario de controles del applet, para escribir recetas."""
        return self.frame.evaluate("""() => {
            const txt = el => (el.innerText || '').trim();
            return {
                buttons: Array.from(document.querySelectorAll('button')).map(b => ({
                    text: txt(b),
                    disabled: b.disabled,
                })).filter(b => b.text),
                textInputs: Array.from(
                    document.querySelectorAll('input[type=text], textarea')
                ).map(i => ({ placeholder: i.placeholder, value: i.value })),
            };
        }""")

    def set_dropdown(self, label: str, value: str) -> None:
        """Abre el FieldDropdown cuyo label coincide y elige la opción pedida.

        El trigger y las opciones son ambos <button>; se distinguen porque el
        accessible name de una opción es exactamente el valor, mientras que el
        del trigger incluye label, valor y el chevron.
        """
        trigger, current = self._trigger_for(label)
        if value in current:
            return  # ya está; abrir el menú al pedo puede tapar otros controles
        trigger.click()
        self.frame.wait_for_timeout(PACE_MS)

        idx = self._button_index("equals", value)
        if idx < 0:
            opts = self._button_texts()
            raise RuntimeError(
                f"no encontré la opción {value!r} en el dropdown {label!r}. "
                f"Botones visibles: {opts}"
            )
        self.frame.locator("button").nth(idx).click()

        self.frame.wait_for_timeout(PACE_MS)
        _, now = self._trigger_for(label)
        if value not in now:
            raise RuntimeError(
                f"el dropdown {label!r} no quedó en {value!r} (muestra: {now!r})"
            )

    def _button_texts(self) -> list[str]:
        return self.frame.evaluate(
            "() => Array.from(document.querySelectorAll('button'))"
            ".map(b => (b.innerText||'').trim())"
        )

    def _button_index(self, mode: str, needle: str) -> int:
        """Índice del primer <button> cuyo innerText coincide con `needle`.

        `mode` es "equals" (opción de menú) o "startsWith" (trigger, cuyo texto
        sigue con el valor actual y el chevron).
        """
        return self.frame.evaluate(
            """({mode, needle}) => Array.from(document.querySelectorAll('button'))
                .map(b => (b.innerText || '').trim())
                .findIndex(t => mode === 'equals'
                    ? t === needle
                    : t.startsWith(needle))""",
            {"mode": mode, "needle": needle},
        )

    def _trigger_for(self, label: str):
        """El <button> del FieldDropdown cuyo label es `label`, y su texto actual.

        Se localiza por índice sobre innerText en vez de con `has_text`, porque
        ese matcher es substring e insensible a mayúsculas: buscar "Acción"
        engancharía también "Fa*cción* / Linaje". Acá el label debe estar al
        principio del texto del control, que es donde el FieldDropdown lo pone.
        """
        idx = self._button_index("startsWith", label)
        if idx < 0:
            raise RuntimeError(
                f"no encontré un control con label {label!r}. "
                f"Botones: {self._button_texts()}"
            )
        texts = self._button_texts()
        return self.frame.locator("button").nth(idx), texts[idx]

    def fill(self, placeholder_fragment: str, value: str) -> None:
        field = self.frame.get_by_placeholder(
            re.compile(re.escape(placeholder_fragment), re.I)
        ).first
        field.fill(value)

    def click(self, button_text: str) -> None:
        self.frame.get_by_role("button").filter(has_text=button_text).first.click()

    # ---------------------------------------------------------------- resultado

    def current_image_key(self) -> str | None:
        """Huella de la imagen mostrada, para distinguir un resultado nuevo del anterior."""
        return self.frame.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('img'))
                .filter(i => (i.src||'').startsWith('data:image'));
            if (!imgs.length) return null;
            const best = imgs.reduce((a,b) => (b.src.length > a.src.length ? b : a));
            return best.src.length + ':' + best.src.slice(-64);
        }""")

    def wait_for_image(
        self,
        timeout: float = 300.0,
        poll: float = POLL_RESULT_S,
        ignore_key: str | None = None,
    ) -> dict:
        """Espera una imagen resultado (data: URI) en el applet.

        `ignore_key` es la huella del resultado anterior: en batch el applet
        sigue mostrando la imagen previa mientras genera la nueva, así que sin
        esto se devolvería dos veces el mismo asset.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            got = self.frame.evaluate("""() => {
                const imgs = Array.from(document.querySelectorAll('img'))
                    .filter(i => (i.src||'').startsWith('data:image'));
                if (!imgs.length) return null;
                const best = imgs.reduce((a,b) =>
                    (b.src.length > a.src.length ? b : a));
                return {
                    src: best.src,
                    w: best.naturalWidth,
                    h: best.naturalHeight,
                    key: best.src.length + ':' + best.src.slice(-64),
                };
            }""")
            if got and ignore_key and got["key"] == ignore_key:
                got = None  # todavía es el resultado anterior
            if got and got["w"] > 64:
                header, b64 = got["src"].split(",", 1)
                mime = header.split(":")[1].split(";")[0]
                return {
                    "base64": b64,
                    "mimeType": mime,
                    "width": got["w"],
                    "height": got["h"],
                    "mediaId": self.last_media_id(),
                }
            err = self.frame.evaluate("""() => {
                const el = Array.from(document.querySelectorAll('*')).find(e =>
                    /error|falló|fallo|failed/i.test(e.innerText || '') &&
                    (e.innerText||'').length < 200 && e.children.length === 0);
                return el ? el.innerText.trim() : null;
            }""")
            if err:
                raise RuntimeError(f"el applet reportó un error: {err}")
            self.page.wait_for_timeout(int(poll * 1000))
        raise TimeoutError(f"sin imagen resultado tras {timeout}s")

    def last_media_id(self) -> str | None:
        """UUID del último `generatedImage.mediaId` visto en la red.

        Sólo sirve el UUID: junto a él viaja un media-key largo codificado en
        base64 que también se llama mediaId en otros nodos de la respuesta, y
        ése el backend no lo acepta.
        """
        uuid_re = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        for entry in reversed(self.network):
            body = entry.get("body")
            if not body or "generatedImage" not in body:
                continue
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                continue
            found: list[str] = []

            def walk(node):
                if isinstance(node, dict):
                    gen = node.get("generatedImage")
                    if isinstance(gen, dict):
                        mid = gen.get("mediaId")
                        if isinstance(mid, str) and uuid_re.match(mid):
                            found.append(mid)
                    for v in node.values():
                        walk(v)
                elif isinstance(node, list):
                    for v in node:
                        walk(v)

            walk(data)
            if found:
                return found[-1]
        return None

    def dump_network(self, path: Path) -> None:
        path.write_text(json.dumps(self.network, indent=2)[:5_000_000])


# ------------------------------------------------------------------- recetas


def apply_controls(drv: "FlowDriver", recipe: dict) -> None:
    for step in recipe.get("controls", []):
        kind = step["type"]
        if kind == "dropdown":
            print(f"   dropdown {step['label']!r} = {step['value']!r}")
            drv.set_dropdown(step["label"], step["value"])
        elif kind == "text":
            print(f"   texto {step['placeholder']!r}")
            drv.fill(step["placeholder"], step["value"])
        else:
            raise ValueError(f"tipo de control desconocido: {kind}")
        drv.frame.wait_for_timeout(PACE_MS)


def dryrun_recipe(recipe: dict, headless: bool) -> None:
    """Setea todos los controles pero NO dispara la generación: cero costo."""
    with FlowDriver(headless=headless) as drv:
        print(f"→ abriendo applet {recipe['appletId']}")
        drv.open(
            recipe["appletId"],
            timeout=recipe.get("loadTimeoutMs", 90000),
            project_id=recipe.get("projectId"),
        )
        print("→ applet montado")
        apply_controls(drv, recipe)
        print("\n→ estado final de los controles (sin generar):")
        for t in drv._button_texts():
            if t:
                print(f"   · {t.replace(chr(10), ' | ')}")
        print("\nOK: la receta es aplicable. No se disparó ninguna generación.")


def run_recipe(recipe: dict, out_dir: Path, headless: bool) -> dict:
    applet_id = recipe["appletId"]
    out_dir.mkdir(parents=True, exist_ok=True)

    before = credits_balance()
    print(f"→ créditos antes: {before}")

    with FlowDriver(headless=headless) as drv:
        print(f"→ abriendo applet {applet_id}")
        drv.open(applet_id, timeout=recipe.get("loadTimeoutMs", 90000))
        print("→ applet montado")

        apply_controls(drv, recipe)

        print(f"→ disparando: {recipe['generateButton']!r}")
        drv.click(recipe["generateButton"])

        result = drv.wait_for_image(timeout=recipe.get("generateTimeoutSec", 300))
        print(f"→ imagen {result['width']}x{result['height']} mediaId={result['mediaId']}")

        after_gen = credits_balance()
        cost = (before - after_gen) if (before is not None and after_gen is not None) else None
        print(f"→ créditos después: {after_gen}  (costo de la generación: {cost})")

        stem = recipe.get("name", "flow-output")
        raw = out_dir / f"{stem}.png"
        raw.write_bytes(base64.b64decode(result["base64"]))
        print(f"→ guardado {raw}")

        drv.dump_network(out_dir / f"{stem}.network.json")

        meta = {
            "appletId": applet_id,
            "recipe": recipe,
            "width": result["width"],
            "height": result["height"],
            "mediaId": result["mediaId"],
            "file": raw.name,
            "credits": {"before": before, "afterGenerate": after_gen, "cost": cost},
        }


        (out_dir / f"{stem}.meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False)
        )
        return meta


def slug(text: str) -> str:
    import unicodedata

    n = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", n.lower())).strip("-")


def expand_matrix(recipe: dict) -> list[dict]:
    """Producto cartesiano de `matrix` -> una lista de recetas concretas."""
    import itertools

    matrix = recipe.get("matrix") or {}
    if not matrix:
        return [recipe]

    labels = list(matrix)
    out = []
    for combo in itertools.product(*(matrix[k] for k in labels)):
        variant = json.loads(json.dumps(recipe))
        variant.pop("matrix", None)
        assigned = dict(zip(labels, combo))
        # Los valores de la matriz pisan cualquier control fijo del mismo label
        controls = [
            c
            for c in variant.get("controls", [])
            if not (c["type"] == "dropdown" and c["label"] in assigned)
        ]
        for label, value in assigned.items():
            controls.append({"type": "dropdown", "label": label, "value": value})
        variant["controls"] = controls
        variant["name"] = "-".join(slug(v) for v in combo)
        variant["_combo"] = assigned
        out.append(variant)
    return out


def run_batch(
    recipe: dict, out_dir: Path, headless: bool, limit: int | None = None
) -> list[dict]:
    """Ejecuta todas las variantes reutilizando una sola sesión de browser.

    Reusar la pestaña evita recargar el applet en cada ítem: es más rápido y
    genera muchísimo menos tráfico que abrir la página N veces.
    """
    variants = expand_matrix(recipe)
    if limit:
        variants = variants[:limit]
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"→ {len(variants)} variantes a generar")
    for v in variants:
        print(f"   · {v['name']}")

    before_all = credits_balance()
    print(f"→ créditos al inicio: {before_all}\n")

    results = []
    with FlowDriver(headless=headless) as drv:
        drv.open(
            recipe["appletId"],
            timeout=recipe.get("loadTimeoutMs", 90000),
            project_id=recipe.get("projectId"),
        )
        print("→ applet montado\n")

        for i, variant in enumerate(variants, 1):
            name = variant["name"]
            dest = out_dir / f"{name}.png"
            if dest.exists():
                print(f"[{i}/{len(variants)}] {name}: ya existe, salteo")
                continue

            print(f"[{i}/{len(variants)}] {name}")
            try:
                apply_controls(drv, variant)
                previous = drv.current_image_key()
                drv.click(recipe["generateButton"])
                res = drv.wait_for_image(
                    timeout=recipe.get("generateTimeoutSec", 300),
                    ignore_key=previous,
                )
                dest.write_bytes(base64.b64decode(res["base64"]))
                entry = {
                    "name": name,
                    "combo": variant.get("_combo"),
                    "file": dest.name,
                    "width": res["width"],
                    "height": res["height"],
                    "mediaId": res["mediaId"],
                }
                results.append(entry)
                print(f"    ok {res['width']}x{res['height']} -> {dest.name}")
            except Exception as e:
                print(f"    FALLÓ: {str(e)[:200]}")
                results.append({"name": name, "error": str(e)[:500]})

            if i < len(variants):
                print(f"    (pausa {PACE_RUN_S}s)")
                time.sleep(PACE_RUN_S)

    after_all = credits_balance()
    ok = [r for r in results if "error" not in r]
    print(f"\n→ {len(ok)}/{len(variants)} generadas")
    print(f"→ créditos: {before_all} -> {after_all} (costo total: "
          f"{(before_all - after_all) if None not in (before_all, after_all) else '?'})")

    (out_dir / "batch-manifest.json").write_text(
        json.dumps(
            {
                "appletId": recipe["appletId"],
                "batch": recipe.get("name"),
                "creditsBefore": before_all,
                "creditsAfter": after_all,
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description="Driver de applets de Flow")
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("inspect", help="inventariar los controles de un applet")
    i.add_argument("applet_id")
    i.add_argument("--headed", action="store_true")

    d = sub.add_parser(
        "dryrun", help="aplicar la receta sin generar (verificación sin costo)"
    )
    d.add_argument("recipe")
    d.add_argument("--headed", action="store_true")

    r = sub.add_parser("run", help="ejecutar una receta")
    r.add_argument("recipe", help="archivo JSON de receta")
    r.add_argument("-o", "--out", default=str(OUT_ROOT))
    r.add_argument("--headed", action="store_true")

    b = sub.add_parser("batch", help="ejecutar una receta con matriz de variantes")
    b.add_argument("recipe")
    b.add_argument("-o", "--out", default=str(OUT_ROOT))
    b.add_argument("--limit", type=int, help="cortar en las primeras N variantes")
    b.add_argument("--headed", action="store_true")

    args = ap.parse_args()

    if args.cmd == "inspect":
        with FlowDriver(headless=not args.headed) as drv:
            drv.open(args.applet_id)
            info = drv.describe()
            print(json.dumps(info, indent=2, ensure_ascii=False))

    elif args.cmd == "dryrun":
        dryrun_recipe(json.loads(Path(args.recipe).read_text()), not args.headed)

    elif args.cmd == "run":
        recipe = json.loads(Path(args.recipe).read_text())
        run_recipe(recipe, Path(args.out), not args.headed)

    elif args.cmd == "batch":
        recipe = json.loads(Path(args.recipe).read_text())
        run_batch(recipe, Path(args.out), not args.headed, args.limit)


if __name__ == "__main__":
    main()
