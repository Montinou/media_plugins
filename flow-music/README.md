# flowmusic

Bridge to **Google Flow Music** (`flowmusic.app`, which under the hood is
Riffusion): catalog, credits, and stem download —**bass included**— through
the API.

## Installation

```
/plugin marketplace add Montinou/media_plugins
/plugin install flow-music@media-plugins
```

## Precondition

Needs a valid session in `www.flowmusic.app.cookies.json`, at the root of the
repo (or `FLOWMUSIC_COOKIES` pointing to the file). The `SessionStart` hook
warns if it expired and can't refresh itself; `/flowmusic:auth` guides the
renewal.

The file is a full session: `chmod 600` and covered by `*.cookies.json`
in `.gitignore`.

## What it includes

**MCP `flowmusic`** (stdio, no pip dependencies):

| Tool | Network | What it does |
|---|---|---|
| `flowmusic_auth_status` | no | session status; always the first stop |
| `flowmusic_account` | yes | user and **real balance** of credits |
| `flowmusic_list_songs` | yes | user's songs |
| `flowmusic_list_stems` | yes | tracks that already have stems |
| `flowmusic_stem_urls` | yes | URLs without downloading |
| `flowmusic_download_stems` | yes | downloads the 4 stems to disk |
| `flowmusic_download_song` | yes | downloads the mix (WAV if it exists) |

**Commands:** `/flowmusic:auth`, `/flowmusic:stems`
**Skill:** `flowmusic` — API, bass restriction, behavior rules, and browser
flows.

## What you need to know

- **The bass.** The UI and `/__api/download/audio/{id}` deny it (403), but the
  clip's `audio_url` points to a public bucket that responds 200 — the same
  URL that "Open Stem" opens in spaces. `flowmusic_download_stems` already
  uses that route.
- **The sidebar credits are not the balance**: they're the free daily quota.
- **The API doesn't separate stems.** You have to run *Split stems* on the
  web.
- **`wav_url` lies on stems**: it comes populated but returns 404. It only
  works on song clips.

## Pacing

The client enforces 2.5 s between requests (`FLOWMUSIC_MIN_INTERVAL`). Do not
lower it: no bursts, no fast retries, no parallel downloads.

## Command-line usage

`lib/flowmusic.py` is also a CLI, with the same capabilities as the MCP tools —
handy for scripts, cron, or a quick check outside an agent:

```bash
python3 flow-music/lib/flowmusic.py status              # session, local, no network
python3 flow-music/lib/flowmusic.py account             # user and credit balance
python3 flow-music/lib/flowmusic.py songs -n 10
python3 flow-music/lib/flowmusic.py stems               # songs that already have stems
python3 flow-music/lib/flowmusic.py urls "Pocket Strut" # what would be downloaded
python3 flow-music/lib/flowmusic.py get "Pocket Strut" -o ~/Music/stems
python3 flow-music/lib/flowmusic.py song <clip_id> -o ~/Music
```

Everything prints JSON. Exit code 2 means the session needs renewing, 1 is any
other failure. The pacing floor applies here too: `--min-interval` defaults to
2.5 s.
