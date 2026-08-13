"""Suno — utilidades locales.

**Este módulo no hace requests a Suno, y es a propósito.** Suno está detrás de
Cloudflare, sus ToS prohíben el acceso automatizado, y el export de cookies del
navegador no trae `__client` (la cookie con la que Clerk emite tokens nuevos),
así que un cliente HTTP moriría a la hora igual. La operación real va por
navegador con la sesión del usuario; acá solo hay diagnóstico local y
verificación de lo que ya se descargó.

Todo lo de abajo lee archivos del disco. Nada toca la red.
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

# Default overrideable: nada acá identifica a un usuario ni a un proyecto.
COOKIE_FILENAME = os.environ.get("SUNO_COOKIE_FILENAME", "suno.com.cookies.json")

# Stems que Suno Studio produce al cargar una canción. Es más granular que
# Flow Music (que hace 4): acá aparecen coros, guitarra y sintes por separado.
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
    """Sesión ausente o vencida. Siempre requiere acción del usuario:
    en Suno no hay renovación programática posible."""


def find_cookies(explicit: str | os.PathLike | None = None) -> Path:
    # Un path explícito es una afirmación sobre QUÉ cuenta usar. Si no existe,
    # fallamos en vez de caer en silencio a otro archivo.
    for source, value in (("argumento", explicit), ("SUNO_COOKIES", os.environ.get("SUNO_COOKIES"))):
        if value:
            p = Path(value).expanduser()
            if not p.is_file():
                raise SunoAuthError(
                    f"El {source} apunta a {p}, que no existe. No busco en otro "
                    "lado para no usar una cuenta distinta a la que pediste."
                )
            return p

    # Sin path explícito: el proyecto actual (cwd y ancestros) y después la
    # config del usuario. Nada relativo a este archivo: el plugin puede estar
    # instalado en cualquier lado.
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
        f"No encontré {COOKIE_FILENAME}. Exportá las cookies de suno.com con la "
        "sesión iniciada y dejá el JSON en la raíz del proyecto, en "
        "~/.config/suno/cookies.json, o apuntá SUNO_COOKIES al archivo."
    )


def _b64url(seg: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))


def auth_status(cookies_path: str | os.PathLike | None = None) -> dict[str, Any]:
    """Diagnóstico local de la sesión de Suno. No toca la red."""
    path = find_cookies(cookies_path)
    try:
        items = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise SunoAuthError(f"{path} no es JSON válido ({e}).") from e

    names = {c["name"] for c in items}
    sessions = [c for c in items if c["name"] == "__session"]
    if not sessions:
        raise SunoAuthError(
            "El archivo no tiene cookie `__session`. Puede que hayas exportado "
            "sin sesión iniciada."
        )
    # Puede haber una por `suno.com` y otra por `.suno.com`; sirve cualquiera.
    token = max((c["value"] for c in sessions), key=len)

    try:
        claims = _b64url(token.split(".")[1])
    except Exception as e:
        raise SunoAuthError(f"No pude decodificar el JWT de sesión: {e}") from e

    left = int(claims.get("exp", 0) - time.time())
    return {
        "cookies_file": str(path),
        "issuer": claims.get("iss"),
        "handle": claims.get("suno/handle"),
        "email": claims.get("suno.com/claims/email") or claims.get("https://suno.ai/claims/email"),
        "plan": claims.get("plan"),
        "expires_in_seconds": left,
        "valid": left > 0,
        # Clerk necesita `__client` para emitir tokens nuevos; los exports del
        # navegador normalmente solo traen `__client_uat`, que es un timestamp.
        "can_refresh": "__client" in names,
        "has_cf_clearance": "cf_clearance" in names,
        "automation_advice": (
            "Operar por navegador con la sesión del usuario. No armar cliente "
            "HTTP: sin __client no hay renovación, sin cf_clearance las requests "
            "de script disparan challenges de Cloudflare, y los ToS prohíben el "
            "acceso automatizado."
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
        return {"error": "ffprobe no está instalado"}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def inspect_multitrack(zip_path: str | os.PathLike) -> dict:
    """Analiza un zip de `Export → Multitrack` de Suno Studio, sin extraerlo.

    Verifica lo que importa: que estén los stems esperados y que todos midan lo
    mismo (Suno los exporta alineados desde 0, así que un tamaño distinto es
    señal de que algo se cortó).
    """
    p = Path(zip_path).expanduser()
    if not p.is_file():
        raise SunoError(f"No existe {p}.")
    with zipfile.ZipFile(p) as z:
        entries = [
            {"name": i.filename, "bytes": i.file_size}
            for i in z.infolist()
            if not i.is_dir()
        ]
    if not entries:
        raise SunoError(f"{p} está vacío.")

    sizes = {e["bytes"] for e in entries}
    # Los nombres vienen como "4 Bass.wav": prefijo de orden de pista.
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
            "Todos los tracks pesan igual: exportados alineados desde 0, listos "
            "para importar a un DAW."
            if len(sizes) == 1
            else "OJO: hay tamaños distintos. Revisá si algún track quedó cortado."
        ),
    }


def band_energy(path: str | os.PathLike, split_hz: int = 250) -> dict:
    """RMS por debajo y por encima de `split_hz`, para verificar que un stem
    contenga lo que su nombre dice. Requiere ffmpeg."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise SunoError(f"No existe {p}.")

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
            raise SunoError("ffmpeg no está instalado.") from None
        except Exception:  # noqa: BLE001
            return None
        return None

    low, high = rms(f"lowpass=f={split_hz}"), rms(f"highpass=f={split_hz}")
    verdict = None
    if low is not None and high is not None:
        d = low - high
        verdict = (
            f"dominancia grave de {d:.1f} dB" if d > 0
            else f"dominancia aguda de {-d:.1f} dB"
        )
    return {
        "file": p.name,
        "split_hz": split_hz,
        "rms_below_db": low,
        "rms_above_db": high,
        "verdict": verdict,
    }
