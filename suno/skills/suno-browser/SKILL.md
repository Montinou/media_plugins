---
name: suno-browser
description: Use when driving suno.com in a browser — generating songs, browsing the library, downloading, or any Suno task outside the Studio. Covers why Suno must never be scripted over HTTP, Cloudflare and account-safety rules, session handling, and the browser interaction patterns that actually work.
---

# Suno in the browser

**Suno is always operated via browser.** It's not a style preference:
it's the only way that doesn't risk the user's account.

## Why there's no HTTP client

Three concrete reasons, all verified:

1. **The session can't be renewed.** Auth is **Clerk** (`auth.suno.com`),
   an RS256 JWT with a 1-hour lifetime. The browser's cookie export
   includes `__client_uat` (a timestamp) but **not `__client`**, which is
   the cookie Clerk uses to issue new tokens. A script dies after an
   hour, always.
2. **Cloudflare.** There's no `cf_clearance` in the exported cookies.
   Requests from a script arrive without clearance and with a bot
   fingerprint: exactly the pattern that triggers challenges.
3. **The ToS forbid automated access.** Downloading your own music from
   the UI is fine; scripting it puts the user's account, subscription,
   and catalog at stake.

If you're tempted to build a client because "it would be more
convenient": multitrack export is **one click**. Automating it gains
little and risks a lot.

**Never** solve a CAPTCHA or a Cloudflare challenge. If one appears,
stop and tell the user.

## Session

`suno_auth_status` is local and doesn't touch the network. Returns
handle, plan, and expiration.

- An expired token **isn't a blocker** for working via browser: it's
  enough for the user to open `https://suno.com/` with the session
  logged in, and it renews itself.
- Only ask them to re-export `suno.com.cookies.json` if you need local
  diagnostics.
- The file is a full session: `chmod 600`, gitignored, never in chat.

## Behavior rules

1. **Never touch play.** Suno has a persistent player at the bottom and
   autoplay in several views. No playback control, in any view, ever.
2. **Human pace.** One step at a time, with real waits between actions.
   No bursts of clicks or repeated reloads. If something is taking a
   while, wait.
3. **Own tab** (`tabs_create_mcp`). Don't step on the user's tabs, and
   close yours when done unless asked to leave them.
4. **Confirm anything that consumes credits or modifies the account**:
   generating, extending, creating personas, publishing, deleting. And
   anything irreversible: publishing, deleting, changing visibility.
5. **Never publish** a song without an explicit request. Suno has a
   public feed: publishing exposes the user's material.
6. **Don't accept terms or consents** on your own.
7. **Verify downloads** with `suno_inspect_multitrack` /
   `suno_verify_stem` instead of playing them back.

## App map

| Route | What it is |
|---|---|
| `/` → `/discover` | public feed |
| `/create` | main generator |
| `/studio` | multitrack DAW (see the `suno-studio` skill) |
| `/library` | the user's songs |
| `/explore` | discovery |
| `/me` | profile |

Audio CDNs: `cdn1.suno.ai`, `cdn2.suno.ai`, `cdn-o.suno.com`.
The frontend is Next.js with ~99 hash-named chunks; the public landing
page doesn't expose API routes.

## Patterns that work

- **Wait for real.** After navigating or triggering a generation, wait
  with pauses of several seconds and check again. Suno shows
  intermediate states ("heavy traffic", placeholders) that resolve on
  their own.
- **Read before clicking.** `get_page_text` or `read_page` to understand
  the state; `find` to locate controls by description instead of
  guessing coordinates.
- **Verify the effect of each click** with a screenshot before the next
  one. Suno's menus close on their own and a blind click can land on
  something else.
- **Heavy downloads**: show up as `.crdownload` and can take minutes.
  Monitor the file size instead of retrying the action.

## Outside the Studio

Basics of what `/create` offers; going deeper here is pending work, and
it's best to explore live before asserting details:

- Description prompt, or **Custom** mode with lyrics and style separate.
- Model selector, instrumental on/off, saved personas and styles.
- On an existing song: extend, remaster, create a cover, edit lyrics.
- Individual download from the song itself (audio and, depending on
  plan, WAV).

**When the user asks for something in this area, explore the UI live and
confirm what you see before treating any claim in this section as
settled.** Prefer `suno-studio` for anything stem-related.
