---
name: suno-studio
description: Use when working in Suno Studio (suno.com/studio) — the multitrack DAW. Covers loading projects, the Legacy vs 2.0 upgrade prompt, per-track effect prompting, and Export → Multitrack to get WAV stems including bass. Read before driving the Studio in a browser.
---

# Suno Studio

`suno.com/studio` is a **multitrack DAW**, not a generator. It's the best
route there is to get stems: 7 lossless WAV tracks, aligned, in one click.

## Before going in

1. `suno_auth_status` — local, no network. If the token expired, ask the
   user to open `https://suno.com/` in Chrome with the session logged in
   (it renews itself on navigation).
2. Its own tab. Never step on another one the user is working in.
3. **Hard rule: don't touch any playback control.** The Studio starts
   with audio loaded, and an involuntary play blares loudly on the other end.

## Entering a project

Two paths:

- **Saved project** — "Pick up where you left off", or `New empty project`.
- **Any song** — `Edit in Studio` button in the list on the right.

Old projects carry a **Legacy** badge. Opening them brings up a dialog:

| Option | Effect |
|---|---|
| `Open in Studio 1.2 (Legacy)` | opens as-is, **creates nothing** |
| `Open in Studio 2.0` | **creates a copy**, updated; doesn't overwrite the original |

**Ask the user which one they want.** Studio 2.0 is the useful version,
but it leaves a new project in their account: that's a modification of
their library and isn't yours to decide.

## The interface (2.0)

```
┌ SUNO  [project]  undo/redo   ▸ transport   87 BPM  4/4   Export  Library
├ 1  <original song>     S  A   ▓▓▓ waveform ▓▓▓
├ 2  Vocals              S  A   ▓▓▓
├ 3  Backing Vocals      S  A   ▓▓▓
├ 4  Drums               S  A   ▓▓▓
├ 5  Bass                S  A   ▓▓▓
├ 6  Bass                S  A   ▓▓▓
├ 7  Guitar              S  A   ▓▓▓
├ 8  Synth               S  A   ▓▓▓
├ + Add New Track
└ Mstr (master)                  [prompt v5.5]   + Add Track Effects
```

- **Suno separates on its own** when the song loads. There's no separate
  "split stems" request needed like in Flow Music.
- Each track: **S** (solo), **A**, fader, and waveform over the timeline.
- Below, a prompt in **BETA** acts on the selected track and generates
  effects or material in natural language — *"build a gritty delay and
  put it on this track"*, *"generate an 8-bar drum loop and drop it
  here"* — with a model selector (**v5.5**). Consumes credits: confirm
  before using.
- `Add Track Effects` for the track's effect chain.

## Export → Multitrack (the stems)

`Export` at the top right, three options:

| Option | What it does |
|---|---|
| `Full Song` | full mix |
| `Selected Time Range` | only the marked range |
| **`Multitrack`** | **zip with one WAV per track** |

`Multitrack` is the official route. There's nothing to work around.

### What to expect

- **Takes time and weighs a lot.** A ~3 min project came out to **421 MB**.
  The download shows up as `.crdownload` and grows for a couple of
  minutes: **wait patiently**, don't press Export again or reload.
- **32-bit float PCM, 48 kHz, stereo.** Lossless.
- All files are **exactly the same size**: they're aligned from 0.
- Names with a track-order prefix: `0 <song>.wav`, `1 Vocals.wav`,
  `2 Backing Vocals.wav`, `3 Drums.wav`, `4 Bass.wav`, `6 Guitar.wav`,
  `7 Synth.wav`.

There's also a **"Bulk-export presets"** option to leave presets configured.

### After downloading

Verify before declaring victory:

1. `suno_inspect_multitrack` with the zip path — tracks, sizes,
   alignment, and missing stems, without extracting anything.
2. `suno_verify_stem` on the extracted bass: it should show **low-end
   dominance** (in a real measurement: 17.3 dB). Vocals, high-end dominance.

Never "verify" by playing it back.

## Comparison with Flow Music

| | Flow Music | Suno Studio |
|---|---|---|
| Stems | 4 | 7 |
| Format | m4a AAC | WAV float32 48 kHz |
| Bass | blocked via the official route | included |
| Separation | must be requested | automatic on load |
| Editing | none | DAW with effects and per-track generation |

For working with stems, Suno is clearly superior. If the user has both,
recommend Suno unless they already have the material in Flow Music.
