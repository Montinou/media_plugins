---
description: Verify the Flow Music session and guide cookie renewal if needed
---

# /flowmusic:auth

Checks the Flow Music authentication precondition and, if it isn't met,
guides the user through renewing it. Doesn't generate anything or spend
credits.

## Steps

1. Call `flowmusic_auth_status`. It's local: doesn't touch the network.

2. Interpret the result:

   - **`valid: true`** — report who the session belongs to and how much time
     is left (in minutes, not raw seconds). Stop there.
   - **`valid: false` with `can_refresh: true`** — say the token expired but
     it renews itself, and confirm by calling `flowmusic_account`. If that
     works, it's resolved.
   - **`valid: false` with `can_refresh: false`, or an authentication error**
     — move on to step 3.

3. Ask for the renewal with concrete instructions:

   > I need you to re-export the Flow Music cookies:
   > 1. Open `https://www.flowmusic.app/` in Chrome and confirm you're logged in.
   > 2. Export the domain's cookies to JSON (an extension like *Cookie-Editor* →
   >    Export → JSON).
   > 3. Save the file as `www.flowmusic.app.cookies.json` at the repo root.
   >
   > Let me know when it's done and I'll continue.

4. Once the user confirms, call `flowmusic_auth_status` again and then
   `flowmusic_account` to verify end to end.

5. Hygiene, once after each renewal:

   ```bash
   chmod 600 www.flowmusic.app.cookies.json
   git check-ignore -v www.flowmusic.app.cookies.json
   ```

   If `git check-ignore` doesn't report it as ignored, **raise a strong
   warning**: a full session is about to enter the repo.

## What not to do

- Don't retry the tools while the session is expired.
- Don't ask the user to paste the token or the file's contents into the chat.
- Don't try to log in yourself or fill out login forms.
