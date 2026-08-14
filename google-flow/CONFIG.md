# Configuration

Everything is resolved through environment variables prefixed `FLOW_`. None
are mandatory except the credentials; the rest have reasonable defaults.

## Credentials

| Variable | Default | What for |
|---|---|---|
| `FLOW_COOKIES` | walks up from the cwd looking for `cookies/labs.google.cookies.json`, then the bare file, and falls back to `FLOW_CONFIG_DIR` | labs.google cookies file |
| `FLOW_CONFIG_DIR` | `~/.config/google-flow` | Where credentials live |
| `FLOW_TOKEN_CACHE` | `$FLOW_CONFIG_DIR/.flow-token.json` | Cache for the bearer derived from the cookie |

A project's `cookies/` folder **wins over `~/.config`**. A stale file in the
config directory shadowing the one you just re-exported is a confusing failure:
the symptom is a 401 that looks like an expired session even after refreshing.

The session cookie lasts months; the bearer, hours. The bearer re-derives
itself, so you only need to re-export cookies once the session fully expires.

## Which project and which tools

| Variable | Default | What for |
|---|---|---|
| `FLOW_PROJECT_ID` | the active pack's | Flow project |
| `FLOW_PACK` | none | Path to a directory with `pack.json` |
| `FLOW_PACK_NAME` | none | Name of a pack inside the plugin's `packs/` |

Without any of the three, tools that open an applet fail with a message
explaining how to get the `projectId`. That's deliberate: the plugin doesn't
ship anyone's project hardcoded.

`FLOW_PACK` wins over `FLOW_PACK_NAME`, and `FLOW_PROJECT_ID` wins over both.

## Outputs

| Variable | Default | What for |
|---|---|---|
| `FLOW_OUT` | `./flow-out` | Generated PNGs and manifests |
| `FLOW_APPLETS` | `./flow-applets` | Downloaded applet source code |

Relative to the directory the server runs from, which is the project you're
working on.

## Development

| Variable | What for |
|---|---|
| `FLOW_LIB` | Point to a different `lib/` checkout without reinstalling the plugin |

## Example

```bash
# per project — preferred: the credentials sit next to the work
mkdir -p cookies
# export labs.google cookies to cookies/labs.google.cookies.json
chmod 600 cookies/labs.google.cookies.json
# and make sure cookies/ is gitignored

# or globally, as a fallback for every project
mkdir -p ~/.config/google-flow
chmod 600 ~/.config/google-flow/labs.google.cookies.json

# per project
export FLOW_PACK=~/packs/my-game
export FLOW_OUT=./assets/generated
```

Verify with `python3 google-flow/doctor.py`.

## The ids don't live in this repo

This repo is public, so it **carries no real `appletId` or `projectId`**.
The ones that appear in the documentation and in `packs/_template/` are
placeholders (`00000000-…`, `11111111-…`).

Yours go in your own pack, outside version control:

```bash
mkdir -p ~/.config/google-flow/packs/my-project
# write pack.json there with your projectId and your appletId
export FLOW_PACK=~/.config/google-flow/packs/my-project
```

To discover your account's ids without copying them by hand:

```bash
python3 -c "import sys; sys.path.insert(0,'google-flow/lib'); import flow_client as f; \
print('\n'.join(f\"{a['appletId']}  {a.get('title','')}\" for a in f.list_applets()))"
```

### A warning that takes time to discover

Several applets open with the generate button **disabled**: they want a source
image. That does not make them unreachable — the requirement is met by
**picking an image from the project gallery**, and the button that does it is
always enabled even when it reads `Upload Source Map`, because it calls
`Flow.media.select`, not a file picker.

Driving that picker is UI work like any other control. The `Flow.upload` path,
for a local file, is the one that would need protocol work — and it isn't
needed. Description fields are optional: generation proceeds without them.

Worth flagging disabled actions in your `pack.json` anyway, so you know which
tools need a gallery pick before they run.

And watch out for the project: an account can have several, and Flow
defaults to one that isn't always the one with your tools. That's why the
pack fixes the `projectId` explicitly.
