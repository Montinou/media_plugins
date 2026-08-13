# suno

Operar **Suno** con criterio: el Studio 2.0 (DAW multipista, export de stems en
WAV), la generación fuera del Studio, y verificación local de lo descargado.

## Instalación

```
/plugin marketplace add Montinou/media_plugins
/plugin install suno@media-plugins
```

## El MCP no toca la red, a propósito

A diferencia de `flowmusic`, acá **ninguna tool hace requests a Suno**. Tres
razones verificadas:

1. **No se puede renovar la sesión.** Auth es Clerk, JWT de 1 hora. El export
   de cookies trae `__client_uat` pero **no `__client`**, que es con lo que
   Clerk emite tokens nuevos. Un script se muere a la hora, siempre.
2. **Cloudflare.** Sin `cf_clearance`, las requests de script llegan con
   fingerprint de bot — justo lo que dispara challenges.
3. **Los ToS prohíben el acceso automatizado.** Está en juego la cuenta, la
   suscripción y el catálogo del usuario.

Y sobre todo: el export multitrack **es un click**. Automatizarlo aporta poco.

La operación va por navegador con la sesión del usuario; el MCP aporta
diagnóstico local y verificación.

## Qué trae

**MCP `suno`** (stdio, sin pip, sin red):

| Tool | Qué hace |
|---|---|
| `suno_auth_status` | handle, plan, expiración; y si la sesión sería renovable (casi siempre no) |
| `suno_inspect_multitrack` | analiza un zip exportado sin extraerlo: tracks, tamaños, alineación, stems faltantes |
| `suno_verify_stem` | RMS por bandas para confirmar que un stem es lo que dice |

**Comandos:** `/suno:auth`, `/suno:stems`
**Skills:** `suno-studio` (el DAW y el export), `suno-browser` (operación segura
en navegador y todo lo que está fuera del Studio).

## Precondición

`suno.com.cookies.json` en la raíz del repo (o `SUNO_COOKIES`). Si el token
venció **no es un bloqueo para trabajar por navegador**: alcanza con que el
usuario abra `suno.com` logueado y se renueva sola. El hook de `SessionStart`
avisa cuando corresponde.

## Los stems

Suno Studio separa **solo** al cargar una canción, en 7 pistas: Vocals, Backing
Vocals, Drums, Bass, Guitar, Synth (más el mix). `Export → Multitrack` da un zip
con un **WAV PCM float32 48 kHz** por pista, todos del mismo largo exacto y
listos para un DAW.

Pesa: ~421 MB para un tema de 3 minutos. Hay que esperar, no reintentar.

## Reglas duras

- **Nunca** tocar un control de reproducción.
- **Nunca** resolver un CAPTCHA o challenge de Cloudflare.
- **Nunca** publicar una canción sin pedido explícito (el feed de Suno es público).
- Confirmar todo lo que consuma créditos o modifique la cuenta.
