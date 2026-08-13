#!/usr/bin/env python3
"""Cliente de las rutas de Flow protegidas por reCAPTCHA.

Las rutas que gastan cuota (`flow/upsampleImage`, `flowMedia:batchGenerateImage`,
`flow/uploadImage`) exigen un token de reCAPTCHA Enterprise dentro del body, en
`clientContext.recaptchaContext`. Ese token sólo lo puede emitir la página, así
que un cliente HTTP propio recibe 403 PUBLIC_ERROR_UNUSUAL_ACTIVITY.

La salida es hacer el fetch *desde* el contexto de labs.google: se abre la página
con las cookies de sesión, se pide un token con `grecaptcha.enterprise.execute()`
y se dispara el fetch desde ahí, con el origin y los headers reales del sitio.

IMPORTANTE — un browser automatizado no alcanza. Un Chromium lanzado por
Playwright emite tokens que reCAPTCHA Enterprise puntúa bajo y rechaza con
403 PUBLIC_ERROR_UNUSUAL_ACTIVITY. Se verificó que no depende del `action`:
cinco valores distintos (vacío, UPSAMPLE, upsample, upsampleImage, PINHOLE)
dieron el mismo rechazo, probados con un mediaId falso para no gastar créditos.

Por eso las operaciones con costo requieren `--cdp`, que se conecta a un Chrome
normal del usuario en vez de lanzar uno automatizado:

    /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
        --remote-debugging-port=9222

La alternativa es no usar esta ruta: para pixel art `flow_upscale.py` da un
resultado mejor (nearest-neighbor entero, sin interpolar bordes) y no cuesta.

Uso:
    python3 tools/flow/flow_api.py token
    python3 tools/flow/flow_api.py upsample <mediaId> [--resolution 2K] [--cdp URL]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
import flow_packs  # noqa: E402
from flow_client import access_token, load_cookies_for_playwright, sandbox  # noqa: E402

SITE_KEY = "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV"
SANDBOX = "https://aisandbox-pa.googleapis.com/v1"
WARM_URL = "https://labs.google/fx/tools/flow"

UPSAMPLE = {
    "2K": "UPSAMPLE_IMAGE_RESOLUTION_2K",
    "4K": "UPSAMPLE_IMAGE_RESOLUTION_4K",
}


class FlowPageAPI:
    """Sesión de browser usada como puente HTTP hacia las rutas protegidas."""

    def __init__(
        self,
        headless: bool = True,
        project_id: str | None = None,
        cdp: str | None = None,
    ):
        self.headless = headless
        self.project_id = flow_packs.project_id(project_id)
        self.cdp = cdp
        self._pw = None
        self.browser = None
        self.page = None
        self._owns_browser = True
        self._tier = None

    def __enter__(self):
        self._pw = sync_playwright().start()
        if self.cdp:
            # Chrome real del usuario: sus tokens de reCAPTCHA sí pasan.
            self.browser = self._pw.chromium.connect_over_cdp(self.cdp)
            self._owns_browser = False
            ctx = self.browser.contexts[0]
            self.page = ctx.new_page()
        else:
            self.browser = self._pw.chromium.launch(
                channel="chrome", headless=self.headless
            )
            ctx = self.browser.new_context(viewport={"width": 1400, "height": 900})
            ctx.add_cookies(load_cookies_for_playwright())
            self.page = ctx.new_page()
        self.page.goto(WARM_URL, wait_until="domcontentloaded", timeout=90000)
        self._wait_for_grecaptcha()
        return self

    def __exit__(self, *exc):
        if self.browser:
            # Con CDP el browser es del usuario: cerrar sólo la pestaña propia.
            if self._owns_browser:
                self.browser.close()
            elif self.page:
                self.page.close()
        if self._pw:
            self._pw.stop()

    def _wait_for_grecaptcha(self, timeout: float = 45.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            ready = self.page.evaluate(
                "() => !!(window.grecaptcha && window.grecaptcha.enterprise"
                " && window.grecaptcha.enterprise.execute)"
            )
            if ready:
                return
            self.page.wait_for_timeout(1000)
        raise TimeoutError("grecaptcha.enterprise no cargó en la página")

    def recaptcha_token(self, action: str = "") -> str:
        """Token fresco de reCAPTCHA Enterprise. Vive ~2 minutos: pedirlo por uso."""
        return self.page.evaluate(
            """async ({siteKey, action}) => {
                await new Promise(r => window.grecaptcha.enterprise.ready(r));
                const opts = action ? { action } : undefined;
                return await window.grecaptcha.enterprise.execute(siteKey, opts);
            }""",
            {"siteKey": SITE_KEY, "action": action},
        )

    def paygate_tier(self) -> str:
        if self._tier is None:
            try:
                self._tier = sandbox("GET", "credits").get(
                    "userPaygateTier", "PAYGATE_TIER_ONE"
                )
            except Exception:
                self._tier = "PAYGATE_TIER_ONE"
        return self._tier

    def client_context(self, action: str = "", tool: str = "PINHOLE") -> dict:
        return {
            "recaptchaContext": {
                "token": self.recaptcha_token(action),
                "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB",
            },
            "projectId": self.project_id,
            "tool": tool,
            "userPaygateTier": self.paygate_tier(),
            "sessionId": f";{int(time.time() * 1000)}",
        }

    def post(self, path: str, body: dict) -> dict:
        """POST a aisandbox-pa disparado desde el contexto de la página.

        El sitio manda content-type text/plain, no application/json: mandar
        application/json dispararía un preflight CORS que el endpoint no espera.
        """
        result = self.page.evaluate(
            """async ({url, token, body}) => {
                const res = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'authorization': 'Bearer ' + token,
                        'content-type': 'text/plain;charset=UTF-8',
                        'accept': '*/*',
                    },
                    body: JSON.stringify(body),
                });
                const text = await res.text();
                return { status: res.status, text };
            }""",
            {
                "url": f"{SANDBOX}/{path.lstrip('/')}",
                "token": access_token(),
                "body": body,
            },
        )
        if result["status"] >= 400:
            raise RuntimeError(
                f"POST {path} -> {result['status']}\n{result['text'][:1200]}"
            )
        try:
            return json.loads(result["text"])
        except json.JSONDecodeError:
            return {"_raw": result["text"]}

    # ------------------------------------------------------------- operaciones

    def upsample(self, media_id: str, resolution: str = "2K") -> dict:
        if resolution not in UPSAMPLE:
            raise ValueError(f"resolución inválida: {resolution} (usá 2K o 4K)")
        return self.post(
            "flow/upsampleImage",
            {
                "mediaId": media_id,
                "targetResolution": UPSAMPLE[resolution],
                "clientContext": self.client_context(),
            },
        )


def credits_now() -> int | None:
    try:
        return sandbox("GET", "credits").get("credits")
    except Exception:
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Rutas de Flow tras reCAPTCHA")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("token", help="emitir un token de reCAPTCHA (verificación sin costo)")

    u = sub.add_parser("upsample", help="upscalear una imagen ya generada")
    u.add_argument("media_id", help="UUID de generatedImage.mediaId")
    u.add_argument("--resolution", choices=["2K", "4K"], default="2K")
    u.add_argument("--headed", action="store_true")
    u.add_argument(
        "--cdp",
        help="ws/http endpoint de un Chrome real (ej. http://localhost:9222). "
        "Necesario: los tokens de un browser automatizado los rechaza reCAPTCHA.",
    )

    args = ap.parse_args()

    if args.cmd == "token":
        with FlowPageAPI() as api:
            t = api.recaptcha_token()
            print(f"token emitido: {len(t)} chars, empieza con {t[:24]}…")
            print("OK: la página puede emitir tokens. No se gastó nada.")
            print("Ojo: que se emita no implica que el backend lo acepte —")
            print("desde un browser automatizado el score es bajo y da 403.")

    elif args.cmd == "upsample":
        if not args.cdp:
            print(
                "AVISO: sin --cdp esto va a dar 403. reCAPTCHA rechaza los tokens\n"
                "de un browser automatizado. Levantá Chrome con\n"
                "  --remote-debugging-port=9222\n"
                "y pasá --cdp http://localhost:9222\n",
                file=sys.stderr,
            )
        before = credits_now()
        print(f"→ créditos antes: {before}")
        with FlowPageAPI(headless=not args.headed, cdp=args.cdp) as api:
            res = api.upsample(args.media_id, args.resolution)
        after = credits_now()
        cost = (before - after) if None not in (before, after) else "?"
        print(f"→ créditos después: {after}  (costo: {cost})")
        print(json.dumps(res, indent=2, ensure_ascii=False)[:2000])


if __name__ == "__main__":
    main()
