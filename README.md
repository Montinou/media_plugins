# media_plugins

Marketplace de plugins de Claude Code para producir audio e imagen con
herramientas de IA que **no exponen API pública**. Cada plugin resuelve el mismo
problema de fondo: usar la sesión del navegador para llegar a un servicio que
sólo tiene UI.

## Plugins

| Plugin | Servicio | Qué resuelve |
|---|---|---|
| [`google-flow`](./google-flow) | [Google Labs Flow](https://labs.google/fx/tools/flow) | generar assets en batch conduciendo los applets, y upscalear |
| [`flow-music`](./flow-music) | [Flow Music](https://www.flowmusic.app) | catálogo, créditos y descarga de stems **incluido el bass** |
| [`suno`](./suno) | [Suno](https://suno.com) | Studio 2.0, export multitrack en WAV y verificación local |

## Instalación

```
/plugin marketplace add Montinou/media_plugins
/plugin install google-flow@media-plugins
/plugin install flow-music@media-plugins
/plugin install suno@media-plugins
```

Cada plugin trae un `doctor.py` que verifica su instalación sin gastar nada:

```bash
python3 google-flow/doctor.py
python3 flow-music/doctor.py
python3 suno/doctor.py
```

Instalar el plugin no da acceso a ninguna cuenta: cada uno pone sus propias
credenciales de sesión, que nunca viven en este repo.

## Requisitos

Lo único común es `python3` y las credenciales de sesión en
`~/.config/<plugin>/`. Lo demás depende de cuánto navegador use cada uno:

| Plugin | Necesita |
|---|---|
| `google-flow` | `playwright`, `requests`, `pillow` y Google Chrome — conduce los applets |
| `flow-music` | sólo stdlib. `ffmpeg` opcional, para verificar stems |
| `suno` | sólo stdlib. `ffmpeg` para verificar stems; el navegador lo maneja el agente |

Ninguno necesita el SDK de MCP: los servidores hablan JSON-RPC sobre stdio con
la stdlib. Es deliberado — el Python de Homebrew está bajo PEP 668, e instalar
el SDK obligaría a `--break-system-packages` sobre el intérprete del sistema.

## Credenciales

Cada plugin busca sus cookies en `~/.config/<plugin>/`, y ninguna credencial
vive en este repo:

| Plugin | Archivo |
|---|---|
| `google-flow` | `~/.config/google-flow/labs.google.cookies.json` |
| `flow-music` | `~/.config/flowmusic/cookies.json` |
| `suno` | `~/.config/suno/cookies.json` |

```bash
mkdir -p ~/.config/google-flow
# exportar las cookies del servicio desde el navegador al archivo de arriba
chmod 600 ~/.config/google-flow/labs.google.cookies.json
```

Los plugins también aceptan el JSON en la raíz del proyecto en el que estés
trabajando, o en una ruta explícita por variable de entorno
(`FLOW_COOKIES`, `FLOWMUSIC_COOKIES`, `SUNO_COOKIES`). Si esa variable apunta a
un archivo que no existe, **fallan en vez de buscar en otro lado**: usar la
cuenta equivocada en silencio es peor que un error.

Las cookies de sesión son equivalentes a estar logueado en la cuenta. El
`.gitignore` cubre los patrones habituales, pero la regla real es que no entren
al repo bajo ningún nombre.

## Sobre automatizar servicios sin API

Estos plugins existen porque la herramienta que hace falta sólo tiene interfaz
web. Eso trae tres consecuencias que están escritas en cada skill y no son
opcionales:

**El ritmo es lento a propósito.** Ningún servicio de estos publica límites de
uso, y una cuenta marcada como automatizada se pierde con todo el trabajo que
dependía de ella. Las pausas entre acciones no se bajan.

**No se evade la detección de bots.** Cuando una ruta rechaza a un browser
automatizado, la respuesta es conectarse a un Chrome real por CDP, no falsear el
fingerprint. Evadir la detección provoca exactamente el bloqueo que se quiere
evitar.

**Los costos se miden, no se suponen.** Antes de una tanda larga, una corrida
corta que compare el saldo antes y después. Los créditos son del dueño de la
cuenta.

Nada de esto usa credenciales ajenas ni sortea un muro de pago: automatiza la
cuenta propia de quien lo instala. Los endpoints están reconstruidos observando
el tráfico del frontend, no hay contrato estable, y pueden cambiar sin aviso —
si un plugin deja de andar de golpe, esa suele ser la razón.

## Core y packs

Cada plugin tiene dos capas, y la distinción es lo que lo hace instalable por
otra persona:

| Capa | Qué vive ahí | ¿Sirve para cualquiera? |
|---|---|---|
| **core** — `lib/`, `mcp/`, `skills/`, `commands/` | cómo hablarle al servicio: auth, ritmo, endpoints, tools | **sí** |
| **pack** — `packs/<proyecto>/` | ids de tus herramientas, presets, prompts, nombres de tu proyecto | **no**, es tuyo |

**La regla: si otra persona no puede usarlo tal cual, es un pack.** Un
`appletId`, un `projectId`, la lista de facciones de tu juego — nada de eso va
en el core.

El core tiene que funcionar **sin ningún pack**: un pack agrega atajos, no
capacidades. Si una tool sólo anda con pack, esa tool está mal diseñada.

Los packs se eligen por variable de entorno (`<SERVICIO>_PACK`), nunca
hardcodeados, y también se leen desde `~/.config/<plugin>/packs/` para los que
no querés publicar.

Ningún pack lleva credenciales. Esas van en `~/.config/<plugin>/`, siempre.

## Armar un plugin nuevo

[`_template/`](./_template) es un esqueleto **funcional** — corre tal cual:

```bash
python3 _template/doctor.py
cp -R _template mi-servicio
```

Trae el cliente base (auth, ritmo, errores accionables), un servidor MCP
completo, hook de precondición, skill, command y doctor. La receta paso a paso
está en su README, incluida la pregunta que conviene hacerse antes de escribir
nada: **si el servicio merece un cliente HTTP o hay que operarlo por navegador.**

`_template` no está listado en el catálogo, así que no se instala por accidente.

## Estructura

```
.claude-plugin/marketplace.json   catálogo
_template/                        esqueleto para plugins nuevos
<plugin>/
├── .claude-plugin/plugin.json    manifest
├── .mcp.json                     servidor MCP
├── lib/                          bibliotecas (autocontenido)
├── mcp/server.py                 tools
├── hooks/                        precondición de sesión al arrancar
├── skills/                       guías de uso
├── commands/                     slash commands
├── packs/<proyecto>/             lo específico de cada proyecto
└── doctor.py                     verificación de instalación
```

Cada plugin es autocontenido: `lib/` viaja adentro para que funcione instalado,
sin depender de ningún otro repo.
