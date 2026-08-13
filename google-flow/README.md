# google-flow

Plugin de Claude Code para producir assets con [Google Labs
Flow](https://labs.google/fx/tools/flow): un MCP server con las tools y una
skill con las guías de uso.

Flow no tiene API pública. El plugin llega a él por la sesión del navegador y
ejecuta las herramientas ("applets") conduciendo la app real, no replicando su
protocolo.

## Instalación

```
/plugin marketplace add Montinou/media_plugins
/plugin install google-flow@media-plugins
```

Después, las credenciales:

```bash
mkdir -p ~/.config/google-flow
# exportar las cookies de labs.google desde el navegador a:
#   ~/.config/google-flow/labs.google.cookies.json
chmod 600 ~/.config/google-flow/labs.google.cookies.json
```

Y verificar:

```bash
python3 google-flow/doctor.py
```

El doctor revisa dependencias, Chrome, credenciales y el handshake del MCP, y
dice qué hacer con cada cosa que falte.

## Requisitos

- `python3` con `playwright`, `requests` y `pillow`
- Google Chrome instalado (el driver usa `channel="chrome"`)
- Cookies de sesión de labs.google

No necesita el SDK de MCP: el server habla JSON-RPC sobre stdio con la stdlib.
Es a propósito — el Python de Homebrew está bajo PEP 668 e instalar el SDK
obligaría a `--break-system-packages` sobre el intérprete del sistema.

## Tools

| Tool | Costo | Qué hace |
|---|---|---|
| `flow_session_status` | — | Usuario, vencimiento y créditos |
| `flow_list_applets` | — | Catálogo de herramientas |
| `flow_get_applet_code` | — | Código fuente y `constants.ts` de un applet |
| `flow_inspect_controls` | — | Controles reales de la UI |
| `flow_dryrun_recipe` | — | Aplica una receta sin generar |
| `flow_generate` | 0 créditos | Una imagen |
| `flow_batch_generate` | 0 créditos | Producto cartesiano de una matriz |
| `flow_upscale_local` | — | Upscale local, nearest o lanczos |
| `flow_upscale_native` | **cuesta** | 2K/4K de Flow; requiere Chrome real |

Que generar salga 0 créditos está medido, no supuesto: cada corrida compara
`/v1/credits` antes y después y reporta el delta. Si eso cambia, se ve en la
corrida.

## Comandos

- `/flow-status` — sesión, créditos y herramientas propias
- `/flow-sprites <descripción>` — grillas de 8 direcciones con el Sprite Forge

## Uso desde línea de comandos

Las bibliotecas de `lib/` también sirven como CLI:

```bash
python3 lib/flow_client.py list
python3 lib/flow_driver.py dryrun recipes/sprite-forge-smoke.json
python3 lib/flow_driver.py batch recipes/sprite-forge-facciones.json --limit 2
python3 lib/flow_upscale.py flow-out/ -f 2
```

Las salidas van al cwd (`flow-out/`, `flow-applets/`) salvo que se definan
`FLOW_OUT`, `FLOW_OUT` o `FLOW_APPLETS`.

## Configuración

| Variable | Para qué |
|---|---|
| `FLOW_COOKIES` | Ruta al archivo de cookies |
| `FLOW_CONFIG_DIR` | Directorio de config (default `~/.config/google-flow`) |
| `FLOW_PROJECT_ID` | Proyecto de Flow a usar |
| `FLOW_OUT` | Carpeta de salida de las tools de MCP |
| `FLOW_APPLETS` | Dónde guardar el código de applets descargado |
| `FLOW_LIB` | Apuntar a otro checkout de `lib/` (desarrollo) |

## Lo que no hace

- **Subir imágenes de referencia.** Sin eso, el Map Compiler y el modo colisión
  del Layer Forge no son automatizables: los dos arrancan de un mapa existente.
- **Crear applets.** El endpoint `flowCreationAgent/sessions` está mapeado pero
  no implementado.

## Ritmo

El driver se mueve despacio a propósito y en batch reutiliza una sola pestaña.
Google Labs no publica límites de uso, y una cuenta marcada como automatizada se
pierde con todo el trabajo que dependía de ella. Las constantes están en
`lib/flow_driver.py`; no bajarlas.

Cuando una ruta rechaza a un browser automatizado, la salida es conectarse a un
Chrome real por CDP (`cdp_url`), no falsear el fingerprint.

## Detalles técnicos

`skills/flow-assets/references/api-map.md` tiene el mapa de endpoints, el
mecanismo de autenticación en dos saltos, y qué protege reCAPTCHA y qué no.
