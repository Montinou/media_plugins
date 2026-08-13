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

## Ids del pack `aerthos`

Documentados en [`packs/aerthos/pack.json`](./packs/aerthos/pack.json) y, en
prosa, en [`packs/aerthos/applets.md`](./packs/aerthos/applets.md).

**Proyecto:** `11111111-1111-1111-1111-111111111111`

| Herramienta | appletId | Botón |
|---|---|---|
| AERTHOS Sprite Forge | `00000000-0000-0000-0000-000000000000` | `FORJAR GRILLA 8 DIRECCIONES` |
| Aerthos: Forja de Tokens | `00000000-0000-0000-0000-000000000000` | `FORJAR SPRITESHEET` |
| Aerthos: Forja de Personajes | `00000000-0000-0000-0000-000000000000` | `Generar Turnaround` |
| Aerthos: Cartógrafo de Reinos | `00000000-0000-0000-0000-000000000000` | `Generar Mapa` |
| AERTHOS — Map Asset Layer Forge | `00000000-0000-0000-0000-000000000000` | `GENERAR CAPA DE ASSETS` ⚠ |
| Remix of Map Asset Layer Forge | `00000000-0000-0000-0000-000000000000` | `GENERAR CAPA DE ASSETS` ⚠ |
| Aerthos Map Compiler | `00000000-0000-0000-0000-000000000000` | `Generate Final Outputs` ⚠ |

⚠ El botón arranca **deshabilitado**: esos applets necesitan una imagen subida
antes de poder generar, y el upload de referencias todavía no está
implementado. Hoy no son automatizables.

Hay otro proyecto en la misma cuenta, `00000000-0000-0000-0000-000000000000`,
que es al que entra Flow por defecto. Las herramientas de Aerthos están en el
primero, así que el pack lo fija explícitamente.
