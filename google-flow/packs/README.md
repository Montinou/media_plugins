# Packs

The `google-flow` plugin is generic: its tools work with any account and any
applet. A **pack** is the part that can't be generic.

## What's specific to each account

| | Why it can't ship in the plugin |
|---|---|
| `projectId` | Goes in every applet's URL, and belongs to each account |
| `appletId` | Identifies *your* tools, not someone else's |
| Vocabularies | Each dropdown's values were defined by whoever built the applet |
| Recipes | Combine the above |

Everything else — authentication, driving the browser, batch, upscale,
credit measurement — is the same for everyone and lives in the plugin.

## Generating your own

```
flow_scaffold_pack   dest: "./my-pack",  name: "my-pack"
```

Discovers the project by opening Flow, lists your tools, opens each one to
read its real controls, extracts the valid values from `constants.ts`, and
leaves you with:

```
my-pack/
├── pack.json        projectId, applets, controls, and vocabularies
├── applets.md       the same info in prose, for reading
└── recipes/*.json   one starter recipe per tool
```

Takes a few minutes: it opens a browser per applet, with pauses. It's a
setup operation you do once.

If you already know your `projectId` (it's in the URL:
`labs.google/fx/tools/flow/project/<projectId>/…`), pass it as `project_id`
and discovery is skipped.

## Activating it

```bash
export FLOW_PACK=/path/to/my-pack        # any directory
export FLOW_PACK_NAME=_template          # or one of the plugin's packs/
```

With the pack active, `flow_pack_info` describes it and the generation
tools accept `recipe_name` in addition to a full recipe.

## Writing it by hand

`pack.json` is a plain file; the scaffolder is a convenience, not a
requirement. The minimum it needs:

```json
{
  "name": "my-pack",
  "projectId": "00000000-0000-0000-0000-000000000000",
  "applets": {
    "my-tool": {
      "appletId": "11111111-1111-1111-1111-111111111111",
      "displayName": "My Tool",
      "generateButton": "GENERAR",
      "controls": [
        { "type": "dropdown", "label": "Estilo", "current": "Realista" }
      ],
      "vocabulary": { "ESTILOS": ["Realista", "Pixel art"] }
    }
  }
}
```

See `_template/` for a full skeleton with comments.

## What the scaffolder gets right, and what it doesn't

The controls and the button text come from **inspecting the mounted UI**,
not from parsing the code: the JSX varies too much between applets to
deduce them reliably. Still, it's worth reviewing what it generates.

Two things you'll want to check:

**Disabled actions.** If `disabledActions` includes the generate button, that
applet wants a source image first. It's still reachable: the button that
provides one is always enabled and calls `Flow.media.select`, which opens the
project gallery — even when it's labelled `Upload …`. Driving that picker is UI
work, not protocol work.

**Empty vocabularies.** If an applet doesn't declare its options in
`constants.ts` but inline in the JSX, `vocabulary` comes up short. Each
dropdown's `current` field still carries the selected value, which works as
a starting point.

## Included packs

Only [`_template`](./_template), with placeholders.

**This repo is public and deliberately includes no real packs.** A pack
carries the `appletId` and `projectId` of a specific account: publishing
them reveals what private tools that person has. Yours goes in
`~/.config/google-flow/packs/<name>` and activates with `FLOW_PACK`, which
accepts any path.

It's the same reason no public reference plugin — `vercel`, `supabase` —
ships its author's account ids.
