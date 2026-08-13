"""Cliente de Google Flow Music (www.flowmusic.app).

Sin dependencias fuera de la stdlib: el Python de Homebrew está bajo PEP 668 y
no queremos obligar a `--break-system-packages`.

Arquitectura del servicio (relevada por ingeniería inversa del bundle):

    front  ──► https://www.flowmusic.app/__api/*   proxy same-origin
           ──► https://wb.flowmusic.app            backend real
    auth   ──► https://sb.flowmusic.app            Supabase
    audio  ──► storage.googleapis.com/producer-app-public/clips/{id}.m4a

Dos cosas que no son obvias y cuestan horas si se ignoran:

1. Hay que pegarle a `/__api`, no a `wb.flowmusic.app` (CORS desde el browser,
   y desde script el proxy es igual de válido y más estable).
2. El stem de `bass` está bloqueado en la UI y en `/__api/download/audio/{id}`
   (403), pero el `audio_url` del clip apunta a un bucket público que responde
   200. No es evasión de un control: es la misma URL que la propia app abre con
   "Open Stem".

Ritmo: nunca ráfagas. Toda request pasa por `_throttle`.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

# Endpoints del servicio. Son defaults, no constantes: Flow Music expone
# backends alternativos (`wb-snake`, `wb-yoshi`, `wb-zelda`) y el día que mueva
# algo no queremos editar código. Nada de esto identifica a un usuario ni a un
# proyecto — los ids concretos van en el repo que los usa, nunca acá.
BASE = os.environ.get("FLOWMUSIC_API_BASE", "https://www.flowmusic.app/__api")
SUPABASE = os.environ.get("FLOWMUSIC_SUPABASE", "https://sb.flowmusic.app")
BUCKET = os.environ.get(
    "FLOWMUSIC_BUCKET",
    "https://storage.googleapis.com/producer-app-public/clips",
)
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)
COOKIE_FILENAME = os.environ.get(
    "FLOWMUSIC_COOKIE_FILENAME", "www.flowmusic.app.cookies.json"
)
STEM_ORDER = {"vocals": 0, "drums": 1, "bass": 2, "other": 3}
ALL_STEMS = frozenset(STEM_ORDER)


class FlowMusicError(RuntimeError):
    """Fallo operativo (HTTP, parseo, etc.)."""


class FlowMusicAuthError(FlowMusicError):
    """La sesión no sirve: falta el archivo, está vencida o no se pudo renovar.

    Siempre trae un mensaje accionable — quien la reciba debe pedirle al usuario
    que reexporte las cookies, no reintentar.
    """


def find_cookies(explicit: str | os.PathLike | None = None) -> Path:
    """Ubica el JSON de cookies.

    Orden: argumento explícito, `FLOWMUSIC_COOKIES`, el proyecto en el que se
    está trabajando (cwd y sus ancestros) y por último la config del usuario
    (`~/.config/flowmusic/`).
    """
    # Un path explícito es una afirmación sobre QUÉ cuenta usar. Si no existe,
    # fallamos: caer en silencio a otro archivo puede operar la cuenta
    # equivocada sin que nadie se entere.
    for source, value in (("argumento", explicit), ("FLOWMUSIC_COOKIES", os.environ.get("FLOWMUSIC_COOKIES"))):
        if value:
            p = Path(value).expanduser()
            if not p.is_file():
                raise FlowMusicAuthError(
                    f"El {source} apunta a {p}, que no existe. No busco en otro "
                    "lado para no usar una cuenta distinta a la que pediste."
                )
            return p

    # Sin path explícito: el proyecto en el que se está trabajando (cwd y sus
    # ancestros, para funcionar desde un subdirectorio) y después la config del
    # usuario. Nada relativo a la ubicación de este archivo: el plugin puede
    # estar instalado en cualquier lado.
    candidates: list[Path] = []
    cwd = Path.cwd().resolve()
    for d in (cwd, *cwd.parents):
        candidates.append(d / COOKIE_FILENAME)
    candidates.append(Path.home() / ".config" / "flowmusic" / "cookies.json")
    candidates.append(Path.home() / ".flowmusic" / "cookies.json")
    candidates.append(Path.home() / ".flowmusic" / COOKIE_FILENAME)

    for c in candidates:
        if c.is_file():
            return c
    raise FlowMusicAuthError(
        f"No encontré {COOKIE_FILENAME}. Exportá las cookies de "
        "www.flowmusic.app (con la sesión iniciada) y dejá el JSON en la raíz "
        "del proyecto, en ~/.config/flowmusic/cookies.json, o apuntá "
        "FLOWMUSIC_COOKIES al archivo."
    )


class FlowMusic:
    def __init__(
        self,
        cookies_path: str | os.PathLike | None = None,
        min_interval: float = 2.5,
    ):
        self.cookies_path = find_cookies(cookies_path)
        self.min_interval = min_interval
        self._last_call = 0.0
        try:
            self._cookies = json.loads(self.cookies_path.read_text())
        except json.JSONDecodeError as e:
            raise FlowMusicAuthError(
                f"{self.cookies_path} no es JSON válido ({e}). Reexportá las cookies."
            ) from e
        self._session = self._load_session()

    # ------------------------------------------------------------------ sesión

    def _load_session(self) -> dict[str, Any]:
        parts = {c["name"]: c["value"] for c in self._cookies}
        chunks = sorted(k for k in parts if k.startswith("sb-sb-auth-token."))
        if not chunks:
            raise FlowMusicAuthError(
                "El archivo no tiene cookies `sb-sb-auth-token.*`. Puede que hayas "
                "exportado sin sesión iniciada, o de otro dominio."
            )
        raw = "".join(parts[k] for k in chunks)
        if raw.startswith("base64-"):
            raw = raw[7:]
        try:
            return json.loads(base64.b64decode(raw + "=" * (-len(raw) % 4)))
        except Exception as e:
            raise FlowMusicAuthError(f"No pude decodificar la sesión: {e}") from e

    @property
    def access_token(self) -> str:
        return self._session["access_token"]

    def _claims(self) -> dict:
        payload = self.access_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))

    def seconds_left(self) -> int:
        return int(self._claims().get("exp", 0) - time.time())

    def auth_status(self) -> dict:
        """Diagnóstico local, sin tocar la red."""
        claims = self._claims()
        left = self.seconds_left()
        return {
            "cookies_file": str(self.cookies_path),
            "email": claims.get("email"),
            "expires_in_seconds": left,
            "valid": left > 0,
            "can_refresh": bool(self._session.get("refresh_token")),
            "needs_user_action": left <= 0
            and not self._session.get("refresh_token"),
        }

    # -------------------------------------------------------------- renovación

    ANON_RE = re.compile(
        r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.eyJ[\w-]{20,}\.[\w-]{10,}"
    )

    def _anon_key(self) -> str:
        """Anon key pública de Supabase (role=anon; no es un secreto).

        Orden: env, cache en disco, scrape del bundle `pages/_app-*.js`.
        """
        if key := os.environ.get("FLOWMUSIC_ANON_KEY"):
            return key
        cache = self.cookies_path.parent / ".flowmusic-anon-key"
        if cache.is_file() and (cached := cache.read_text().strip()):
            return cached

        html = self._raw_get("https://www.flowmusic.app/")
        chunk = re.search(r"/_next/static/chunks/pages/_app-[\w]+\.js", html.decode())
        if not chunk:
            raise FlowMusicAuthError("No encontré el chunk _app para la anon key.")
        bundle = self._raw_get(f"https://www.flowmusic.app{chunk.group(0)}")
        m = self.ANON_RE.search(bundle.decode("utf-8", "replace"))
        if not m:
            raise FlowMusicAuthError("No pude extraer la anon key del bundle.")
        try:
            cache.write_text(m.group(0))
            cache.chmod(0o600)
        except OSError:
            pass  # cachear es un lujo, no un requisito
        return m.group(0)

    def refresh(self) -> None:
        token = self._session.get("refresh_token")
        if not token:
            raise FlowMusicAuthError(
                "La sesión venció y no hay refresh_token. Reexportá las cookies "
                "de www.flowmusic.app."
            )
        body = json.dumps({"refresh_token": token}).encode()
        anon = self._anon_key()
        req = urllib.request.Request(
            f"{SUPABASE}/auth/v1/token?grant_type=refresh_token",
            data=body,
            headers={
                "apikey": anon,
                "Authorization": f"Bearer {anon}",
                "Content-Type": "application/json",
                "User-Agent": UA,
            },
        )
        self._throttle()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                self._session = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise FlowMusicAuthError(
                f"Supabase rechazó la renovación ({e.code}). Reexportá las cookies."
            ) from e

    # ------------------------------------------------------------- transporte

    def _throttle(self) -> None:
        delta = time.monotonic() - self._last_call
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)
        self._last_call = time.monotonic()

    def _raw_get(self, url: str) -> bytes:
        self._throttle()
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.read()

    def call(self, method: str, path: str, body: Any = None, raw: bool = False) -> Any:
        if self.seconds_left() < 60:
            self.refresh()
        cookie = "; ".join(f"{c['name']}={c['value']}" for c in self._cookies)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{BASE}{path}",
            data=data,
            method=method.upper(),
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Cookie": cookie,
                "User-Agent": UA,
                "Accept": "application/json",
                "Referer": "https://www.flowmusic.app/",
                **({"Content-Type": "application/json"} if data else {}),
            },
        )
        self._throttle()
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                payload = r.read()
                return payload if raw else json.loads(payload)
        except urllib.error.HTTPError as e:
            detail = e.read()[:300].decode("utf-8", "replace")
            if e.code in (401, 403) and "/download/audio/" not in path:
                raise FlowMusicAuthError(
                    f"{e.code} en {path}. La sesión puede haber vencido; "
                    "reexportá las cookies de www.flowmusic.app."
                ) from e
            raise FlowMusicError(f"{method.upper()} {path} -> {e.code}: {detail}") from e

    # --------------------------------------------------------------- endpoints

    def me(self) -> dict:
        return self.call("get", "/users/me")

    def credits(self) -> dict:
        """Saldo real. Ojo: el contador del sidebar es el cupo diario gratis,
        no el saldo — mirá `credits_remaining`."""
        data = self.call("get", "/billing/credits").get("data", {})
        return {
            "credits_remaining": data.get("credits_remaining"),
            "tokens_remaining": data.get("tokens_remaining"),
        }

    def clips(self) -> list[dict]:
        r = self.call("get", "/clips/auth-user")
        return r if isinstance(r, list) else r.get("clips", r.get("data", []))

    # ------------------------------------------------------------------ stems

    def songs_with_stems(self) -> dict[str, dict]:
        """{source_clip_id: {"title", "stems": {stem_type: clip}}}"""
        clips = self.clips()
        by_id = {c["id"]: c for c in clips}
        songs: dict[str, dict] = defaultdict(lambda: {"title": None, "stems": {}})
        for c in clips:
            if c.get("op_type") != "audio__split_stems":
                continue
            op = c.get("operation") or {}
            src = op.get("source_clip_id")
            if not src:
                continue
            entry = songs[src]
            for s in op.get("stems") or []:
                if s.get("clip_id") == c["id"]:
                    entry["stems"][s["stem_type"]] = c
            if entry["title"] is None:
                parent = by_id.get(src)
                entry["title"] = (
                    parent.get("title")
                    if parent
                    else (c.get("title") or "").rsplit(" - ", 1)[0]
                )
        return dict(songs)

    def resolve_song(self, target: str) -> tuple[str, dict]:
        """Acepta un source_clip_id o parte del título. Falla si es ambiguo."""
        songs = self.songs_with_stems()
        if target in songs:
            return target, songs[target]
        hits = [
            (src, i)
            for src, i in songs.items()
            if target.lower() in (i["title"] or "").lower()
        ]
        if not hits:
            known = ", ".join(sorted(filter(None, (i["title"] for i in songs.values()))))
            raise FlowMusicError(
                f"No hay stems para {target!r}. Con stems hoy: {known or '(ninguno)'}. "
                "Si el tema existe pero no aparece, corré 'Split stems' en la UI."
            )
        if len(hits) > 1:
            names = "; ".join(f"{i['title']} ({src})" for src, i in hits)
            raise FlowMusicError(f"{target!r} es ambiguo: {names}")
        return hits[0]

    def stem_urls(self, target: str) -> dict:
        src, info = self.resolve_song(target)
        stems = {
            k: v.get("audio_url") or f"{BUCKET}/{v['id']}.m4a"
            for k, v in sorted(
                info["stems"].items(), key=lambda kv: STEM_ORDER.get(kv[0], 9)
            )
        }
        return {
            "source_clip_id": src,
            "title": info["title"],
            "stems": stems,
            "missing": sorted(ALL_STEMS - set(stems)),
        }

    def download_stems(self, target: str, outdir: str | os.PathLike) -> dict:
        info = self.stem_urls(target)
        out = Path(outdir).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        written = []
        for stem_type, url in info["stems"].items():
            dest = out / f"{info['title']}_{stem_type}.m4a"
            dest.write_bytes(self._raw_get(url))
            written.append({"stem": stem_type, "path": str(dest), "bytes": dest.stat().st_size})
        return {
            "title": info["title"],
            "source_clip_id": info["source_clip_id"],
            "outdir": str(out),
            "files": written,
            "missing": info["missing"],
        }

    def download_song(self, clip_id: str, outdir: str | os.PathLike, wav: bool = True) -> dict:
        """Baja la mezcla. `wav=True` intenta el WAV (existe para canciones)."""
        clip = next((c for c in self.clips() if c["id"] == clip_id), None)
        if clip is None:
            raise FlowMusicError(f"No encontré el clip {clip_id}.")
        url = (clip.get("wav_url") if wav else None) or clip.get("audio_url")
        if wav and clip.get("wav_url"):
            try:
                self._throttle()
                req = urllib.request.Request(
                    clip["wav_url"], method="HEAD", headers={"User-Agent": UA}
                )
                urllib.request.urlopen(req, timeout=30)
            except Exception:
                url = clip.get("audio_url")  # los stems exponen wav_url que da 404
        out = Path(outdir).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        dest = out / f"{clip.get('title') or clip_id}{'.wav' if url.endswith('.wav') else '.m4a'}"
        dest.write_bytes(self._raw_get(url))
        return {"title": clip.get("title"), "path": str(dest), "bytes": dest.stat().st_size}
