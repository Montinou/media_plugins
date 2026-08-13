#!/usr/bin/env python3
"""Upscale local de assets generados en Flow.

Por qué local y no el 2K nativo de Flow:

  1. `/v1/flow/upsampleImage` exige un token de reCAPTCHA Enterprise que sólo
     produce el frontend, así que devuelve 403 desde cualquier cliente propio.
  2. Consume créditos (el frontend chequea `hasEnoughCredits` antes de ofrecerlo).
  3. Para pixel art un upscaler neuronal es contraproducente: interpola bordes
     que el arte necesita duros. Nearest-neighbor con factor entero es la
     operación correcta — reversible, sin pérdida y sin costo.

Para arte no-pixelado (fondos pintados, ilustración) usar --filter lanczos.

Uso:
    python3 tools/flow/flow_upscale.py entrada.png -f 2
    python3 tools/flow/flow_upscale.py entrada.png --target-width 2560
    python3 tools/flow/flow_upscale.py carpeta/ -f 2 --suffix @2x
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

FILTERS = {
    "nearest": Image.NEAREST,  # pixel art: preserva bordes duros
    "lanczos": Image.LANCZOS,  # arte pintado / fotográfico
    "bicubic": Image.BICUBIC,
}


def upscale(
    src: Path,
    dest: Path,
    factor: int | None = None,
    target_width: int | None = None,
    filt: str = "nearest",
) -> tuple[int, int, int, int]:
    img = Image.open(src)
    w, h = img.size

    if target_width:
        if filt == "nearest" and target_width % w:
            # Un factor fraccionario con nearest duplica columnas de forma
            # despareja y arruina la grilla del pixel art.
            factor = max(1, round(target_width / w))
            print(
                f"  ! {target_width}px no es múltiplo entero de {w}px; "
                f"uso factor {factor}x ({w * factor}px) para no romper la grilla"
            )
            new = (w * factor, h * factor)
        else:
            scale = target_width / w
            new = (target_width, round(h * scale))
    elif factor:
        new = (w * factor, h * factor)
    else:
        raise ValueError("hay que dar --factor o --target-width")

    out = img.resize(new, FILTERS[filt])
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.save(dest, optimize=True)
    return w, h, new[0], new[1]


def main() -> None:
    ap = argparse.ArgumentParser(description="Upscale local, sin costo")
    ap.add_argument("src", help="archivo PNG o carpeta")
    ap.add_argument("-f", "--factor", type=int, help="factor entero (2, 3, 4...)")
    ap.add_argument("--target-width", type=int, help="ancho destino en px")
    ap.add_argument(
        "--filter", choices=list(FILTERS), default="nearest",
        help="nearest para pixel art (default), lanczos para arte pintado",
    )
    ap.add_argument("--suffix", default="@2x", help="sufijo del archivo salida")
    ap.add_argument("-o", "--out", help="carpeta destino")
    args = ap.parse_args()

    src = Path(args.src)
    files = sorted(src.glob("*.png")) if src.is_dir() else [src]
    if not files:
        raise SystemExit(f"sin PNGs en {src}")

    for f in files:
        out_dir = Path(args.out) if args.out else f.parent
        dest = out_dir / f"{f.stem}{args.suffix}.png"
        w, h, nw, nh = upscale(
            f, dest, args.factor, args.target_width, args.filter
        )
        print(f"{f.name}: {w}x{h} -> {nw}x{nh} [{args.filter}] -> {dest}")


if __name__ == "__main__":
    main()
