# suno

Operate **Suno** with judgment: Studio 2.0 (multitrack DAW, stem export in
WAV), generation outside the Studio, and local verification of downloads.

## Install

```
/plugin marketplace add Montinou/media_plugins
/plugin install suno@media-plugins
```

## The MCP doesn't touch the network, on purpose

Unlike `flowmusic`, here **no tool makes requests to Suno**. Three verified
reasons:

1. **The session can't be renewed.** Auth is Clerk, 1-hour JWT. The cookie
   export includes `__client_uat` but **not `__client`**, which is what
   Clerk uses to issue new tokens. A script dies after an hour, always.
2. **Cloudflare.** Without `cf_clearance`, script requests arrive with a
   bot fingerprint — exactly what triggers challenges.
3. **The ToS forbid automated access.** The account, subscription, and the
   user's catalog are all at stake.

And above all: multitrack export **is one click**. Automating it gains
little.

Operation goes through the browser with the user's session; the MCP
provides local diagnostics and verification.

## What it includes

**MCP `suno`** (stdio, no pip, no network):

| Tool | What it does |
|---|---|
| `suno_auth_status` | handle, plan, expiration; and whether the session would be renewable (almost always not) |
| `suno_inspect_multitrack` | analyzes an exported zip without extracting it: tracks, sizes, alignment, missing stems |
| `suno_verify_stem` | RMS by band to confirm a stem is what it claims to be |

**Commands:** `/suno:auth`, `/suno:stems`
**Skills:** `suno-studio` (the DAW and export), `suno-browser` (safe
browser operation and everything outside the Studio).

## Precondition

`suno.com.cookies.json` at the repo root (or `SUNO_COOKIES`). If the token
expired, **that is not a blocker for working via browser**: it's enough
for the user to open `suno.com` logged in, and it renews itself. The
`SessionStart` hook warns when relevant.

## The stems

Suno Studio separates **only** when a song is loaded, into 7 tracks:
Vocals, Backing Vocals, Drums, Bass, Guitar, Synth (plus the mix).
`Export → Multitrack` gives a zip with one **32-bit float PCM WAV at
48 kHz** per track, all the exact same length and ready for a DAW.

Weight: ~421 MB for a 3-minute track. You need to wait, not retry.

## Hard rules

- **Never** touch a playback control.
- **Never** solve a CAPTCHA or Cloudflare challenge.
- **Never** publish a song without an explicit request (Suno's feed is public).
- Confirm anything that consumes credits or modifies the account.

## Command-line usage

`lib/suno.py` is also a CLI. Like the MCP tools, none of it touches Suno's
network — it only reads local files:

```bash
python3 suno/lib/suno.py status                          # session, from the cookies JSON
python3 suno/lib/suno.py inspect ~/Downloads/project.zip  # multitrack export
python3 suno/lib/suno.py verify "4 Bass.wav"             # RMS per band
```

Everything prints JSON. Exit code 2 means the session needs renewing, 1 is any
other failure.
