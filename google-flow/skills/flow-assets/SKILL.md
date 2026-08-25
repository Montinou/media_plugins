---
name: flow-assets
description: Use when generating assets with Google Labs Flow — sprites, character turnarounds, map layers, dioramas — or when working with recipes, packs, appletId, projectId, credits, or labs.google tools. For building or editing an applet itself, see flow-applets
---

# Generating assets with Google Labs Flow

Google Labs Flow has no public API. Access relies on the user's browser
session, and the tools ("applets") are run by driving the real app, not by
replicating its protocol.

The `google-flow` MCP's `flow_*` tools cover the whole cycle. This document
is for deciding **which one to use and in what order**, and for the three
non-negotiable rules.

## Non-negotiable rules

**1. Dryrun before any new batch.** `flow_dryrun_recipe` applies all the
controls without generating. A recipe with a misspelled label fails on
variant 14 of 28 if it isn't verified first.

**2. Don't speed up or parallelize.** The pauses in `flow_driver.py`
(`PACE_MS`, `PACE_RUN_S`) are set deliberately. Google Labs doesn't publish
usage limits, and an account flagged as automated gets lost along with all
the work that depended on it. Never run two batches in parallel or lower the
pauses.

**3. Don't evade automation detection.** If a route responds with 403
`PUBLIC_ERROR_UNUSUAL_ACTIVITY`, the answer is to use a real Chrome via
`cdp_url`, not to fake `navigator.webdriver` or patch the fingerprint.
Evading detection is exactly what triggers the block you're trying to avoid.

| Rationalization | Reality |
|---|---|
| "It's only 3 variants, I'll skip the dryrun" | The dryrun takes a minute; a failed batch wastes ten. |
| "I'll drop the pause to 5s just for this run" | The risk isn't per-run, it accumulates on the account. |
| "Two batches in parallel go faster" | It doubles the request rate, which is exactly what gets measured. |
| "One stealth patch and the upscale works" | It turns a recoverable 403 into a flagged account. |
| "The user has 234 credits, spending a few is fine" | The credits are theirs. Measure and report, don't decide for them. |

## Building or fixing an applet

That lives in the **flow-applets** skill: which controls a recipe can reach,
how to chain steps, the model selector every applet needs, and the failures
that look like nothing at all. Read it before asking the tool creator for
anything — an applet that works by hand can be impossible to drive, and
retrofitting means editing it mid-run.

## What's generic and what's per-account

The tools work with any account. What's specific to each one —`projectId`,
`appletId`, dropdown vocabularies— lives in a **pack**.

Before anything else, `flow_pack_info`: says whether there's an active pack
and what it has. If there isn't one, `flow_scaffold_pack` generates one by
reading the account. Without a pack or `FLOW_PROJECT_ID`, tools that open an
applet fail on purpose: the plugin doesn't ship anyone's project hardcoded.

## Normal flow

```
flow_session_status        does the cookie still work? how many credits are there?
flow_pack_info             what tools and recipes are available?
flow_dryrun_recipe         verify the recipe, zero cost
flow_batch_generate        with limit 2-3 first, then the full batch
flow_upscale_local         nearest x2 for pixel art
```

With an active pack, the generation tools accept `recipe_name` and there's
no need to build the recipe by hand.

For a tool that isn't in the pack:

```
flow_list_applets          get the appletId
flow_get_applet_code       constants.ts has the valid dropdown values
flow_inspect_controls      the labels and the exact text of the generate button
```

Those last two are the ones that get skipped and the ones that cause
failures: **dropdown values come from `constants.ts`, not from guessing**,
and the labels and the button come from `flow_inspect_controls`, not from
the code. Applets' JSX varies too much to deduce them reliably.

## Costs

Measured by comparing `/v1/credits` before and after; every run reports the
delta.

- **Generating images: 0 credits.** The generation routes don't even
  validate reCAPTCHA.
- **Native 2K/4K upscale: costs**, and requires a real Chrome.

If a `flow_generate` reports a cost other than 0, say so explicitly: it
means Flow changed its policy and the user needs to know before launching a
batch of 28.

## Upscale: local almost always

For pixel art, `flow_upscale_local` with `nearest` and an integer factor is
**better** than native 2K, not a poor substitute. Flow's upscaler is
generative: it interpolates exactly the sharp edges pixel art needs. Nearest
with an integer factor is exact and lossless — a 1376x768 grid comes out
2752x1536, above 2K, for free.

Native 2K only makes sense for **painted art** (backgrounds, dioramas),
where interpolation works in your favor. There it requires `cdp_url` and
spends credits: ask the user for confirmation before calling it.

## Media ids: `mediaId` and `fe_id_<uuid>` are the same id

**Read this before wiring any step that feeds an image into another one.**

A generation returns a bare UUID as `mediaId`. Everything that TAKES an image
as a reference — `referenceImageMediaIds`, an applet's reference field — wants
that same UUID spelled `fe_id_<uuid>`. Same id, different spelling.

```
mediaId      55019664-7e03-43b2-8ad8-9b5d041d80ed
referenceId  fe_id_55019664-7e03-43b2-8ad8-9b5d041d80ed   ← what a reference takes
```

`flow_generate` and `flow_batch_generate` already return `referenceId` spelled
correctly. **Use it and never build the string by hand.**

Why this one is worth a section: the bare UUID does not fail loudly. The applet
reports `Reference image with ID ... not found or not ready`, which contains
none of the words the driver watches for, so the run neither errors nor returns
— it sits until the generation timeout and looks exactly like a slow model.
Two runs were lost to it, and the wrong conclusion drawn from it (that ids die
with their session) sent a whole redesign down the wrong path before someone
who remembered the prefix said so. It is a missing prefix, nothing more.

Uploaded library images use the same spelling, so a style reference picked from
the library and a layer you just generated are interchangeable as references.

## Recipes

A recipe describes how to drive an applet's controls. Full schema, your
pack's applet vocabularies, and the details of `matrix` are in
`references/recipes.md`.

```json
{
  "appletId": "00000000-0000-0000-0000-000000000000",
  "generateButton": "FORJAR GRILLA 8 DIRECCIONES",
  "controls": [
    { "type": "dropdown", "label": "Fondo Chroma", "value": "Magenta puro" }
  ],
  "matrix": {
    "Facción / Linaje": ["Imperio de Aethelria", "Clanes de Crkds"]
  }
}
```

`matrix` is only used by `flow_batch_generate`: it expands the cartesian
product and skips variants whose PNG already exists, so an interrupted batch
resumes by calling it again.

## When something fails

| Symptom | Cause | What to do |
|---|---|---|
| Auth error | expired cookie | Ask the user to re-export `labs.google.cookies.json` |
| `couldn't find the option X` | value not in `constants.ts` | Reread constants with `flow_get_applet_code` |
| `couldn't find a control with label X` | label taken from the code, not the UI | Run `flow_inspect_controls` |
| Automation can only fill the first of several fields | they share a placeholder; `fill()` takes `.first` | `flow_edit_applet` to make the placeholders distinct |
| A run with reference images times out with no error | the bare UUID was passed where a reference goes; it needs the `fe_id_` prefix | Use the `referenceId` that the generation returned (see Media ids) |
| 403 `PUBLIC_ERROR_UNUSUAL_ACTIVITY` | route with cost from an automated browser | Use `cdp_url` with a real Chrome |
| The applet didn't mount | compiles with esbuild.wasm in the browser | Raise `loadTimeoutMs`; usually takes ~30s |
| `don't know which project to work with` | no pack and no `FLOW_PROJECT_ID` | `flow_scaffold_pack`, or set the variable |
| The generate button is disabled | the applet wants a source image | Add a `gallery` control to the recipe. The `Upload …` button calls `Flow.media.select`, not a file picker, and is always enabled |

## References

- the **flow-applets** skill — building and editing applets an automation can drive
- `references/recipes.md` — recipe schema and how `matrix` works
- `references/api-map.md` — endpoints, two-hop auth, what reCAPTCHA protects
- the plugin's `packs/README.md` — what's specific to each account and how to generate a pack

The catalog of concrete tools isn't here: it lives in each pack's
`applets.md`, because it depends on the account.
