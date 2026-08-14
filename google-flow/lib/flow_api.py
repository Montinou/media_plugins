#!/usr/bin/env python3
"""Client for the Flow routes protected by reCAPTCHA.

The routes that spend quota (`flow/upsampleImage`, `flowMedia:batchGenerateImage`,
`flow/uploadImage`) require a reCAPTCHA Enterprise token inside the body, at
`clientContext.recaptchaContext`. Only the page itself can issue that token,
so a standalone HTTP client gets 403 PUBLIC_ERROR_UNUSUAL_ACTIVITY.

The way out is to make the fetch *from* the labs.google page context: open
the page with the session cookies, request a token with
`grecaptcha.enterprise.execute()`, and fire the fetch from there, with the
site's real origin and headers.

IMPORTANT — an automated browser isn't enough. A Chromium launched by
Playwright issues tokens that reCAPTCHA Enterprise scores low and rejects
with 403 PUBLIC_ERROR_UNUSUAL_ACTIVITY. Verified that it doesn't depend on
the `action`: five different values (empty, UPSAMPLE, upsample,
upsampleImage, PINHOLE) got the same rejection, tested with a fake mediaId
to avoid spending credits.

That's why the operations that cost something require `--cdp`, which
connects to a real Chrome the user already has running instead of launching
an automated one:

    /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
        --remote-debugging-port=9222

The alternative is to avoid this route entirely: for pixel art
`flow_upscale.py` gives a better result (integer nearest-neighbor, no edge
interpolation) and costs nothing.

Usage:
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
    """Browser session used as an HTTP bridge into the protected routes."""

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
            # The user's real Chrome: its reCAPTCHA tokens do get through.
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
            # With CDP the browser belongs to the user: only close our own tab.
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
        raise TimeoutError("grecaptcha.enterprise did not load on the page")

    def recaptcha_token(self, action: str = "") -> str:
        """Fresh reCAPTCHA Enterprise token. Lives ~2 minutes: request one per use."""
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
        """POST to aisandbox-pa fired from the page context.

        The site sends content-type text/plain, not application/json: sending
        application/json would trigger a CORS preflight the endpoint doesn't
        expect.
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

    # ------------------------------------------------------------- operations

    def upsample(self, media_id: str, resolution: str = "2K") -> dict:
        if resolution not in UPSAMPLE:
            raise ValueError(f"invalid resolution: {resolution} (use 2K or 4K)")
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
    ap = argparse.ArgumentParser(description="Flow routes behind reCAPTCHA")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("token", help="issue a reCAPTCHA token (free verification)")

    u = sub.add_parser("upsample", help="upscale an already-generated image")
    u.add_argument("media_id", help="UUID of generatedImage.mediaId")
    u.add_argument("--resolution", choices=["2K", "4K"], default="2K")
    u.add_argument("--headed", action="store_true")
    u.add_argument(
        "--cdp",
        help="ws/http endpoint of a real Chrome (e.g. http://localhost:9222). "
        "Required: reCAPTCHA rejects tokens from an automated browser.",
    )

    args = ap.parse_args()

    if args.cmd == "token":
        with FlowPageAPI() as api:
            t = api.recaptcha_token()
            print(f"token issued: {len(t)} chars, starts with {t[:24]}…")
            print("OK: the page can issue tokens. Nothing was spent.")
            print("Careful: issuing one doesn't mean the backend accepts it —")
            print("from an automated browser the score is low and gets a 403.")

    elif args.cmd == "upsample":
        if not args.cdp:
            print(
                "WARNING: without --cdp this will get a 403. reCAPTCHA rejects\n"
                "tokens from an automated browser. Start Chrome with\n"
                "  --remote-debugging-port=9222\n"
                "and pass --cdp http://localhost:9222\n",
                file=sys.stderr,
            )
        before = credits_now()
        print(f"→ credits before: {before}")
        with FlowPageAPI(headless=not args.headed, cdp=args.cdp) as api:
            res = api.upsample(args.media_id, args.resolution)
        after = credits_now()
        cost = (before - after) if None not in (before, after) else "?"
        print(f"→ credits after: {after}  (cost: {cost})")
        print(json.dumps(res, indent=2, ensure_ascii=False)[:2000])


if __name__ == "__main__":
    main()
