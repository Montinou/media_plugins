"""Cliente base para un servicio con sesión de navegador.

Este archivo es el **core reusable**: no contiene ningún identificador de
proyecto. Copialo, renombrá `SERVICE` y los endpoints, y ya tenés un cliente que
respeta las reglas de la casa (ritmo pausado, credenciales fuera del repo,
errores de auth accionables).

Lo específico de tu proyecto —ids de applets, prompts, presets— NO va acá:
va en `packs/<proyecto>/`. Ver `packs/README.md`.

Sin dependencias fuera de la stdlib: el Python de Homebrew está bajo PEP 668 y
no queremos forzar `--break-system-packages`.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# --- personalizá esto -------------------------------------------------------
SERVICE = "example"                              # nombre corto del plugin
BASE = "https://api.example.com"                 # base de la API
COOKIE_FILENAME = "example.com.cookies.json"     # como lo exporta el navegador
MIN_INTERVAL = 2.5                               # segundos entre requests
# ---------------------------------------------------------------------------

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)


class ServiceError(RuntimeError):
    """Fallo operativo (HTTP, parseo, etc.)."""


class ServiceAuthError(ServiceError):
    """La sesión no sirve. Siempre con un mensaje accionable: quien la reciba
    debe pedirle al usuario que reexporte las cookies, no reintentar."""


def find_cookies(explicit: str | os.PathLike | None = None) -> Path:
    """Ubica el JSON de cookies sin asumir una estructura de repo.

    Un path explícito es una afirmación sobre QUÉ cuenta usar: si no existe,
    fallamos en vez de caer en silencio a otro archivo (usar la cuenta
    equivocada en silencio es peor que un error).
    """
    env_var = f"{SERVICE.upper()}_COOKIES"
    for source, value in (("argumento", explicit), (env_var, os.environ.get(env_var))):
        if value:
            p = Path(value).expanduser()
            if not p.is_file():
                raise ServiceAuthError(
                    f"El {source} apunta a {p}, que no existe. No busco en otro "
                    "lado para no usar una cuenta distinta a la que pediste."
                )
            return p

    candidates: list[Path] = []
    cwd = Path.cwd().resolve()
    for d in (cwd, *cwd.parents):          # el proyecto en el que se trabaja
        candidates.append(d / COOKIE_FILENAME)
    candidates.append(Path.home() / ".config" / SERVICE / "cookies.json")
    candidates.append(Path.home() / ".config" / SERVICE / COOKIE_FILENAME)

    for c in candidates:
        if c.is_file():
            return c
    raise ServiceAuthError(
        f"No encontré {COOKIE_FILENAME}. Exportá las cookies de {SERVICE} con la "
        f"sesión iniciada a ~/.config/{SERVICE}/cookies.json, o apuntá "
        f"{env_var} al archivo."
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
                f"{self.cookies_path} no es JSON válido ({e}). Reexportá las cookies."
            ) from e

    # ------------------------------------------------------------------ auth

    def auth_status(self) -> dict[str, Any]:
        """Diagnóstico LOCAL, sin tocar la red.

        Adaptalo al esquema de tu servicio: si usa un JWT, decodificá el payload
        y devolvé `expires_in_seconds`; si usa cookie opaca, al menos verificá
        que las cookies de sesión estén presentes.
        """
        names = {c["name"] for c in self._cookies}
        session_cookies = {"session", "__session", "auth_token"} & names
        return {
            "cookies_file": str(self.cookies_path),
            "cookie_count": len(self._cookies),
            "has_session_cookie": bool(session_cookies),
            "valid": bool(session_cookies),
        }

    # ------------------------------------------------------------- transporte

    def _throttle(self) -> None:
        """Ritmo pausado. No lo saques: es la diferencia entre una cuenta sana
        y una marcada como automatizada."""
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
                    f"{e.code} en {path}. La sesión puede haber vencido; "
                    f"reexportá las cookies de {SERVICE}."
                ) from e
            raise ServiceError(f"{method.upper()} {path} -> {e.code}: {detail}") from e

    def download(self, url: str, dest: str | os.PathLike) -> dict:
        """Descarga espaciada. Nunca en paralelo."""
        p = Path(dest).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        self._throttle()
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=300) as r:
            p.write_bytes(r.read())
        return {"path": str(p), "bytes": p.stat().st_size}
