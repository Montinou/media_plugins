#!/usr/bin/env python3
"""Cliente HTTP para Google Labs Flow (applets / tools).

Autenticación en dos saltos:
    cookie NextAuth  ->  GET labs.google/fx/api/auth/session  ->  access_token
    access_token     ->  Authorization: Bearer  ->  aisandbox-pa.googleapis.com

La cookie de sesión vive meses; el bearer dura horas. Por eso el bearer se
re-deriva de la cookie en cada ejecución y se cachea en disco hasta que expira.

Uso:
    python3 tools/flow/flow_client.py whoami
    python3 tools/flow/flow_client.py list
    python3 tools/flow/flow_client.py get <appletId>
    python3 tools/flow/flow_client.py code <appletId> [-o destino.jsx]
    python3 tools/flow/flow_client.py sessions
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

COOKIE_NAME = "labs.google.cookies.json"

# El plugin se llamaba `aerthos-flow` antes de volverse genérico. Preferimos el
# nombre nuevo, pero seguimos leyendo el viejo para no romper instalaciones que
# ya tienen las cookies puestas.
_CONFIG_CANDIDATES = [
    Path.home() / ".config" / "google-flow",
    Path.home() / ".config" / "aerthos-flow",
]

if _env := os.environ.get("FLOW_CONFIG_DIR"):
    CONFIG_DIR = Path(_env)
else:
    CONFIG_DIR = next(
        (d for d in _CONFIG_CANDIDATES if (d / COOKIE_NAME).is_file()),
        _CONFIG_CANDIDATES[0],
    )


def _find_cookies() -> Path:
    """Ubica el archivo de cookies sin asumir una estructura de repo.

    Orden: variable de entorno, directorio de config del usuario, y el cwd
    subiendo hacia la raíz — así funciona tanto instalado como dentro de un
    proyecto que guarde sus cookies en la raíz.
    """
    if os.environ.get("FLOW_COOKIES"):
        return Path(os.environ["FLOW_COOKIES"])
    candidates = [CONFIG_DIR / COOKIE_NAME]
    cwd = Path.cwd().resolve()
    candidates += [d / COOKIE_NAME for d in [cwd, *cwd.parents]]
    for c in candidates:
        if c.exists():
            return c
    return CONFIG_DIR / COOKIE_NAME  # para que el error nombre el lugar canónico


COOKIE_PATH = _find_cookies()
TOKEN_CACHE = Path(
    os.environ.get("FLOW_TOKEN_CACHE", CONFIG_DIR / ".flow-token.json")
)
# Sin default: el proyecto es de cada cuenta. Lo resuelve flow_packs.project_id(),
# que mira el entorno y el pack activo.
PROJECT_ID = os.environ.get("FLOW_PROJECT_ID")

LABS = "https://labs.google/fx"
SANDBOX = "https://aisandbox-pa.googleapis.com/v1"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


class FlowAuthError(RuntimeError):
    """La cookie de sesión no sirve más: hay que reexportarla del navegador."""


# --------------------------------------------------------------------------- auth


def _cookie_jar() -> dict[str, str]:
    if not COOKIE_PATH.exists():
        raise FlowAuthError(
            f"no encuentro las cookies en {COOKIE_PATH}. Exportá las de "
            f"labs.google desde el navegador a esa ruta, o apuntá "
            f"FLOW_COOKIES al archivo."
        )
    raw = json.loads(COOKIE_PATH.read_text())
    jar = {}
    now = time.time()
    for c in raw:
        exp = c.get("expires") or c.get("expirationDate") or 0
        if exp and 0 < exp < now:
            continue  # vencida
        if "labs.google" in c.get("domain", ""):
            jar[c["name"]] = c["value"]
    if "__Secure-next-auth.session-token" not in jar:
        raise FlowAuthError(
            "falta la cookie __Secure-next-auth.session-token (o está vencida). "
            "Reexportá las cookies de labs.google desde el navegador."
        )
    return jar


def load_cookies_for_playwright() -> list[dict]:
    """Las mismas cookies, en el formato que espera `context.add_cookies()`."""
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
    token = data.get("access_token")
    if not token:
        raise FlowAuthError(
            "la sesión respondió sin access_token — la cookie ya no es válida. "
            "Reexportá las cookies de labs.google."
        )
    # `expires` es el vencimiento de la sesión NextAuth; el bearer suele durar menos.
    # Cacheamos con margen conservador.
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
            raise SystemExit(f"no existe el applet {applet_id}")
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
    ap = argparse.ArgumentParser(description="Cliente de Google Labs Flow")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami", help="verificar sesión")
    sub.add_parser("list", help="listar applets/tools")
    sub.add_parser("sessions", help="sesiones del agente creador")

    g = sub.add_parser("get", help="definición completa de un applet")
    g.add_argument("applet_id")

    c = sub.add_parser("code", help="extraer el código fuente del applet")
    c.add_argument("applet_id")
    c.add_argument("-o", "--out", help="archivo destino")

    pl = sub.add_parser("pull", help="bajar todos los archivos fuente de un applet")
    pl.add_argument("applet_id")
    pl.add_argument("-d", "--dir", help="directorio destino")

    ss = sub.add_parser(
        "session", help="conversación con el agente creador que produjo el applet"
    )
    ss.add_argument("applet_id")

    args = ap.parse_args()

    if args.cmd == "whoami":
        info = session_info()
        user = info.get("user", {})
        print(f"usuario : {user.get('name')} <{user.get('email')}>")
        print(f"sesión  : expira {info.get('expires')}")
        print(f"bearer  : {'OK' if info.get('access_token') else 'AUSENTE'}")

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
            print(f"escrito en {args.out} ({len(code)} bytes)")
        else:
            print(code)

    elif args.cmd == "pull":
        data = get_applet(args.applet_id)
        dest = Path(args.dir or REPO / "tools/flow/applets" / args.applet_id)
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
        print(f"\n{len(files)} archivos en {dest}")

    elif args.cmd == "session":
        data = get_applet(args.applet_id)
        events = (data.get("appletSession") or {}).get("events") or []
        print(f"{len(events)} eventos\n")
        for i, ev in enumerate(events):
            author = ev.get("author", "?")
            text = ev.get("text", "")
            print(f"--- [{i}] {author} ({len(text)} chars) " + "-" * 40)
            print(text)
            print()

    elif args.cmd == "sessions":
        print(json.dumps(creation_sessions(), indent=2, ensure_ascii=False))


def _extract_code(data: dict) -> str:
    """Busca el campo de código dentro de la definición del applet."""
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
    print(f"// campo: {path}", file=sys.stderr)
    return code


if __name__ == "__main__":
    try:
        main()
    except FlowAuthError as e:
        print(f"ERROR DE AUTENTICACIÓN: {e}", file=sys.stderr)
        sys.exit(2)
