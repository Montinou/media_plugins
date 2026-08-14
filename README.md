# media_plugins

Claude Code plugin marketplace for producing audio and image with AI tools
that **do not expose a public API**. Each plugin solves the same underlying
problem: use the browser session to reach a service that only has a UI.

## Plugins

| Plugin | Service | What it solves |
|---|---|---|
| [`google-flow`](./google-flow) | [Google Labs Flow](https://labs.google/fx/tools/flow) | generate assets in batch by driving the applets, and upscale |
| [`flow-music`](./flow-music) | [Flow Music](https://www.flowmusic.app) | catalog, credits, and stem download **including the bass** |
| [`suno`](./suno) | [Suno](https://suno.com) | Studio 2.0, multitrack WAV export, and local verification |

## Installation

```
/plugin marketplace add Montinou/media_plugins
/plugin install google-flow@media-plugins
/plugin install flow-music@media-plugins
/plugin install suno@media-plugins
```

Each plugin ships a `doctor.py` that verifies its installation without
spending anything:

```bash
python3 google-flow/doctor.py
python3 flow-music/doctor.py
python3 suno/doctor.py
```

Installing the plugin does not grant access to any account: each one supplies
its own session credentials, which never live in this repo.

## Requirements

The only thing they share is `python3` and session credentials in
`~/.config/<plugin>/`. Everything else depends on how much browser each one
uses:

| Plugin | Needs |
|---|---|
| `google-flow` | `playwright`, `requests`, `pillow`, and Google Chrome — drives the applets |
| `flow-music` | stdlib only. `ffmpeg` optional, for verifying stems |
| `suno` | stdlib only. `ffmpeg` for verifying stems; the browser is handled by the agent |

None of them need the MCP SDK: the servers speak JSON-RPC over stdio using
the stdlib. This is deliberate — Homebrew's Python is under PEP 668, and
installing the SDK would force `--break-system-packages` on the system
interpreter.

## Credentials

Each plugin looks for its cookies in `~/.config/<plugin>/`, and no
credential lives in this repo:

| Plugin | File |
|---|---|
| `google-flow` | `~/.config/google-flow/labs.google.cookies.json` |
| `flow-music` | `~/.config/flowmusic/cookies.json` |
| `suno` | `~/.config/suno/cookies.json` |

```bash
mkdir -p ~/.config/google-flow
# export the service's cookies from the browser to the file above
chmod 600 ~/.config/google-flow/labs.google.cookies.json
```

The plugins also accept the JSON at the root of the project you're working
in, or at an explicit path via environment variable (`FLOW_COOKIES`,
`FLOWMUSIC_COOKIES`, `SUNO_COOKIES`). If that variable points to a file that
doesn't exist, **they fail instead of looking elsewhere**: silently using
the wrong account is worse than an error.

Session cookies are equivalent to being logged into the account. The
`.gitignore` covers the usual patterns, but the real rule is that they never
enter the repo under any name.

## About automating services without an API

These plugins exist because the tool that's needed only has a web interface.
That brings three consequences that are written into every skill and are
not optional:

**The pace is slow on purpose.** None of these services publish usage
limits, and an account flagged as automated is lost along with all the work
that depended on it. The pauses between actions are not lowered.

**Bot detection is not evaded.** When a path rejects an automated browser,
the answer is to connect to a real Chrome via CDP, not to spoof the
fingerprint. Evading detection triggers exactly the block it's trying to
avoid.

**Costs are measured, not assumed.** Before a long batch, run a short pass
that compares the balance before and after. The credits belong to the
account owner.

None of this uses someone else's credentials or bypasses a paywall: it
automates the installer's own account. The endpoints were reconstructed by
observing the frontend's traffic, there is no stable contract, and they can
change without notice — if a plugin suddenly stops working, that's usually
why.

## Core and packs

Each plugin has two layers, and the distinction is what makes it installable
by someone else:

| Layer | What lives there | Works for anyone? |
|---|---|---|
| **core** — `lib/`, `mcp/`, `skills/`, `commands/` | how to talk to the service: auth, pacing, endpoints, tools | **yes** |
| **pack** — `packs/<project>/` | your tool ids, presets, prompts, your project's names | **no**, it's yours |

**The rule: if someone else can't use it as-is, it's a pack.** An
`appletId`, a `projectId`, your game's faction list — none of that goes in
core.

Core has to work **without any pack**: a pack adds shortcuts, not
capabilities. If a tool only works with a pack, that tool is badly designed.

Packs are selected via environment variable (`<SERVICE>_PACK`), never
hardcoded, and are also read from `~/.config/<plugin>/packs/` for the ones
you don't want to publish.

No pack carries credentials. Those go in `~/.config/<plugin>/`, always.

## Building a new plugin

[`_template/`](./_template) is a **functional** skeleton — it runs as-is:

```bash
python3 _template/doctor.py
cp -R _template mi-servicio
```

It brings the base client (auth, pacing, actionable errors), a full MCP
server, a precondition hook, a skill, a command, and a doctor. The
step-by-step recipe is in its README, including the question worth asking
before writing anything: **whether the service deserves an HTTP client or
has to be operated through the browser.**

`_template` is not listed in the catalog, so it doesn't get installed by
accident.

## Structure

```
.claude-plugin/marketplace.json   catalog
_template/                        skeleton for new plugins
<plugin>/
├── .claude-plugin/plugin.json    manifest
├── .mcp.json                     MCP server
├── lib/                          libraries (self-contained)
├── mcp/server.py                 tools
├── hooks/                        session precondition on startup
├── skills/                       usage guides
├── commands/                     slash commands
├── packs/<project>/              project-specific pieces
└── doctor.py                     installation check
```

Each plugin is self-contained: `lib/` travels inside it so it works once
installed, without depending on any other repo.
