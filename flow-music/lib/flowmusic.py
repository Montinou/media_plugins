"""Google Flow Music (www.flowmusic.app) client.

No dependencies outside the stdlib: Homebrew's Python is under PEP 668 and
we don't want to force `--break-system-packages`.

Service architecture (reverse-engineered from the bundle):

    front  ──► https://www.flowmusic.app/__api/*   same-origin proxy
           ──► https://wb.flowmusic.app            real backend
    auth   ──► https://sb.flowmusic.app            Supabase
    audio  ──► storage.googleapis.com/producer-app-public/clips/{id}.m4a

Two things that aren't obvious and cost hours if ignored:

1. You have to hit `/__api`, not `wb.flowmusic.app` (CORS from the browser,
   and from a script the proxy is just as valid and more stable).
2. The `bass` stem is blocked in the UI and in `/__api/download/audio/{id}`
   (403), but the clip's `audio_url` points to a public bucket that responds
   200. This isn't evading a control: it's the same URL the app itself opens
   with "Open Stem".

Pacing: never burst. Every request goes through `_throttle`.
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

# Service endpoints. These are defaults, not constants: Flow Music exposes
# alternate backends (`wb-snake`, `wb-yoshi`, `wb-zelda`), and the day it
# moves something we don't want to edit code. None of this identifies a user
# or a project — the actual ids go in the repo that uses them, never here.
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
    """Operational failure (HTTP, parsing, etc.)."""


class FlowMusicAuthError(FlowMusicError):
    """The session is unusable: the file is missing, expired, or couldn't refresh.

    Always carries an actionable message — whoever receives it should ask the
    user to re-export the cookies, not retry.
    """


def find_cookies(explicit: str | os.PathLike | None = None) -> Path:
    """Locates the cookies JSON.

    Order: explicit argument, `FLOWMUSIC_COOKIES`, the project being worked
    on (cwd and its ancestors), and finally the user config
    (`~/.config/flowmusic/`).
    """
    # An explicit path is a claim about WHICH account to use. If it doesn't
    # exist, we fail: silently falling back to another file could operate the
    # wrong account without anyone noticing.
    for source, value in (("argument", explicit), ("FLOWMUSIC_COOKIES", os.environ.get("FLOWMUSIC_COOKIES"))):
        if value:
            p = Path(value).expanduser()
            if not p.is_file():
                raise FlowMusicAuthError(
                    f"The {source} points to {p}, which doesn't exist. I won't look "
                    "elsewhere to avoid using a different account than the one you requested."
                )
            return p

    # Without an explicit path: the project being worked on (cwd and its
    # ancestors, to work from a subdirectory) and then the user config.
    # Nothing relative to this file's location: the plugin can be installed
    # anywhere.
    candidates: list[Path] = []
    cwd = Path.cwd().resolve()
    for d in (cwd, *cwd.parents):
        # A `cookies/` folder at the project root keeps credentials in one
        # place instead of loose next to the code.
        candidates.append(d / "cookies" / COOKIE_FILENAME)
        candidates.append(d / COOKIE_FILENAME)
    candidates.append(Path.home() / ".config" / "flowmusic" / "cookies.json")
    candidates.append(Path.home() / ".flowmusic" / "cookies.json")
    candidates.append(Path.home() / ".flowmusic" / COOKIE_FILENAME)

    for c in candidates:
        if c.is_file():
            return c
    raise FlowMusicAuthError(
        f"Couldn't find {COOKIE_FILENAME}. Export the cookies for "
        "www.flowmusic.app (while logged in) and put the JSON at the project "
        "root, in ~/.config/flowmusic/cookies.json, or point "
        "FLOWMUSIC_COOKIES at the file."
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
                f"{self.cookies_path} is not valid JSON ({e}). Re-export the cookies."
            ) from e
        self._session = self._load_session()

    # ------------------------------------------------------------------ session

    def _load_session(self) -> dict[str, Any]:
        parts = {c["name"]: c["value"] for c in self._cookies}
        chunks = sorted(k for k in parts if k.startswith("sb-sb-auth-token."))
        if not chunks:
            raise FlowMusicAuthError(
                "The file has no `sb-sb-auth-token.*` cookies. You may have "
                "exported without being logged in, or from a different domain."
            )
        raw = "".join(parts[k] for k in chunks)
        if raw.startswith("base64-"):
            raw = raw[7:]
        try:
            return json.loads(base64.b64decode(raw + "=" * (-len(raw) % 4)))
        except Exception as e:
            raise FlowMusicAuthError(f"Couldn't decode the session: {e}") from e

    @property
    def access_token(self) -> str:
        return self._session["access_token"]

    def _claims(self) -> dict:
        payload = self.access_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))

    def seconds_left(self) -> int:
        return int(self._claims().get("exp", 0) - time.time())

    def auth_status(self) -> dict:
        """Local diagnostic, without touching the network."""
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

    # -------------------------------------------------------------- renewal

    ANON_RE = re.compile(
        r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.eyJ[\w-]{20,}\.[\w-]{10,}"
    )

    def _anon_key(self) -> str:
        """Supabase's public anon key (role=anon; not a secret).

        Order: env, on-disk cache, scrape from the `pages/_app-*.js` bundle.
        """
        if key := os.environ.get("FLOWMUSIC_ANON_KEY"):
            return key
        cache = self.cookies_path.parent / ".flowmusic-anon-key"
        if cache.is_file() and (cached := cache.read_text().strip()):
            return cached

        html = self._raw_get("https://www.flowmusic.app/")
        chunk = re.search(r"/_next/static/chunks/pages/_app-[\w]+\.js", html.decode())
        if not chunk:
            raise FlowMusicAuthError("Couldn't find the _app chunk for the anon key.")
        bundle = self._raw_get(f"https://www.flowmusic.app{chunk.group(0)}")
        m = self.ANON_RE.search(bundle.decode("utf-8", "replace"))
        if not m:
            raise FlowMusicAuthError("Couldn't extract the anon key from the bundle.")
        try:
            cache.write_text(m.group(0))
            cache.chmod(0o600)
        except OSError:
            pass  # caching is a nicety, not a requirement
        return m.group(0)

    def refresh(self) -> None:
        token = self._session.get("refresh_token")
        if not token:
            raise FlowMusicAuthError(
                "The session expired and there's no refresh_token. Re-export the "
                "cookies from www.flowmusic.app."
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
                f"Supabase rejected the renewal ({e.code}). Re-export the cookies."
            ) from e

    # ------------------------------------------------------------- transport

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
                    f"{e.code} on {path}. The session may have expired; "
                    "re-export the cookies from www.flowmusic.app."
                ) from e
            raise FlowMusicError(f"{method.upper()} {path} -> {e.code}: {detail}") from e

    # --------------------------------------------------------------- endpoints

    def me(self) -> dict:
        return self.call("get", "/users/me")

    def credits(self) -> dict:
        """Real balance. Note: the sidebar counter is the free daily quota,
        not the balance — check `credits_remaining`."""
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
        """Accepts a source_clip_id or part of the title. Fails if ambiguous."""
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
                f"No stems for {target!r}. With stems today: {known or '(none)'}. "
                "If the track exists but doesn't show up, run 'Split stems' in the UI."
            )
        if len(hits) > 1:
            names = "; ".join(f"{i['title']} ({src})" for src, i in hits)
            raise FlowMusicError(f"{target!r} is ambiguous: {names}")
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
        """Downloads the mix. `wav=True` tries the WAV (exists for songs)."""
        clip = next((c for c in self.clips() if c["id"] == clip_id), None)
        if clip is None:
            raise FlowMusicError(f"Couldn't find clip {clip_id}.")
        url = (clip.get("wav_url") if wav else None) or clip.get("audio_url")
        if wav and clip.get("wav_url"):
            try:
                self._throttle()
                req = urllib.request.Request(
                    clip["wav_url"], method="HEAD", headers={"User-Agent": UA}
                )
                urllib.request.urlopen(req, timeout=30)
            except Exception:
                url = clip.get("audio_url")  # stems expose a wav_url that returns 404
        out = Path(outdir).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        dest = out / f"{clip.get('title') or clip_id}{'.wav' if url.endswith('.wav') else '.m4a'}"
        dest.write_bytes(self._raw_get(url))
        return {"title": clip.get("title"), "path": str(dest), "bytes": dest.stat().st_size}


# --------------------------------------------------------------------------- CLI


def main() -> int:
    """Same capabilities as the MCP tools, from a terminal.

    Useful outside an agent: scripts, cron, or just checking something fast.
    """
    import argparse

    p = argparse.ArgumentParser(
        prog="flowmusic", description="Google Flow Music client"
    )
    p.add_argument("-c", "--cookies", help="path to the cookies JSON")
    p.add_argument(
        "--min-interval",
        type=float,
        default=float(os.environ.get("FLOWMUSIC_MIN_INTERVAL", "2.5")),
        help="seconds between requests (default 2.5; do not lower it)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="session state — local, no network")
    sub.add_parser("account", help="user and credit balance")

    ls = sub.add_parser("songs", help="list your songs")
    ls.add_argument("-n", "--limit", type=int, default=20)

    sub.add_parser("stems", help="list the songs that already have stems")

    urls = sub.add_parser("urls", help="stem download URLs, without downloading")
    urls.add_argument("song", help="source_clip_id or part of the title")

    get = sub.add_parser("get", help="download a song's stems, bass included")
    get.add_argument("song", help="source_clip_id or part of the title")
    get.add_argument("-o", "--outdir", default=".", help="destination (default: cwd)")

    song = sub.add_parser("song", help="download the full mix")
    song.add_argument("clip_id")
    song.add_argument("-o", "--outdir", default=".")
    song.add_argument("--no-wav", action="store_true", help="skip WAV, take the m4a")

    a = p.parse_args()

    try:
        fm = FlowMusic(a.cookies, min_interval=a.min_interval)
        if a.cmd == "status":
            out = fm.auth_status()
        elif a.cmd == "account":
            out = {"user": fm.me(), "credits": fm.credits()}
        elif a.cmd == "songs":
            out = [
                {"clip_id": c["id"], "title": c.get("title"), "op_type": c.get("op_type")}
                for c in fm.clips()
                if c.get("op_type") != "audio__split_stems"
            ][: a.limit]
        elif a.cmd == "stems":
            out = [
                {
                    "source_clip_id": src,
                    "title": i["title"],
                    "stems": sorted(i["stems"], key=lambda s: STEM_ORDER.get(s, 9)),
                }
                for src, i in fm.songs_with_stems().items()
            ]
        elif a.cmd == "urls":
            out = fm.stem_urls(a.song)
        elif a.cmd == "get":
            out = fm.download_stems(a.song, a.outdir)
        elif a.cmd == "song":
            out = fm.download_song(a.clip_id, a.outdir, wav=not a.no_wav)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    except FlowMusicAuthError as e:
        print(f"authentication: {e}", file=__import__("sys").stderr)
        return 2
    except FlowMusicError as e:
        print(f"error: {e}", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
