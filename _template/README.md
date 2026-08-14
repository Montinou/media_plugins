# _template — build a new plugin

**Functional** skeleton of a plugin for this marketplace. It's not
pseudocode: it runs as-is. Try it before touching anything:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{}}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python3 _template/mcp/server.py
```

`_template` starts with an underscore and **is not listed in the
marketplace**, so it never gets installed by accident.

## The two layers

Before writing a line, place each thing where it belongs:

| Layer | What goes there | Works for anyone? |
|---|---|---|
| **core** — `lib/`, `mcp/`, `skills/`, `commands/` | auth, pacing, endpoints, tools | **yes** |
| **pack** — `packs/<project>/` | your tool ids, presets, prompts | **no**, it's yours |

**If someone else can't use it as-is, it's a pack.** See
[`packs/README.md`](./packs/README.md).

The core has to work without any pack. A pack adds shortcuts, not
capabilities.

## Recipe

```bash
cp -R _template my-service
cd my-service
```

1. **`lib/service.py`** — change `SERVICE`, `BASE`, `COOKIE_FILENAME`. Adapt
   `auth_status()` to the real schema (if there's a JWT, decode it and return
   `expires_in_seconds`). Leave `_throttle` as is.
2. **`mcp/server.py`** — change `SERVER_NAME`, replace the example tools.
   The JSON-RPC layer stays untouched.
3. **`.claude-plugin/plugin.json`** and **`.mcp.json`** — name, description,
   commands.
4. **`skills/<service>/SKILL.md`** — when to use the plugin, auth
   precondition, behavior rules, API map, browser flows.
5. **`commands/auth.md`** — the credential-renewal flow.
6. **`hooks/preflight.py`** — local session check on startup.
7. **`doctor.py`** — installation check.
8. Add the entry in `../.claude-plugin/marketplace.json`.

Verify with `python3 my-service/doctor.py`.

## Non-negotiable rules

These live in the core because they're the difference between a healthy
account and a banned one:

- **Slow, paced requests.** `_throttle` on every request. No bursts, no fast
  retries, no parallel downloads.
- **Credentials outside the repo.** `~/.config/<plugin>/`, `600`
  permissions, and in `.gitignore`. Never in a pack, never in the chat.
- **An explicit path that doesn't exist is an error**, not an invitation to
  look elsewhere: silently using the wrong account is worse than failing.
- **Auth errors are never retried.** The user is asked to re-export.
- **No evading bot detection**, no CAPTCHAs, no 403. If a door is closed on
  purpose, it stays closed.
- **Confirm before spending credits** or any irreversible action.
- **Never play audio** to "verify": measure with `ffprobe`/`ffmpeg`.

## Deciding MCP or browser

Not every service deserves an HTTP client. Before writing one, answer:

1. **Can the session be renewed without the browser?** If the cookie export
   doesn't bring anything to refresh with, a client dies within the hour.
   (Happens to `suno`.)
2. **Is there anti-bot protection?** Without the browser's clearance, script
   requests trigger challenges.
3. **Does the ToS allow automated access?**
4. **How much does it really save?** If the action is a single click,
   automating it gains little and risks the account.

With two "no"s, the plugin goes through the browser and the MCP is limited
to local diagnostics and verifying what was downloaded — exactly what
`suno` does. With four "yes"s, an HTTP client, like `flow-music`.
