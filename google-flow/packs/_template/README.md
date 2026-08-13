# Esqueleto de pack

Copiar este directorio y completar a mano, o —más rápido— generar todo con:

```
flow_scaffold_pack   dest: "./mi-pack",  name: "mi-pack"
```

Las claves que empiezan con `_` son comentarios: JSON no los tiene, así que se
usan campos que el lector ignora. Se pueden borrar.

## Pasos si lo hacés a mano

1. **`projectId`** — de la URL de Flow:
   `labs.google/fx/tools/flow/project/<projectId>/tool/<appletId>`
2. **`appletId`** — de la misma URL, o de `flow_list_applets`
3. **`generateButton` y `controls`** — de `flow_inspect_controls`, que lee la UI
   montada. No deducirlos del código: el JSX varía demasiado entre applets.
4. **`vocabulary`** — de `flow_get_applet_code`, que devuelve `constants.ts`
5. **Verificar** — `flow_dryrun_recipe` aplica una receta sin generar, costo cero

## Después

```bash
export FLOW_PACK=/ruta/a/mi-pack
```

Y `flow_pack_info` debería describirlo.
