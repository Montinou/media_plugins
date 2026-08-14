---
description: Check the Suno session and guide renewal if needed
---

# /suno:auth

Checks the Suno session precondition. It's all local: not a single
request to the service.

## Steps

1. Call `suno_auth_status`.

2. Interpret and tell the user, in minutes rather than raw seconds:

   - **`valid: true`** — report handle, plan, and how much time is left. Done.
   - **`valid: false`** — the token expired. Clarify that **this isn't a
     blocker for working via browser**:

     > The Suno session shows expired in the cookies file. If we're going
     > to operate in the browser, just opening `https://suno.com/` in
     > Chrome while logged in is enough: it renews itself. Only re-export
     > `suno.com.cookies.json` if you want local diagnostics.

   - **Authentication error** (file missing or no `__session`) — ask for
     the export:

     > 1. Open `https://suno.com/` in Chrome and confirm you're logged in.
     > 2. Export the domain's cookies to JSON.
     > 3. Save it as `suno.com.cookies.json` at the repo root.

3. Always report two things from the result, because they explain the plugin's design:

   - **`can_refresh`** — almost always `false`: the Clerk `__client`
     cookie is missing, so there's no programmatic renewal available.
   - **`has_cf_clearance`** — usually `false`: without it, any script
     request runs into Cloudflare.

   That's why this plugin **has no HTTP client** and operates via browser.

4. Hygiene after every renewal:

   ```bash
   chmod 600 suno.com.cookies.json
   git check-ignore -v suno.com.cookies.json
   ```

   If it's not ignored, warn loudly before continuing.

## What not to do

- Don't build an HTTP client against Suno, no matter how convenient it seems.
- Don't ask the user to paste the token in chat.
- Don't try to log in yourself or fill out login forms.
