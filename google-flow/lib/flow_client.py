#!/usr/bin/env python3
"""HTTP client for Google Labs Flow (applets / tools).

Two-hop authentication:
    NextAuth cookie  ->  GET labs.google/fx/api/auth/session  ->  access_token
    access_token     ->  Authorization: Bearer  ->  aisandbox-pa.googleapis.com

The session cookie lives for months; the bearer lasts hours. That's why the
bearer is re-derived from the cookie on every run and cached to disk until
it expires.

Usage:
    python3 google-flow/lib/flow_client.py whoami
    python3 google-flow/lib/flow_client.py list
    python3 google-flow/lib/flow_client.py get <appletId>
    python3 google-flow/lib/flow_client.py code <appletId> [-o dest.jsx]
    python3 google-flow/lib/flow_client.py sessions
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

COOKIE_NAME = "labs.google.cookies.json"

CONFIG_DIR = Path(
    os.environ.get("FLOW_CONFIG_DIR", Path.home() / ".config" / "google-flow")
)


def _find_cookies() -> Path:
    """Locates the cookies file without assuming a repo structure.

    Order: environment variable, the user's config directory, and the cwd
    walking up toward the root — this works both when installed and inside
    a project that keeps its cookies at the root.
    """
    if os.environ.get("FLOW_COOKIES"):
        return Path(os.environ["FLOW_COOKIES"])
    candidates = [CONFIG_DIR / COOKIE_NAME]
    cwd = Path.cwd().resolve()
    candidates += [d / COOKIE_NAME for d in [cwd, *cwd.parents]]
    for c in candidates:
        if c.exists():
            return c
    return CONFIG_DIR / COOKIE_NAME  # so the error message names the canonical spot


COOKIE_PATH = _find_cookies()
TOKEN_CACHE = Path(
    os.environ.get("FLOW_TOKEN_CACHE", CONFIG_DIR / ".flow-token.json")
)
# No default: the project belongs to each account. Resolved by
# flow_packs.project_id(), which checks the environment and the active pack.
PROJECT_ID = os.environ.get("FLOW_PROJECT_ID")

LABS = "https://labs.google/fx"
SANDBOX = "https://aisandbox-pa.googleapis.com/v1"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


class FlowAuthError(RuntimeError):
    """The session cookie no longer works: re-export it from the browser."""


# --------------------------------------------------------------------------- auth


def _cookie_jar() -> dict[str, str]:
    if not COOKIE_PATH.exists():
        raise FlowAuthError(
            f"can't find the cookies at {COOKIE_PATH}. Export the labs.google "
            f"ones from the browser to that path, or point FLOW_COOKIES at "
            f"the file."
        )
    raw = json.loads(COOKIE_PATH.read_text())
    jar = {}
    now = time.time()
    for c in raw:
        exp = c.get("expires") or c.get("expirationDate") or 0
        if exp and 0 < exp < now:
            continue  # expired
        if "labs.google" in c.get("domain", ""):
            jar[c["name"]] = c["value"]
    if "__Secure-next-auth.session-token" not in jar:
        raise FlowAuthError(
            "missing the __Secure-next-auth.session-token cookie (or it's "
            "expired). Re-export the labs.google cookies from the browser."
        )
    return jar


def load_cookies_for_playwright() -> list[dict]:
    """The same cookies, in the format `context.add_cookies()` expects."""
    raw = json.loads(COOKIE_PATH.read_text())
    out = []
    for c in raw:
        ck = {
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"],
            "path": c.get("path", "/"),
            "secure": c.get("secure", True),
            "httpOnly": c.get("httpOnly", False),
            "sameSite": "Lax",
        }
        exp = c.get("expires") or c.get("expirationDate")
        if exp and exp > 0:
            ck["expires"] = float(exp)
        out.append(ck)
    return out


def _fetch_access_token() -> tuple[str, float]:
    r = requests.get(
        f"{LABS}/api/auth/session",
        cookies=_cookie_jar(),
        headers={"User-Agent": UA, "Accept": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    # `expires` is the NextAuth session deadline. Past it, the endpoint still
    # returns an access_token — an expired one — so without this check the
    # failure surfaces later as an opaque 401 from googleapis that says nothing
    # about what to do.
    expires = data.get("expires")
    if expires:
        try:
            exp = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if exp < datetime.now(timezone.utc):
                raise FlowAuthError(
                    f"the Flow session expired on {expires}. Re-export the "
                    f"labs.google cookies from the browser to {COOKIE_PATH}."
                )
        except ValueError:
            pass  # unexpected format: let it through and fail later if it fails

    token = data.get("access_token")
    if not token:
        raise FlowAuthError(
            "the session responded without an access_token — the cookie is "
            "no longer valid. Re-export the labs.google cookies."
        )
    # `expires` is the NextAuth session's expiration; the bearer usually lasts
    # less. We cache with a conservative margin.
    expires_at = time.time() + 45 * 60
    return token, expires_at


def access_token(force_refresh: bool = False) -> str:
    if not force_refresh and TOKEN_CACHE.exists():
        try:
            cached = json.loads(TOKEN_CACHE.read_text())
            if cached.get("expires_at", 0) > time.time() + 60:
                return cached["token"]
        except (json.JSONDecodeError, KeyError):
            pass
    token, expires_at = _fetch_access_token()
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(json.dumps({"token": token, "expires_at": expires_at}))
    TOKEN_CACHE.chmod(0o600)
    return token


def session_info() -> dict:
    r = requests.get(
        f"{LABS}/api/auth/session",
        cookies=_cookie_jar(),
        headers={"User-Agent": UA, "Accept": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# ------------------------------------------------------------------------ sandbox


def sandbox(method: str, path: str, *, params=None, json_body=None, retry_auth=True):
    url = f"{SANDBOX}/{path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {access_token()}",
        "User-Agent": UA,
        "Accept": "*/*",
        "Origin": "https://labs.google",
        "Referer": "https://labs.google/",
        "Content-Type": "application/json",
    }
    r = requests.request(
        method, url, headers=headers, params=params, json=json_body, timeout=120
    )
    if r.status_code in (401, 403) and retry_auth:
        access_token(force_refresh=True)
        return sandbox(method, path, params=params, json_body=json_body, retry_auth=False)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code}\n{r.text[:1500]}")
    if not r.content:
        return {}
    try:
        return r.json()
    except json.JSONDecodeError:
        return {"_raw": r.text}


# --------------------------------------------------------------------------- API


def list_applets() -> list[dict]:
    return sandbox("GET", "flowAppletAgent/applets").get("applets", [])


def get_applet(applet_id: str, version_id: str | None = None) -> dict:
    if version_id is None:
        match = next(
            (a for a in list_applets() if a["appletId"] == applet_id), None
        )
        if match is None:
            raise SystemExit(f"applet {applet_id} does not exist")
        version_id = match["currentVersionId"]
    return sandbox("GET", f"flowAppletAgent/applets/{applet_id}/versions/{version_id}")


def creation_sessions(project_id: str | None = None) -> dict:
    import flow_packs

    return sandbox(
        "GET",
        "flowCreationAgent/sessions",
        params={"projectId": flow_packs.project_id(project_id)},
    )


# --------------------------------------------------------------------------- CLI


def main() -> None:
    ap = argparse.ArgumentParser(description="Google Labs Flow client")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami", help="verify session")
    sub.add_parser("list", help="list applets/tools")
    sub.add_parser("sessions", help="creation agent sessions")

    g = sub.add_parser("get", help="full definition of an applet")
    g.add_argument("applet_id")

    c = sub.add_parser("code", help="extract the applet's source code")
    c.add_argument("applet_id")
    c.add_argument("-o", "--out", help="destination file")

    pl = sub.add_parser("pull", help="download all of an applet's source files")
    pl.add_argument("applet_id")
    pl.add_argument("-d", "--dir", help="destination directory")

    ss = sub.add_parser(
        "session", help="conversation with the creation agent that produced the applet"
    )
    ss.add_argument("applet_id")

    args = ap.parse_args()

    if args.cmd == "whoami":
        info = session_info()
        user = info.get("user", {})
        print(f"user    : {user.get('name')} <{user.get('email')}>")
        print(f"session : expires {info.get('expires')}")
        print(f"bearer  : {'OK' if info.get('access_token') else 'MISSING'}")

    elif args.cmd == "list":
        applets = list_applets()
        print(f"{len(applets)} applets\n")
        for a in applets:
            fav = "★" if a.get("isFavorited") else " "
            print(f"{fav} {a['displayName']}")
            print(f"    id      : {a['appletId']}")
            print(f"    version : {a['currentVersionId']}")
            print(f"    desc    : {a.get('description','')[:100]}")
            print(f"    updated : {a.get('updateTime','')}")
            print()

    elif args.cmd == "get":
        print(json.dumps(get_applet(args.applet_id), indent=2, ensure_ascii=False))

    elif args.cmd == "code":
        data = get_applet(args.applet_id)
        code = _extract_code(data)
        if args.out:
            Path(args.out).write_text(code)
            print(f"written to {args.out} ({len(code)} bytes)")
        else:
            print(code)

    elif args.cmd == "pull":
        data = get_applet(args.applet_id)
        # Defaults to the current directory: this is a CLI and the plugin must
        # not assume it lives inside any particular repo.
        dest = Path(args.dir or Path.cwd() / "applets" / args.applet_id)
        dest.mkdir(parents=True, exist_ok=True)
        files = data.get("codeFiles") or []
        for f in files:
            (dest / f["name"]).parent.mkdir(parents=True, exist_ok=True)
            (dest / f["name"]).write_text(f.get("content", ""))
            print(f"  {f['name']:<28} {len(f.get('content','')):>7} bytes")
        if data.get("codeContent"):
            (dest / "_bundle.txt").write_text(data["codeContent"])
            print(f"  {'_bundle.txt':<28} {len(data['codeContent']):>7} bytes")
        meta = {
            k: v for k, v in data.get("appletVersion", {}).items() if k != "codeBlobref"
        }
        (dest / "_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        print(f"\n{len(files)} files in {dest}")

    elif args.cmd == "session":
        data = get_applet(args.applet_id)
        events = (data.get("appletSession") or {}).get("events") or []
        print(f"{len(events)} events\n")
        for i, ev in enumerate(events):
            author = ev.get("author", "?")
            text = ev.get("text", "")
            print(f"--- [{i}] {author} ({len(text)} chars) " + "-" * 40)
            print(text)
            print()

    elif args.cmd == "sessions":
        print(json.dumps(creation_sessions(), indent=2, ensure_ascii=False))


def _extract_code(data: dict) -> str:
    """Looks for the code field inside the applet definition."""
    hits: list[tuple[str, str]] = []

    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str) and len(node) > 400:
            hits.append((path, node))

    walk(data)
    if not hits:
        return json.dumps(data, indent=2, ensure_ascii=False)
    hits.sort(key=lambda t: len(t[1]), reverse=True)
    path, code = hits[0]
    print(f"// field: {path}", file=sys.stderr)
    return code


if __name__ == "__main__":
    try:
        main()
    except FlowAuthError as e:
        print(f"AUTHENTICATION ERROR: {e}", file=sys.stderr)
        sys.exit(2)
