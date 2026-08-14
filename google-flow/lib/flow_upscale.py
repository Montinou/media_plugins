#!/usr/bin/env python3
"""Local upscale for assets generated in Flow.

Why local instead of Flow's native 2K:

  1. `/v1/flow/upsampleImage` requires a reCAPTCHA Enterprise token that only
     the frontend can produce, so it returns 403 from any standalone client.
  2. It spends credits (the frontend checks `hasEnoughCredits` before offering it).
  3. For pixel art a neural upscaler is counterproductive: it interpolates
     edges the art needs sharp. Nearest-neighbor with an integer factor is
     the correct operation — reversible, lossless, and free.

For non-pixel art (painted backgrounds, illustration) use --filter lanczos.

Usage:
    python3 tools/flow/flow_upscale.py input.png -f 2
    python3 tools/flow/flow_upscale.py input.png --target-width 2560
    python3 tools/flow/flow_upscale.py folder/ -f 2 --suffix @2x
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

FILTERS = {
    "nearest": Image.NEAREST,  # pixel art: preserves sharp edges
    "lanczos": Image.LANCZOS,  # painted / photographic art
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
            # A fractional factor with nearest duplicates columns unevenly
            # and wrecks the pixel art grid.
            factor = max(1, round(target_width / w))
            print(
                f"  ! {target_width}px isn't an integer multiple of {w}px; "
                f"using factor {factor}x ({w * factor}px) to keep the grid intact"
            )
            new = (w * factor, h * factor)
        else:
            scale = target_width / w
            new = (target_width, round(h * scale))
    elif factor:
        new = (w * factor, h * factor)
    else:
        raise ValueError("must pass --factor or --target-width")

    out = img.resize(new, FILTERS[filt])
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.save(dest, optimize=True)
    return w, h, new[0], new[1]


def main() -> None:
    ap = argparse.ArgumentParser(description="Local upscale, no cost")
    ap.add_argument("src", help="PNG file or folder")
    ap.add_argument("-f", "--factor", type=int, help="integer factor (2, 3, 4...)")
    ap.add_argument("--target-width", type=int, help="destination width in px")
    ap.add_argument(
        "--filter", choices=list(FILTERS), default="nearest",
        help="nearest for pixel art (default), lanczos for painted art",
    )
    ap.add_argument("--suffix", default="@2x", help="output file suffix")
    ap.add_argument("-o", "--out", help="destination folder")
    args = ap.parse_args()

    src = Path(args.src)
    files = sorted(src.glob("*.png")) if src.is_dir() else [src]
    if not files:
        raise SystemExit(f"no PNGs in {src}")

    for f in files:
        out_dir = Path(args.out) if args.out else f.parent
        dest = out_dir / f"{f.stem}{args.suffix}.png"
        w, h, nw, nh = upscale(
            f, dest, args.factor, args.target_width, args.filter
        )
        print(f"{f.name}: {w}x{h} -> {nw}x{nh} [{args.filter}] -> {dest}")


if __name__ == "__main__":
    main()
