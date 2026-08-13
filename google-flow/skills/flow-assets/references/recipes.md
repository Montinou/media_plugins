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

## Vocabularios de los applets de Aerthos

### AERTHOS Sprite Forge · `00000000-0000-0000-0000-000000000000`

Botón: `FORJAR GRILLA 8 DIRECCIONES`

| Label | Valores |
|---|---|
| `Facción / Linaje` | Imperio de Aethelria · Clanes de Crkds · Reino de Eldoria · Enanos de Grimstone · Imperio Syl'theri · Orcos de Espina Negra · Tejedores de Ecos |
| `Acción` | Reposo / Idle · En Guardia · Atacando con arma · Caminando |
| `Fondo Chroma` | Magenta puro · Verde puro |

Campo de texto: placeholder `Capa desgarrada, espada curva…` para detalles
físicos del personaje.

Salida: grilla 4×2 con las 8 direcciones (0° front, 45°, 90°, 135°, 180°, 225°,
270°, 315°) sobre chroma plano, 1376×768.

### Map Asset Layer Forge · `00000000-0000-0000-0000-000000000000`

| Label | Valores |
|---|---|
| `Aspect Ratio` | 16:9 · 1:1 · 4:3 · 3:2 · 9:16 · Igual al mapa |
| `Fondo Chroma` | Magenta puro · Verde puro |
| `Tipo de elementos` | Automático · Naturaleza · Arquitectura / Props · Gameplay · Ruinas · Mixto |
| `Margen de Colisión` | Preciso · Normal · Amplio |

Campos de texto: `Indicaciones: mercado, vegetación…` y, en modo colisión,
`Ej: el río no es transitable…`.

Tiene dos modos de salida (capa de assets / mapa de colisión) y **acepta una
imagen de referencia**. Subir referencias todavía no está implementado en el
driver, así que el modo que parte de un mapa existente no es automatizable aún.

### Aerthos Map Compiler · `00000000-0000-0000-0000-000000000000`

Produce las capas técnicas de un mapa: occlusion mask, height map, surface
material, gameplay semantic. **Arranca de una imagen subida**, así que depende
del upload de referencias que falta implementar.

## Verificar antes de gastar tiempo

```
flow_dryrun_recipe   → aplica todo sin generar, costo cero
flow_batch_generate con limit: 2  → validar el resultado antes de la tanda larga
```
