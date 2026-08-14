# Recipes

A recipe is a JSON object that describes how to drive a Flow applet's
controls. It's what `flow_dryrun_recipe`, `flow_generate`, and
`flow_batch_generate` receive.

## Schema

```json
{
  "name": "my-project-8dir",
  "appletId": "00000000-0000-0000-0000-000000000000",
  "generateButton": "FORJAR GRILLA 8 DIRECCIONES",
  "generateTimeoutSec": 420,
  "loadTimeoutMs": 90000,
  "controls": [
    { "type": "dropdown", "label": "Fondo Chroma", "value": "Magenta puro" },
    { "type": "text", "placeholder": "Capa desgarrada", "value": "capa roja, lanza" }
  ],
  "matrix": {
    "Facción / Linaje": ["Imperio de Aethelria", "Clanes de Crkds"],
    "Acción": ["Reposo / Idle", "En Guardia"]
  }
}
```

| Field | Required | Note |
|---|---|---|
| `appletId` | yes | UUID from `flow_list_applets` |
| `generateButton` | yes | Substring of the button text, as it appears in the UI |
| `controls` | no | Applied in order before generating |
| `matrix` | no | Only `flow_batch_generate`; cartesian product |
| `name` | no | Base of the output filename (in batch it's derived from the combination) |
| `generateTimeoutSec` | no | Default 300. 8-direction grids take a while |
| `loadTimeoutMs` | no | Default 90000. The applet compiles in the browser |

### Controls

**`dropdown`** — `label` is the text preceding the value in the control;
`value` must match an option **exactly**. Valid values come from the
applet's `constants.ts` (`flow_get_applet_code`), not from guessing.

**`text`** — `placeholder` is a substring of the field's placeholder,
enough to identify it.

### matrix

**`gallery`** — for applets that want a source image before enabling their
generate button. `button` is the control that asks for one; despite usually
reading `Upload …`, it calls `Flow.media.select` and opens the project gallery.

```json
{ "type": "gallery", "button": "Upload Source Map", "pick": "turnaround" }
```

`pick` is a substring of the item's title; omit it to take the preselected one,
which is the most recent. `search` narrows the list first, for galleries with
many items.

The picker renders in the **parent frame**, not the applet's iframe, because
`Flow.media.select` belongs to the host. The driver handles that.

Maps dropdown labels to lists of values. `flow_batch_generate` generates the
cartesian product: 7 factions × 4 actions = 28 images. Matrix values
**override** any fixed control with the same label, so a fixed control and a
matrix entry for the same dropdown don't conflict.

Each file is named with the combination's slug
(`imperio-de-aethelria-en-guardia.png`). The batch skips variants whose PNG
already exists: an interrupted batch resumes by calling it again with the
same recipe and the same `out_dir`.

## Why labels are taken from the UI

Controls are located by the `<button>`'s `innerText`, not by CSS classes. A
mistyped label doesn't fail with a network error but with a 30s timeout
looking for an element that doesn't exist.

Watch out for substrings: `"Acción"` is contained in `"Fa`**`cción`**` /
Linaje"`. That's exactly why the driver anchors the label to the start of
the control's text, but if two controls start the same way you need to use
the full label.

## Where the vocabularies come from

The valid values for each dropdown were defined by whoever built the
applet, so they aren't in this plugin: they live in each account's pack.

- `flow_pack_info` returns them for registered tools
- each pack's `applets.md` lists them in prose
- `flow_get_applet_code` fetches any applet's `constants.ts`

If a dropdown isn't in the pack, `flow_inspect_controls` shows its label and
the selected value, which works as a starting point.

## Verify before spending time

```
flow_dryrun_recipe   → applies everything without generating, zero cost
flow_batch_generate with limit: 2  → validate the result before the long batch
```
