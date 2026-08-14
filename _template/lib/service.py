"""Base client for a service with a browser session.

This file is the **reusable core**: it contains no project-specific
identifiers. Copy it, rename `SERVICE` and the endpoints, and you have a
client that follows house rules (slow, paced requests, credentials outside
the repo, actionable auth errors).

Anything specific to your project — applet ids, prompts, presets — does NOT
go here: it goes in `packs/<project>/`. See `packs/README.md`.

No dependencies outside the stdlib: Homebrew's Python is under PEP 668 and
we don't want to force `--break-system-packages`.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# --- customize this ---------------------------------------------------------
SERVICE = "example"                              # short plugin name
BASE = "https://api.example.com"                 # API base URL
COOKIE_FILENAME = "example.com.cookies.json"     # as exported by the browser
MIN_INTERVAL = 2.5                               # seconds between requests
# ---------------------------------------------------------------------------

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)


class ServiceError(RuntimeError):
    """Operational failure (HTTP, parsing, etc.)."""


class ServiceAuthError(ServiceError):
    """The session isn't usable. Always carries an actionable message:
    whoever receives it should ask the user to re-export the cookies, not
    retry."""


def find_cookies(explicit: str | os.PathLike | None = None) -> Path:
    """Locates the cookies JSON without assuming a repo structure.

    An explicit path is a claim about WHICH account to use: if it doesn't
    exist, we fail instead of silently falling back to another file
    (silently using the wrong account is worse than an error).
    """
    env_var = f"{SERVICE.upper()}_COOKIES"
    for source, value in (("argument", explicit), (env_var, os.environ.get(env_var))):
        if value:
            p = Path(value).expanduser()
            if not p.is_file():
                raise ServiceAuthError(
                    f"The {source} points to {p}, which doesn't exist. I "
                    "won't look elsewhere to avoid using a different "
                    "account than the one you asked for."
                )
            return p

    candidates: list[Path] = []
    cwd = Path.cwd().resolve()
    for d in (cwd, *cwd.parents):          # the project being worked on
        candidates.append(d / COOKIE_FILENAME)
    candidates.append(Path.home() / ".config" / SERVICE / "cookies.json")
    candidates.append(Path.home() / ".config" / SERVICE / COOKIE_FILENAME)

    for c in candidates:
        if c.is_file():
            return c
    raise ServiceAuthError(
        f"Couldn't find {COOKIE_FILENAME}. Export {SERVICE}'s cookies while "
        f"logged in to ~/.config/{SERVICE}/cookies.json, or point "
        f"{env_var} at the file."
    )


class Service:
    def __init__(
        self,
        cookies_path: str | os.PathLike | None = None,
        min_interval: float = MIN_INTERVAL,
    ):
        self.cookies_path = find_cookies(cookies_path)
        self.min_interval = min_interval
        self._last_call = 0.0
        try:
            self._cookies = json.loads(self.cookies_path.read_text())
        except json.JSONDecodeError as e:
            raise ServiceAuthError(
                f"{self.cookies_path} isn't valid JSON ({e}). Re-export the cookies."
            ) from e

    # ------------------------------------------------------------------ auth

    def auth_status(self) -> dict[str, Any]:
        """LOCAL diagnostic, without touching the network.

        Adapt it to your service's schema: if it uses a JWT, decode the
        payload and return `expires_in_seconds`; if it uses an opaque
        cookie, at least verify the session cookies are present.
        """
        names = {c["name"] for c in self._cookies}
        session_cookies = {"session", "__session", "auth_token"} & names
        return {
            "cookies_file": str(self.cookies_path),
            "cookie_count": len(self._cookies),
            "has_session_cookie": bool(session_cookies),
            "valid": bool(session_cookies),
        }

    # -------------------------------------------------------------- transport

    def _throttle(self) -> None:
        """Slow, paced requests. Don't remove this: it's the difference
        between a healthy account and one flagged as automated."""
        delta = time.monotonic() - self._last_call
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)
        self._last_call = time.monotonic()

    def call(self, method: str, path: str, body: Any = None, raw: bool = False) -> Any:
        cookie = "; ".join(f"{c['name']}={c['value']}" for c in self._cookies)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{BASE}{path}",
            data=data,
            method=method.upper(),
            headers={
                "Cookie": cookie,
                "User-Agent": UA,
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if data else {}),
            },
        )
        self._throttle()
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                payload = r.read()
                return payload if raw else json.loads(payload)
        except urllib.error.HTTPError as e:
            detail = e.read()[:300].decode("utf-8", "replace")
            if e.code in (401, 403):
                raise ServiceAuthError(
                    f"{e.code} on {path}. The session may have expired; "
                    f"re-export {SERVICE}'s cookies."
                ) from e
            raise ServiceError(f"{method.upper()} {path} -> {e.code}: {detail}") from e

    def download(self, url: str, dest: str | os.PathLike) -> dict:
        """Paced download. Never in parallel."""
        p = Path(dest).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        self._throttle()
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=300) as r:
            p.write_bytes(r.read())
        return {"path": str(p), "bytes": p.stat().st_size}


# --------------------------------------------------------------------------- CLI


def main() -> int:
    """Expose the same capabilities as the MCP tools, from a terminal.

    Worth keeping: an agent is not the only caller. Scripts, cron jobs and a
    quick manual check all want the same operations, and writing them twice is
    how the two copies drift apart.

    Mirror your MCP tools here one to one, print JSON, and use the exit code to
    distinguish "renew the session" (2) from any other failure (1).
    """
    import argparse
    import sys

    p = argparse.ArgumentParser(prog=SERVICE, description=f"{SERVICE} client")
    p.add_argument("-c", "--cookies", help="path to the cookies JSON")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="session state — local, no network")
    # Add one subparser per operation, matching your tools.

    a = p.parse_args()

    try:
        svc = Service(a.cookies)
        if a.cmd == "status":
            out = svc.auth_status()
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    except ServiceAuthError as e:
        print(f"authentication: {e}", file=sys.stderr)
        return 2
    except ServiceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
