# Pack skeleton

Copy this directory and fill it in by hand, or — faster — generate
everything with:

```
flow_scaffold_pack   dest: "./my-pack",  name: "my-pack"
```

Keys starting with `_` are comments: JSON has none, so fields the reader
ignores are used instead. They can be deleted.

## Steps if you do it by hand

1. **`projectId`** — from the Flow URL:
   `labs.google/fx/tools/flow/project/<projectId>/tool/<appletId>`
2. **`appletId`** — from the same URL, or from `flow_list_applets`
3. **`generateButton` and `controls`** — from `flow_inspect_controls`, which
   reads the mounted UI. Don't deduce them from the code: the JSX varies
   too much between applets.
4. **`vocabulary`** — from `flow_get_applet_code`, which returns
   `constants.ts`
5. **Verify** — `flow_dryrun_recipe` applies a recipe without generating,
   zero cost

## Afterward

```bash
export FLOW_PACK=/path/to/my-pack
```

And `flow_pack_info` should describe it.
