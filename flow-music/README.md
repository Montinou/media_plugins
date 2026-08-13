# flowmusic

Puente a **Google Flow Music** (`flowmusic.app`, que por debajo es Riffusion):
catálogo, créditos y descarga de stems —**incluido el de bass**— por la API.

## Instalación

```
/plugin marketplace add Montinou/media_plugins
/plugin install flow-music@media-plugins
```

## Precondición

Necesita una sesión válida en `www.flowmusic.app.cookies.json`, en la raíz del
repo (o `FLOWMUSIC_COOKIES` apuntando al archivo). El hook de `SessionStart`
avisa si venció y no puede renovarse sola; `/flowmusic:auth` guía la renovación.

El archivo es una sesión completa: `chmod 600` y cubierto por `*.cookies.json`
en `.gitignore`.

## Qué trae

**MCP `flowmusic`** (stdio, sin dependencias de pip):

| Tool | Red | Qué hace |
|---|---|---|
| `flowmusic_auth_status` | no | estado de sesión; primera parada siempre |
| `flowmusic_account` | sí | usuario y **saldo real** de créditos |
| `flowmusic_list_songs` | sí | canciones del usuario |
| `flowmusic_list_stems` | sí | temas que ya tienen stems |
| `flowmusic_stem_urls` | sí | URLs sin descargar |
| `flowmusic_download_stems` | sí | baja los 4 stems a disco |
| `flowmusic_download_song` | sí | baja la mezcla (WAV si existe) |

**Comandos:** `/flowmusic:auth`, `/flowmusic:stems`
**Skill:** `flowmusic` — API, restricción del bass, cuidados y flujos de navegador.

## Lo que hay que saber

- **El bass.** La UI y `/__api/download/audio/{id}` lo niegan (403), pero el
  `audio_url` del clip apunta a un bucket público que responde 200 — la misma
  URL que abre "Open Stem" en los spaces. `flowmusic_download_stems` ya usa esa
  vía.
- **Los créditos del sidebar no son el saldo**: son el cupo diario gratis.
- **Separar stems no lo hace la API.** Hay que correr *Split stems* en la web.
- **`wav_url` miente en los stems**: viene poblado pero da 404. Solo sirve en
  clips de canción.

## Ritmo

El cliente impone 2,5 s entre requests (`FLOWMUSIC_MIN_INTERVAL`). No lo bajes:
nada de ráfagas, reintentos rápidos ni descargas en paralelo.
