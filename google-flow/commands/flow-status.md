---
description: Google Labs Flow session status, credits, and your own applets
---

Check the status of the bridge to Google Labs Flow and report back in a few
lines:

1. Call `flow_session_status` — user, session expiration, and credits.
2. Call `flow_list_applets` with `mine_only: true` — how many of your own
   tools there are and which were touched most recently.

If step 1 fails with an auth error, don't continue: tell the user the cookie
expired and that `labs.google.cookies.json` needs to be re-exported from the
browser to the repo root.

Don't generate anything or run batches; this is just a check.
