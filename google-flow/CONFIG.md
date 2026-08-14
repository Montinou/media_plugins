# Configuración

Todo se resuelve por variables de entorno con prefijo `FLOW_`. Ninguna es
obligatoria salvo las credenciales; el resto tiene defaults razonables.

## Credenciales

| Variable | Default | Para qué |
|---|---|---|
| `FLOW_COOKIES` | busca `labs.google.cookies.json` en `FLOW_CONFIG_DIR` y subiendo desde el cwd | Archivo de cookies de labs.google |
| `FLOW_CONFIG_DIR` | `~/.config/google-flow` | Dónde viven las credenciales |
| `FLOW_TOKEN_CACHE` | `$FLOW_CONFIG_DIR/.flow-token.json` | Cache del bearer derivado de la cookie |

La cookie de sesión dura meses; el bearer, horas. El bearer se re-deriva solo,
así que sólo hay que reexportar cookies cuando la sesión caduca del todo.

## Qué proyecto y qué herramientas

| Variable | Default | Para qué |
|---|---|---|
| `FLOW_PROJECT_ID` | el del pack activo | Proyecto de Flow |
| `FLOW_PACK` | ninguno | Ruta a un directorio con `pack.json` |
| `FLOW_PACK_NAME` | ninguno | Nombre de un pack dentro de `packs/` del plugin |

Sin ninguna de las tres, las tools que abren un applet fallan con un mensaje que
explica cómo obtener el `projectId`. Es deliberado: el plugin no trae el
proyecto de nadie hardcodeado.

`FLOW_PACK` gana sobre `FLOW_PACK_NAME`, y `FLOW_PROJECT_ID` gana sobre ambos.

## Salidas

| Variable | Default | Para qué |
|---|---|---|
| `FLOW_OUT` | `./flow-out` | PNGs generados y manifests |
| `FLOW_APPLETS` | `./flow-applets` | Código fuente de applets descargado |

Relativas al directorio desde donde corre el server, que es el del proyecto en
el que estés trabajando.

## Desarrollo

| Variable | Para qué |
|---|---|
| `FLOW_LIB` | Apuntar a otro checkout de `lib/` sin reinstalar el plugin |

## Ejemplo

```bash
# una vez
mkdir -p ~/.config/google-flow
# exportar cookies de labs.google a ~/.config/google-flow/labs.google.cookies.json
chmod 600 ~/.config/google-flow/labs.google.cookies.json

# por proyecto
export FLOW_PACK=~/packs/mi-juego
export FLOW_OUT=./assets/generados
```

Verificar con `python3 google-flow/doctor.py`.

## Los ids no viven en este repo

Este repo es público, así que **no lleva ningún `appletId` ni `projectId` real**.
Los que aparecen en la documentación y en `packs/_template/` son placeholders
(`00000000-…`, `11111111-…`).

Los tuyos van en un pack propio, fuera del control de versiones:

```bash
mkdir -p ~/.config/google-flow/packs/mi-proyecto
# escribí ahí pack.json con tu projectId y tus appletId
export FLOW_PACK=~/.config/google-flow/packs/mi-proyecto
```

Para descubrir los ids de tu cuenta, sin copiarlos a mano:

```bash
python3 -c "import sys; sys.path.insert(0,'google-flow/lib'); import flow_client as f; \
print('\n'.join(f\"{a['appletId']}  {a.get('title','')}\" for a in f.list_applets()))"
```

### Una advertencia que cuesta tiempo descubrir

Varios applets tienen el botón de generar **deshabilitado** hasta que se sube
una imagen de referencia, y el upload todavía no está implementado. Esos no son
automatizables hoy: conviene marcarlos en tu `pack.json` para no perder tiempo.

Y ojo con el proyecto: una cuenta puede tener varios, y Flow entra por defecto
al que no siempre es el que tiene tus herramientas. Por eso el pack fija el
`projectId` explícitamente.
