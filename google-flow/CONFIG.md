# Configuration

Everything is resolved through environment variables prefixed `FLOW_`. None
are mandatory except the credentials; the rest have reasonable defaults.

## Credentials

| Variable | Default | What for |
|---|---|---|
| `FLOW_COOKIES` | looks for `labs.google.cookies.json` in `FLOW_CONFIG_DIR` and upward from the cwd | labs.google cookies file |
| `FLOW_CONFIG_DIR` | `~/.config/google-flow` | Where credentials live |
| `FLOW_TOKEN_CACHE` | `$FLOW_CONFIG_DIR/.flow-token.json` | Cache for the bearer derived from the cookie |

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
# once
mkdir -p ~/.config/google-flow
# export labs.google cookies to ~/.config/google-flow/labs.google.cookies.json
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

Several applets have the generate button **disabled** until a reference
image is uploaded, and the upload isn't implemented yet. Those aren't
automatable today: it's worth flagging them in your `pack.json` so you don't
waste time.

And watch out for the project: an account can have several, and Flow
defaults to one that isn't always the one with your tools. That's why the
pack fixes the `projectId` explicitly.
