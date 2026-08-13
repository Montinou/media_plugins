# media_plugins

Marketplace de plugins de Claude Code para producir audio e imagen con
herramientas de IA que **no exponen API pública**. Cada plugin resuelve el mismo
problema de fondo: usar la sesión del navegador para llegar a un servicio que
sólo tiene UI.

## Plugins

| Plugin | Servicio | Estado |
|---|---|---|
| [`aerthos-flow`](./aerthos-flow) | [Google Labs Flow](https://labs.google/fx/tools/flow) | funcionando |
| `flow-music` | [Flow Music](https://www.flowmusic.app) | pendiente |
| `suno` | [Suno](https://suno.com) | pendiente |

## Instalación

```
/plugin marketplace add Montinou/media_plugins
/plugin install aerthos-flow@media-plugins
```

Instalar el plugin no da acceso a ninguna cuenta: cada uno pone sus propias
credenciales de sesión, que nunca viven en este repo.

## Requisitos comunes

Los plugins conducen un navegador real, así que comparten base:

- `python3` con `playwright`, `requests` y `pillow`
- Google Chrome instalado
- Las credenciales de sesión del servicio en `~/.config/<plugin>/`

Ninguno necesita el SDK de MCP: los servidores hablan JSON-RPC sobre stdio con
la stdlib. Es deliberado — el Python de Homebrew está bajo PEP 668, e instalar
el SDK obligaría a `--break-system-packages` sobre el intérprete del sistema.

## Credenciales

Cada plugin busca sus cookies en `~/.config/<plugin>/`, y ninguna credencial
vive en este repo. Para `aerthos-flow`:

```bash
mkdir -p ~/.config/aerthos-flow
# exportar las cookies de labs.google desde el navegador a:
#   ~/.config/aerthos-flow/labs.google.cookies.json
chmod 600 ~/.config/aerthos-flow/labs.google.cookies.json
```

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

## Estructura

```
.claude-plugin/marketplace.json   catálogo
<plugin>/
├── .claude-plugin/plugin.json    manifest
├── .mcp.json                     servidor MCP
├── lib/                          bibliotecas (autocontenido)
├── mcp/server.py                 tools
├── skills/                       guías de uso
└── commands/                     slash commands
```

Cada plugin es autocontenido: `lib/` viaja adentro para que funcione instalado,
sin depender de ningún otro repo.
