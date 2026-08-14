---
name: flowmusic
description: Use when working with Google Flow Music (flowmusic.app) — downloading stems or songs, checking credits, generating music, or driving its Producer UI in the browser. Covers the API map, the bass-stem restriction and how to get it legitimately, session/auth preconditions, and the pacing rules this service requires.
---

# Google Flow Music

Flow Music is Google's layer on top of **Riffusion**. This plugin covers two
complementary modes of work:

- **MCP (`flowmusic_*`)** — read catalog, credits, and **download stems and
  songs**.
- **Browser** — everything the API doesn't do: generate music with the
  Producer and run **Split stems**.

## Precondition: authentication

**Before the first operation of each session, call `flowmusic_auth_status`.**
It's local, free, and doesn't touch the network.

| Result | What to do |
|---|---|
| `valid: true` | continue |
| `valid: false`, `can_refresh: true` | continue; it renews itself on the next call |
| `valid: false`, `can_refresh: false` | **stop and ask the user to re-export the cookies** |
| tool fails with `AUTHENTICATION:` | same: stop and ask for renewal |

When renewal is needed, ask for it plainly — no beating around the bush, and
don't retry in the meantime:

> The Flow Music session expired. Re-export the cookies for
> `www.flowmusic.app` while logged in and put the JSON at the repo root as
> `www.flowmusic.app.cookies.json`.

**Never** retry a tool that failed on authentication, or try other tools "to
see if they work". A repeated 401/403 is exactly what gets a service to flag
an account.

The cookies file is a full session: `chmod 600`, covered by
`*.cookies.json` in `.gitignore`, and never pasted into a chat, an issue, or
a log.

## Behavior rules

These aren't decoration: they're the rules that keep the plugin safe to use.

1. **Slow, paced requests, always.** The client enforces 2.5 s between
   requests (`FLOWMUSIC_MIN_INTERVAL`). Don't lower it. No bursts, no fast
   retries, no parallelizing downloads.
2. **Never play audio.** Not in the browser, not locally. If you need to
   know what's in a file, measure it (`ffprobe`, band-split `astats`), don't
   listen to it. The user might be on a call or recording.
3. **Don't evade a 403.** `/__api/download/audio/{bassClipId}` returns 403 on
   purpose. The public `audio_url` **is not an evasion** — it's the URL that
   the app itself opens with "Open Stem". If that also starts returning 403
   someday, that's it: don't look for another door.
4. **Confirm before spending.** Generating music consumes credits. Show the
   prompt and the balance (`flowmusic_account`) and wait for the go-ahead.
5. **Verify what you deliver.** After downloading stems, confirm each file is
   what it claims to be (see *Verification* below). Don't trust the file
   name.
6. **Never delete anything of the user's.** Not old downloads, not clips, not
   projects.

## Credit balance

`flowmusic_account` returns `credits_remaining` and `tokens_remaining`.
**The web sidebar counter is NOT the balance** — it's the free daily quota
(30/day, type `daily-free`). Confusing the two leads to telling the user they
have 29 credits when they actually have ten thousand.

## Stems

Flow Music splits into **4 stems**: `vocals`, `drums`, `bass`, `other`, in
m4a (AAC 48 kHz). No WAV for stems.

### Flow

1. `flowmusic_list_stems` — which tracks already have stems.
2. If the track isn't there: **open the web and run "Split stems"** on the
   clip. The API doesn't trigger it; this is browser work.
3. `flowmusic_stem_urls` to show what's about to be downloaded (cheap, no
   side effects).
4. `flowmusic_download_stems` to download them.

### The bass

Three paths deny it and one delivers it:

| Route | bass |
|---|---|
| UI's "Download tracks" zip | absent |
| `···` menu → "Download stem" | option doesn't appear |
| `GET /__api/stems/clip/{id}` | not included |
| `GET /__api/download/audio/{clipId}` | **403** |
| **clip's `audio_url` → public bucket** | **200** ✅ |

The bundle has a `new Set(["bass"])` that marks those clips as a special
case. It affects the UI and the download endpoint, not the asset. Each stem
is an independent clip, and its `audio_url` points to
`storage.googleapis.com/producer-app-public/clips/{clip_id}.m4a`.

**Important corollary:** if someone reports "it won't let me download the
bass", it's not their connection or the server being down. It's this, and
the fix is `flowmusic_download_stems`, which already uses the correct route.

### Formats: the `wav_url` trap

`audio_url` (m4a) exists for all clips. `wav_url` **only works on song
clips** (`audio__create_song`, `audio__render_edit`); on stems the field
comes populated but returns **404**. You have to check it, not trust that
it's present. `flowmusic_download_song` already does that check.

### Verification

A mislabeled stem is detected by measuring energy per band:

```bash
for f in *.m4a; do
  lo=$(ffmpeg -hide_banner -i "$f" -af "lowpass=f=250,astats=measure_perchannel=none" -f null - 2>&1 | grep "RMS level" | head -1 | awk '{print $NF}')
  hi=$(ffmpeg -hide_banner -i "$f" -af "highpass=f=250,astats=measure_perchannel=none" -f null - 2>&1 | grep "RMS level" | head -1 | awk '{print $NF}')
  printf "%-28s <250Hz %9s  >250Hz %9s\n" "$f" "$lo" "$hi"
done
```

In a healthy set: **bass** with low end dominating ~14 dB, **drums** ~10 dB
(kick), **vocals** and **other** with highs dominating.

## Browser

What the API doesn't do. Rules: dedicated tab, one step at a time, and
**never** touch a playback button.

### Generate a song

1. `https://www.flowmusic.app/` → **"Ask Producer…"** field.
2. Write the prompt and send. The Producer rewrites it into a `Sound` block
   and generates **two takes**.
3. Takes ~30–40 s. Wait with long pauses; don't reload.
4. The URL changes to `/session/{uuid}` — that's the session id.

For the stems to come out clean, ask for explicit separation in the prompt
("clear separation between bass, drums, guitar and keys").

### Split stems

Clip's `···` menu → **Split stems**. Takes ~30 s. When done, the 4 channels
appear with M/S. Then you can go back to the MCP.

### Spaces (applets)

Spaces are React applets that run on `jitterbug.riffusion.com` inside a
sandboxed iframe. Two things learned the hard way:

- **Synthetic keyboard input doesn't reach them** from the parent frame. Use
  the accessibility tree, or open the applet standalone.
- **Standalone gets stuck on "Loading…"**: its SDK talks via `postMessage`
  with the host, and outside flowmusic.app there's no one to answer. To
  operate them, they have to be embedded.

## API map

Base: **`https://www.flowmusic.app/__api`** (same-origin proxy). Hitting
`wb.flowmusic.app` directly gets CORS-blocked from the browser. Auth:
`Authorization: Bearer` with the `access_token` from the `sb-sb-auth-token.*`
cookie (Supabase, chunked, 1 h lifetime, with `refresh_token` inside).

| Method | Path | Notes |
|---|---|---|
| GET | `/users/me` | identity |
| GET | `/billing/credits` | real balance |
| GET | `/clips/auth-user` | user's clips; stems are clips with `op_type: audio__split_stems` |
| GET | `/clips/user/{id}`, `/clips/favorites` | catalog |
| PATCH | `/clips/{id}` | rename, etc. |
| GET | `/stems/clip/{id}` | stems in base64 — **no bass** |
| GET | `/download/audio/{clipId}` | audio; **403 on bass** |
| POST | `/batch-download-clip` | batch download |
| POST | `/conversation` | send a message to the Producer |
| POST | `/conversation/create` | new session |
| GET | `/conversations`, `/conversations/{id}` | history |
| GET | `/operations/{id}` | operation debug |

Internal operations: `audio__create_song`, `audio__split_stems`,
`audio__render_edit`, `audio__apply_effect`, `audio__convert_format`,
`image__create_image`, `video__create_video_clip`, `lyrics__create`,
`code__create_space`.

There's a backend override via the `backend_origin` cookie, validated
against `*.flowmusic.app` (environments `wb-snake`, `wb-yoshi`, `wb-zelda`).

The full client is in `lib/flowmusic.py`; for anything not covered by a
tool, `FlowMusic.call(method, path, body)` reaches any endpoint in the table
while respecting the throttle.
