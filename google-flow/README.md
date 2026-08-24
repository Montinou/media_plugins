# google-flow

Claude Code plugin for producing assets with [Google Labs
Flow](https://labs.google/fx/tools/flow): an MCP server with the tools and a
skill with the usage guides.

Flow has no public API. The plugin reaches it through the browser session and
runs the tools ("applets") by driving the real app, not by replicating its
protocol.

## Installation

```
/plugin marketplace add Montinou/media_plugins
/plugin install google-flow@media-plugins
```

Then, the credentials:

```bash
mkdir -p ~/.config/google-flow
# export the labs.google cookies from the browser to:
#   ~/.config/google-flow/labs.google.cookies.json
chmod 600 ~/.config/google-flow/labs.google.cookies.json
```

And verify:

```bash
python3 google-flow/doctor.py
```

The doctor checks dependencies, Chrome, credentials, and the MCP handshake,
and says what to do about anything missing.

## Requirements

- `python3` with `playwright`, `requests`, and `pillow`
- Google Chrome installed (the driver uses `channel="chrome"`)
- labs.google session cookies

Doesn't need the MCP SDK: the server speaks JSON-RPC over stdio with the
stdlib. That's on purpose — Homebrew's Python is under PEP 668 and installing
the SDK would force `--break-system-packages` on the system interpreter.

## Tools

| Tool | Cost | What it does |
|---|---|---|
| `flow_session_status` | — | User, expiration, and credits |
| `flow_list_applets` | — | Tool catalog |
| `flow_get_applet_code` | — | Source code and `constants.ts` for an applet |
| `flow_inspect_controls` | — | Real UI controls |
| `flow_dryrun_recipe` | — | Applies a recipe without generating |
| `flow_edit_applet` | — | Asks an applet's tool creator for a change |
| `flow_generate` | 0 credits | One image |
| `flow_batch_generate` | 0 credits | Cartesian product of a matrix |
| `flow_upscale_local` | — | Local upscale, nearest or lanczos |
| `flow_upscale_native` | **costs** | Flow's 2K/4K; requires real Chrome |

That generating costs 0 credits is measured, not assumed: every run compares
`/v1/credits` before and after and reports the delta. If that changes, it
shows up in the run.

## Commands

- `/flow-status` — session, credits, and own tools
- `/flow-sprites <description>` — 8-direction grids with the Sprite Forge

## Command-line usage

The `lib/` libraries also work as a CLI:

```bash
python3 lib/flow_client.py list
python3 lib/flow_driver.py dryrun "$FLOW_PACK/recipes/my-recipe.json"
python3 lib/flow_driver.py batch "$FLOW_PACK/recipes/my-recipe.json" --limit 2
python3 lib/flow_upscale.py flow-out/ -f 2
```

Run them from this directory. The recipes live in your pack, not here — see
[`packs/`](./packs) — so `dryrun` first: it resolves the applet and prints what
it would do without generating or spending anything.

Outputs go to cwd (`flow-out/`, `flow-applets/`) unless `FLOW_OUT`, `FLOW_OUT`
or `FLOW_APPLETS` are set.

## Configuration

| Variable | What for |
|---|---|
| `FLOW_COOKIES` | Path to the cookies file |
| `FLOW_CONFIG_DIR` | Config directory (default `~/.config/google-flow`) |
| `FLOW_PROJECT_ID` | Flow project to use |
| `FLOW_OUT` | Output folder for the MCP tools |
| `FLOW_APPLETS` | Where to save downloaded applet code |
| `FLOW_LIB` | Point to a different `lib/` checkout (development) |

## What it doesn't do

- **Upload reference images.** Without that, the Map Compiler and the Layer
  Forge's collision mode can't be automated: both start from an existing map.
- **Create applets.** The `flowCreationAgent/sessions` endpoint is mapped but
  not implemented.

## Pace

The driver moves slowly on purpose, and in batch mode it reuses a single tab.
Google Labs doesn't publish usage limits, and an account flagged as automated
gets lost along with all the work that depended on it. The constants live in
`lib/flow_driver.py`; do not lower them.

When a route rejects an automated browser, the way out is connecting to a
real Chrome over CDP (`cdp_url`), not faking the fingerprint.

## Technical details

`skills/flow-assets/references/api-map.md` has the endpoint map, the
two-hop authentication mechanism, and what reCAPTCHA protects and what it
doesn't.
