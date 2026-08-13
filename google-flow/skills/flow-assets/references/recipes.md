# Recetas

Una receta es un objeto JSON que describe cómo manejar los controles de un
applet de Flow. Es lo que reciben `flow_dryrun_recipe`, `flow_generate` y
`flow_batch_generate`.

## Esquema

```json
{
  "name": "aerthos-facciones-8dir",
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

| Campo | Obligatorio | Nota |
|---|---|---|
| `appletId` | sí | UUID de `flow_list_applets` |
| `generateButton` | sí | Subcadena del texto del botón, tal como aparece en la UI |
| `controls` | no | Se aplican en orden antes de generar |
| `matrix` | no | Sólo `flow_batch_generate`; producto cartesiano |
| `name` | no | Base del nombre de archivo (en batch lo deriva de la combinación) |
| `generateTimeoutSec` | no | Default 300. Las grillas de 8 direcciones tardan |
| `loadTimeoutMs` | no | Default 90000. El applet compila en el browser |

### Controles

**`dropdown`** — `label` es el texto que precede al valor en el control;
`value` debe coincidir **exacto** con una opción. Los valores válidos salen del
`constants.ts` del applet (`flow_get_applet_code`), no de suponer.

**`text`** — `placeholder` es una subcadena del placeholder del campo, que
alcanza para identificarlo.

### matrix

Mapea labels de dropdown a listas de valores. `flow_batch_generate` genera el
producto cartesiano: 7 facciones × 4 acciones = 28 imágenes. Los valores de la
matriz **pisan** cualquier control fijo del mismo label, así que un control fijo
y una entrada de matriz para el mismo dropdown no entran en conflicto.

Cada archivo se nombra con el slug de la combinación
(`imperio-de-aethelria-en-guardia.png`). El batch saltea las variantes cuyo PNG
ya existe: una tanda interrumpida se retoma volviéndola a llamar con la misma
receta y el mismo `out_dir`.

## Por qué los labels se sacan de la UI

Los controles se localizan por el `innerText` de los `<button>`, no por clases
CSS. Un label mal copiado no falla con un error de red sino con un timeout de
30s buscando un elemento que no existe.

Ojo con las subcadenas: `"Acción"` está contenido en `"Fa`**`cción`**` /
Linaje"`. El driver ancla el label al inicio del texto del control justamente
por eso, pero si dos controles empiezan igual hay que usar el label completo.

## De dónde salen los vocabularios

Los valores válidos de cada dropdown los definió quien creó el applet, así que
no están en este plugin: viven en el pack de cada cuenta.

- `flow_pack_info` los devuelve para las herramientas registradas
- `applets.md` de cada pack los lista en prosa
- `flow_get_applet_code` trae el `constants.ts` de cualquier applet

Si un dropdown no aparece en el pack, `flow_inspect_controls` muestra su label
y el valor seleccionado, que sirve de punto de partida.

## Verificar antes de gastar tiempo

```
flow_dryrun_recipe   → aplica todo sin generar, costo cero
flow_batch_generate con limit: 2  → validar el resultado antes de la tanda larga
```
