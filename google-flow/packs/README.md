# Packs

El plugin `google-flow` es genérico: sus tools funcionan con cualquier cuenta y
cualquier applet. Un **pack** es la parte que no puede ser genérica.

## Qué es propio de cada cuenta

| | Por qué no puede venir en el plugin |
|---|---|
| `projectId` | Va en la URL de todo applet, y es de cada cuenta |
| `appletId` | Identifica *tus* herramientas, no las de otro |
| Vocabularios | Los valores de cada dropdown los definió quien creó el applet |
| Recetas | Combinan lo anterior |

Todo lo demás —autenticación, conducción del browser, batch, upscale, medición
de créditos— es igual para todos y vive en el plugin.

## Generar el tuyo

```
flow_scaffold_pack   dest: "./mi-pack",  name: "mi-pack"
```

Descubre el proyecto abriendo Flow, lista tus herramientas, abre cada una para
leer sus controles reales, extrae los valores válidos de `constants.ts` y deja:

```
mi-pack/
├── pack.json        projectId, applets, controles y vocabularios
├── applets.md       la misma info en prosa, para leer
└── recipes/*.json   una receta inicial por herramienta
```

Tarda unos minutos: abre un browser por applet, con pausas. Es una operación de
setup que se hace una vez.

Si ya sabés tu `projectId` (está en la URL:
`labs.google/fx/tools/flow/project/<projectId>/…`), pasalo como `project_id` y
se saltea el descubrimiento.

## Activarlo

```bash
export FLOW_PACK=/ruta/a/mi-pack        # cualquier directorio
export FLOW_PACK_NAME=aerthos           # o uno de packs/ del plugin
```

Con el pack activo, `flow_pack_info` lo describe y las tools de generación
aceptan `recipe_name` además de la receta completa.

## Escribirlo a mano

`pack.json` es un archivo común; el scaffolder es una comodidad, no un
requisito. Lo mínimo que necesita:

```json
{
  "name": "mi-pack",
  "projectId": "00000000-0000-0000-0000-000000000000",
  "applets": {
    "mi-herramienta": {
      "appletId": "11111111-1111-1111-1111-111111111111",
      "displayName": "Mi Herramienta",
      "generateButton": "GENERAR",
      "controls": [
        { "type": "dropdown", "label": "Estilo", "current": "Realista" }
      ],
      "vocabulary": { "ESTILOS": ["Realista", "Pixel art"] }
    }
  }
}
```

Ver `_template/` para un esqueleto completo con comentarios.

## Lo que el scaffolder acierta y lo que no

Los controles y el texto del botón salen de **inspeccionar la UI montada**, no
de parsear el código: el JSX varía demasiado entre applets para deducirlos con
confianza. Aun así conviene revisar lo generado.

Dos cosas que vas a querer mirar:

**Acciones deshabilitadas.** Si `disabledActions` incluye el botón de generar,
ese applet necesita un insumo previo —típicamente una imagen subida— y hoy no
es automatizable, porque falta implementar el upload de referencias.

**Vocabularios vacíos.** Si un applet no declara sus opciones en `constants.ts`
sino inline en el JSX, `vocabulary` queda corto. El campo `current` de cada
dropdown igual trae el valor seleccionado, que sirve como punto de partida.

## Packs incluidos

| Pack | Cuenta | Herramientas |
|---|---|---|
| [`aerthos`](./aerthos) | proyecto de Aerthos | 7 — sprites, mapas, tokens |

Sirve como ejemplo real de un pack generado y después ajustado a mano.
