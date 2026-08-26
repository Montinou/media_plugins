---
name: flow-applets
description: Use when building, editing, or debugging a Google Labs Flow applet that an automation has to drive — control shapes a recipe can reach, chaining steps by media id, model selectors, and the failures that look like nothing at all
---

# Building applets an automation can drive

An applet that works by hand can be impossible to drive by recipe, and the
difference is not obvious from using it. This is what to get right while the
applet is being built — retrofitting means editing it mid-production-run.

Applets are built by asking Flow's tool creator in the browser; there is no API
to create one. `flow_edit_applet` sends a change request to that creator.

## The four rules

**1. Every control a recipe touches is a dropdown or a text field.** The driver
supports those two and nothing else — `apply_controls` raises `unknown control
type` for anything else. Media pickers, toggles, sliders and tabs are all
unreachable.

**2. Steps go in a dropdown, never in tabs.** A multi-step applet naturally
grows tabs. A recipe cannot click one. Put the step in a dropdown and the whole
applet becomes one reachable surface.

**3. Every field a recipe fills needs its own distinctive placeholder.** Text
fields are located by placeholder fragment, taking the first match, so three
fields reading `mediaId...` leave two of them unreachable and no error to
explain why. Name them `mediaId del mapa completo`, `mediaId del terreno
limpio`, and so on.

**4. Give it a model dropdown, and never hardcode `modelDisplayName`.** Each
model has its own daily quota; when it runs out the backend answers `FALLO EN
GENERACIÓN` and nothing else — indistinguishable from a transient error, and
the natural reaction is to retry, which is exactly what you must not do.
Measured on one account: Nano Banana Pro started refusing everything near 115
images in a day, and switching the dropdown to Nano Banana 2 generated four in
a row with no other change.

The names go to the SDK verbatim, emoji and spacing included:

```js
const MODEL_OPTIONS = ['🍌 Nano Banana Pro', '🍌 Nano Banana 2', '🍌 Nano Banana 2 Lite'];
```

## Chaining steps: two shapes, and when each one is right

An applet whose later steps consume its earlier output can chain **outside** or
**inside**.

**Outside — one run per step, joined by media id.** The natural shape, and it
works: pass the previous run's `referenceId` into the next recipe. Each step is
verifiable and retryable on its own. It needs one thing to be right, and it is
the thing everyone gets wrong:

> A generation returns `mediaId` as a bare UUID. Anything taking an image as a
> reference wants that same UUID as `fe_id_<uuid>`. Use the `referenceId` the
> generation already returns; never rebuild the string.

**Inside — one run, a composed strip.** When the applet does every step itself
and returns a single image with the layers stacked. Use this when you want one
generation per map instead of three, or when the intermediate images are of no
interest on their own.

The constraint that decides the shape: **the driver captures exactly one image
per run** — the largest `data:` URI on the page. So an applet that chains
inside must compose its outputs into one image, and must NOT display the
intermediates separately, or the wrong one comes back. Same reason a reference
thumbnail must never be rendered.

Make the composite exact and boring: fixed band height, no gaps, no borders, no
labels. Whatever cuts it apart later will thank you.

## Both doors on every reference field

A reference field should be a text input holding the id **and** a library
picker beside it that writes into that same field. The picker alone is
unreachable by a recipe; the field alone makes a person hunt for a uuid. Ask
for both, in that order, and say that the field is what automation fills.

## Failures that look like nothing

These share a shape: the run does not error, it simply never finishes. The
driver only recognizes text matching `/error|falló|fallo|failed/`, and none of
these produce it.

| What you see | What it is |
|---|---|
| A run with references times out, no error | bare UUID where `fe_id_<uuid>` goes |
| Only the first of several fields gets filled | those fields share a placeholder |
| An edit request seems ignored | the creator's box does not submit on Enter — the send button does |
| `FALLO EN GENERACIÓN` and nothing more | that model's daily quota is gone; switch the model dropdown |
| The applet "didn't mount" | it compiles with esbuild.wasm in the browser; ~30s is normal, raise `loadTimeoutMs` |
| `flow_edit_applet` can't find the creator's input | the creator panel may start collapsed in a fresh session; open it in the browser, or make the change by hand |

## Verify against the applet, never against the answer

The tool creator will report changes it did not make, and the editor's own
preview lags behind the published applet. Measured: the agent replied "changes
made" and listed them correctly while the preview still showed the old
placeholders — only reopening the published applet confirmed it.

So: `flow_inspect_controls` after every edit. It returns the published
applet's real controls. To check that a dropdown gained an option, run
`flow_dryrun_recipe` asking for that option — a missing one fails with the
visible options listed, which is the cheapest inventory there is.

`flow_edit_applet` returns those controls for exactly this reason, and
withholds the agent's prose on purpose. What comes back is evidence, not a
verdict: compare it to what you asked for.

## Asking for a change

Be surgical. The creator rewrites code, and a broad request gets a broad
rewrite. Say what to change, say what to leave alone, and say **why** — the
reason is what lets it choose well in the cases your wording didn't cover.

> The three mediaId fields share one placeholder. Automation locates fields by
> placeholder text and takes the first match, so only Ref 1 is reachable.
> Change ONLY those three placeholders to «…», «…», «…». Don't touch the
> labels, the dropdowns, the logic, the prompts or the model.

After the edit, download the source with `flow_get_applet_code` and keep it in
the repo. It is the only copy that survives someone else editing the applet.
