---
description: Verify the service session and guide credential renewal
---

# /example:auth

Checks the auth precondition and, if it's not met, guides the user through
renewing it. Generates nothing and spends no credits.

## Steps

1. Call `example_auth_status`. It's local: it doesn't touch the network.

2. Interpret the result and tell the user in human units (minutes, not
   seconds):

   - **valid** — report who it belongs to and how much time is left. Stop
     there.
   - **expired but renewable** — say so and confirm it with a tool that hits
     the network. If it works, it's resolved.
   - **expired and not renewable, or the file is missing** — go to step 3.

3. Ask for renewal with concrete instructions:

   > I need you to re-export the `<service>` cookies:
   > 1. Open `<url>` in Chrome and confirm you're logged in.
   > 2. Export the domain's cookies to JSON (an extension like
   >    *Cookie-Editor*).
   > 3. Save it to `~/.config/<service>/cookies.json`.
   >
   > Let me know when it's done and I'll continue.

4. Once confirmed, verify end-to-end again.

5. Hygiene, once after every renewal:

   ```bash
   chmod 600 ~/.config/<service>/cookies.json
   ```

   If the file ended up inside a repo, verify it's ignored:

   ```bash
   git check-ignore -v <path>
   ```

   If it isn't, **raise a strong flag**: a full session is about to enter
   version control.

## What not to do

- Do not retry the tools while the session is expired.
- Do not ask the user to paste the token or the file's contents into the chat.
- Do not try to log in yourself or fill out login forms.
