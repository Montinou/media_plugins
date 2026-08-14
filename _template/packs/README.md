# packs/ — what's yours, not the plugin's

A plugin in this marketplace has two layers, and the distinction isn't
cosmetic:

| Layer | What lives there | Works for anyone? |
|---|---|---|
| **core** (`lib/`, `mcp/`, `skills/`, `commands/`) | how to talk to the service: auth, pacing, endpoints, tools | **yes** |
| **pack** (`packs/<project>/`) | your tool ids, presets, prompts, your project's names | **no**, it's yours |

The rule: **if someone else can't use it as-is, it's a pack.**

An `appletId`, a `space_version_id`, a `project_id`, your game's faction
list, your style presets — none of that goes in the core. If it leaks in,
the plugin stops being installable by anyone else, and on top of that your
identifiers end up in a public repo.

## Structure of a pack

```
packs/
└── my-project/
    ├── pack.json          project ids and config
    ├── recipes/           executable presets
    └── notes.md           catalog of your tools, decisions, whatever
```

Minimal `pack.json`:

```json
{
  "name": "my-project",
  "description": "What this pack is for",
  "ids": {
    "appletId": "…",
    "projectId": "…"
  },
  "defaults": {
    "style": "…"
  }
}
```

## How a pack gets chosen

By environment variable or tool argument — never hardcoded:

```bash
export EXAMPLE_PACK=my-project
```

In code, resolve it like this (and fail with a clear message if it doesn't
exist):

```python
def load_pack(name: str | None = None) -> dict:
    name = name or os.environ.get(f"{SERVICE.upper()}_PACK")
    if not name:
        return {}                      # no pack: the core works the same
    p = Path(__file__).resolve().parents[1] / "packs" / name / "pack.json"
    if not p.is_file():
        avail = [d.name for d in p.parents[0].parent.iterdir() if d.is_dir()]
        raise ServiceError(f"Pack {name!r} doesn't exist. Available: {avail}")
    return json.loads(p.read_text())
```

**The core has to work without any pack.** A pack adds shortcuts, not
capabilities: if a tool only works with a pack, that tool is badly designed.

## Publishing packs, or not

A pack in the public repo is readable by anyone. If it has ids for private
projects or prompts you don't want to share, leave it out: packs are also
read from `~/.config/<plugin>/packs/`, which never enters the repo.

No pack ever carries credentials. Ever. That goes in `~/.config/<plugin>/`.
