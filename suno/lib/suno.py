"""Suno — local utilities.

**This module makes no requests to Suno, and it's on purpose.** Suno sits
behind Cloudflare, its ToS forbid automated access, and the browser's cookie
export doesn't include `__client` (the cookie Clerk uses to issue new
tokens), so an HTTP client would die after an hour anyway. The actual
operation goes through the browser with the user's session; here there's
only local diagnostics and verification of what's already been downloaded.

Everything below reads files from disk. Nothing touches the network.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any

# Overrideable default: nothing here identifies a user or a project.
COOKIE_FILENAME = os.environ.get("SUNO_COOKIE_FILENAME", "suno.com.cookies.json")

# Stems that Suno Studio produces when a song is loaded. More granular than
# Flow Music (which does 4): backing vocals, guitar, and synth appear separately here.
KNOWN_STEMS = (
    "Vocals",
    "Backing Vocals",
    "Drums",
    "Bass",
    "Guitar",
    "Synth",
)


class SunoError(RuntimeError):
    pass


class SunoAuthError(SunoError):
    """Session missing or expired. Always requires user action:
    Suno has no programmatic renewal available."""


def find_cookies(explicit: str | os.PathLike | None = None) -> Path:
    # An explicit path is a statement about WHICH account to use. If it
    # doesn't exist, fail instead of silently falling back to another file.
    for source, value in (("argument", explicit), ("SUNO_COOKIES", os.environ.get("SUNO_COOKIES"))):
        if value:
            p = Path(value).expanduser()
            if not p.is_file():
                raise SunoAuthError(
                    f"The {source} points to {p}, which doesn't exist. I won't "
                    "look elsewhere to avoid using a different account than the one you asked for."
                )
            return p

    # No explicit path: the current project (cwd and ancestors), then the
    # user config. Nothing relative to this file: the plugin can be
    # installed anywhere.
    candidates: list[Path] = []
    cwd = Path.cwd().resolve()
    for d in (cwd, *cwd.parents):
        candidates.append(d / COOKIE_FILENAME)
    candidates.append(Path.home() / ".config" / "suno" / "cookies.json")
    candidates.append(Path.home() / ".suno" / "cookies.json")
    candidates.append(Path.home() / ".suno" / COOKIE_FILENAME)

    for c in candidates:
        if c.is_file():
            return c
    raise SunoAuthError(
        f"Couldn't find {COOKIE_FILENAME}. Export suno.com cookies with the "
        "session logged in and place the JSON at the project root, at "
        "~/.config/suno/cookies.json, or point SUNO_COOKIES to the file."
    )


def _b64url(seg: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))


def auth_status(cookies_path: str | os.PathLike | None = None) -> dict[str, Any]:
    """Local diagnostics of the Suno session. Doesn't touch the network."""
    path = find_cookies(cookies_path)
    try:
        items = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise SunoAuthError(f"{path} isn't valid JSON ({e}).") from e

    names = {c["name"] for c in items}
    sessions = [c for c in items if c["name"] == "__session"]
    if not sessions:
        raise SunoAuthError(
            "The file has no `__session` cookie. You may have exported "
            "without being logged in."
        )
    # There can be one for `suno.com` and another for `.suno.com`; either works.
    token = max((c["value"] for c in sessions), key=len)

    try:
        claims = _b64url(token.split(".")[1])
    except Exception as e:
        raise SunoAuthError(f"Couldn't decode the session JWT: {e}") from e

    left = int(claims.get("exp", 0) - time.time())
    return {
        "cookies_file": str(path),
        "issuer": claims.get("iss"),
        "handle": claims.get("suno/handle"),
        "email": claims.get("suno.com/claims/email") or claims.get("https://suno.ai/claims/email"),
        "plan": claims.get("plan"),
        "expires_in_seconds": left,
        "valid": left > 0,
        # Clerk needs `__client` to issue new tokens; browser exports
        # usually only carry `__client_uat`, which is a timestamp.
        "can_refresh": "__client" in names,
        "has_cf_clearance": "cf_clearance" in names,
        "automation_advice": (
            "Operate via browser with the user's session. Don't build an HTTP "
            "client: without __client there's no renewal, without cf_clearance "
            "script requests trigger Cloudflare challenges, and the ToS forbid "
            "automated access."
        ),
    }


def _ffprobe(path: Path) -> dict:
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=codec_name,sample_rate,channels,duration",
                "-of", "json", str(path),
            ],
            capture_output=True, text=True, timeout=60, check=True,
        )
        return (json.loads(out.stdout).get("streams") or [{}])[0]
    except FileNotFoundError:
        return {"error": "ffprobe isn't installed"}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def inspect_multitrack(zip_path: str | os.PathLike) -> dict:
    """Analyzes a `Export → Multitrack` zip from Suno Studio, without extracting it.

    Verifies what matters: that the expected stems are present and that they
    all measure the same (Suno exports them aligned from 0, so a different
    size is a sign something got cut off).
    """
    p = Path(zip_path).expanduser()
    if not p.is_file():
        raise SunoError(f"{p} doesn't exist.")
    with zipfile.ZipFile(p) as z:
        entries = [
            {"name": i.filename, "bytes": i.file_size}
            for i in z.infolist()
            if not i.is_dir()
        ]
    if not entries:
        raise SunoError(f"{p} is empty.")

    sizes = {e["bytes"] for e in entries}
    # Names come as "4 Bass.wav": track-order prefix.
    def stem_of(name: str) -> str:
        base = Path(name).stem
        return base.split(" ", 1)[1] if " " in base and base.split(" ", 1)[0].isdigit() else base

    found = [stem_of(e["name"]) for e in entries]
    return {
        "zip": str(p),
        "zip_bytes": p.stat().st_size,
        "track_count": len(entries),
        "tracks": entries,
        "stems_found": found,
        "stems_missing": [s for s in KNOWN_STEMS if s not in found],
        "aligned": len(sizes) == 1,
        "alignment_note": (
            "All tracks are the same size: exported aligned from 0, ready "
            "to import into a DAW."
            if len(sizes) == 1
            else "WATCH OUT: sizes differ. Check whether a track got cut off."
        ),
    }


def band_energy(path: str | os.PathLike, split_hz: int = 250) -> dict:
    """RMS below and above `split_hz`, to verify that a stem contains what
    its name says. Requires ffmpeg."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise SunoError(f"{p} doesn't exist.")

    def rms(filt: str) -> float | None:
        try:
            out = subprocess.run(
                ["ffmpeg", "-hide_banner", "-i", str(p), "-af",
                 f"{filt},astats=measure_perchannel=none", "-f", "null", "-"],
                capture_output=True, text=True, timeout=300,
            )
            for line in out.stderr.splitlines():
                if "RMS level" in line:
                    return float(line.split(":")[-1].strip())
        except FileNotFoundError:
            raise SunoError("ffmpeg isn't installed.") from None
        except Exception:  # noqa: BLE001
            return None
        return None

    low, high = rms(f"lowpass=f={split_hz}"), rms(f"highpass=f={split_hz}")
    verdict = None
    if low is not None and high is not None:
        d = low - high
        verdict = (
            f"low-end dominance of {d:.1f} dB" if d > 0
            else f"high-end dominance of {-d:.1f} dB"
        )
    return {
        "file": p.name,
        "split_hz": split_hz,
        "rms_below_db": low,
        "rms_above_db": high,
        "verdict": verdict,
    }
