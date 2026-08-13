---
name: flowmusic
description: Use when working with Google Flow Music (flowmusic.app) — downloading stems or songs, checking credits, generating music, or driving its Producer UI in the browser. Covers the API map, the bass-stem restriction and how to get it legitimately, session/auth preconditions, and the pacing rules this service requires.
---

# Google Flow Music

Flow Music es la capa de Google sobre **Riffusion**. Este plugin cubre dos
modos de trabajo que se complementan:

- **MCP (`flowmusic_*`)** — leer catálogo, créditos y **bajar stems y canciones**.
- **Navegador** — todo lo que la API no hace: generar música con el Producer y
  correr **Split stems**.

## Precondición: autenticación

**Antes de la primera operación de cada sesión, llamá `flowmusic_auth_status`.**
Es local, gratis y no toca la red.

| Resultado | Qué hacer |
|---|---|
| `valid: true` | seguir |
| `valid: false`, `can_refresh: true` | seguir; se renueva sola en la primera llamada |
| `valid: false`, `can_refresh: false` | **parar y pedirle al usuario que reexporte las cookies** |
| tool falla con `AUTENTICACIÓN:` | ídem: parar y pedir renovación |

Cuando haya que renovar, pedilo así — sin rodeos y sin reintentar mientras tanto:

> La sesión de Flow Music venció. Exportá de nuevo las cookies de
> `www.flowmusic.app` con la sesión iniciada y dejá el JSON en la raíz del repo
> como `www.flowmusic.app.cookies.json`.

**Nunca** reintentes una tool que falló por autenticación, ni pruebes otras
tools "a ver si andan". Un 401/403 repetido es exactamente lo que hace que un
servicio marque una cuenta.

El archivo de cookies es una sesión completa: `chmod 600`, cubierto por
`*.cookies.json` en `.gitignore`, y nunca pegado en un chat, un issue ni un log.

## Cuidados de comportamiento

Estos no son adornos: son las reglas que hacen que el plugin sea seguro de usar.

1. **Ritmo pausado, siempre.** El cliente impone 2,5 s entre requests
   (`FLOWMUSIC_MIN_INTERVAL`). No lo bajes. Nada de ráfagas, nada de reintentos
   rápidos, nada de paralelizar descargas.
2. **No reproduzcas audio.** Ni en el navegador ni localmente. Si necesitás
   saber qué hay en un archivo, medilo (`ffprobe`, `astats` por bandas), no lo
   escuches. El usuario puede estar en una llamada o grabando.
3. **No evadas un 403.** `/__api/download/audio/{bassClipId}` responde 403 a
   propósito. El `audio_url` público **no es una evasión** — es la URL que la
   propia app abre con "Open Stem". Si algún día también da 403, se acabó:
   no busques otra puerta.
4. **Confirmá antes de gastar.** Generar música consume créditos. Mostrá el
   prompt y el saldo (`flowmusic_account`) y esperá el visto bueno.
5. **Verificá lo que entregás.** Después de bajar stems, confirmá que cada
   archivo es lo que dice ser (ver *Verificación* abajo). No confíes en el
   nombre del archivo.
6. **No borres nada del usuario.** Ni descargas viejas, ni clips, ni proyectos.

## Saldo de créditos

`flowmusic_account` devuelve `credits_remaining` y `tokens_remaining`.
**El contador del sidebar de la web NO es el saldo** — es el cupo diario gratis
(30/día, tipo `daily-free`). Confundirlos lleva a decirle al usuario que tiene
29 créditos cuando en realidad tiene diez mil.

## Stems

Flow Music separa en **4 stems**: `vocals`, `drums`, `bass`, `other`, en m4a
(AAC 48 kHz). No hay WAV para stems.

### Flujo

1. `flowmusic_list_stems` — qué temas ya tienen stems.
2. Si el tema no está: **abrir la web y correr "Split stems"** sobre el clip.
   La API no lo dispara; esto es trabajo de navegador.
3. `flowmusic_stem_urls` para mostrar qué se va a bajar (barato, sin efectos).
4. `flowmusic_download_stems` para bajarlos.

### El bass

Tres caminos lo niegan y uno lo entrega:

| Vía | bass |
|---|---|
| Zip "Download tracks" de la UI | ausente |
| Menú `···` → "Download stem" | la opción no aparece |
| `GET /__api/stems/clip/{id}` | no viene |
| `GET /__api/download/audio/{clipId}` | **403** |
| **`audio_url` del clip → bucket público** | **200** ✅ |

En el bundle hay un `new Set(["bass"])` que marca esos clips como caso
especial. Afecta a la UI y al endpoint de descarga, no al asset. Cada stem es un
clip independiente y su `audio_url` apunta a
`storage.googleapis.com/producer-app-public/clips/{clip_id}.m4a`.

**Corolario importante:** si alguien reporta "no me deja bajar el bass", no es
su conexión ni el servidor caído. Es esto, y la solución es
`flowmusic_download_stems`, que ya usa la vía correcta.

### Formatos: la trampa del `wav_url`

`audio_url` (m4a) existe para todos los clips. `wav_url` **solo sirve en clips
de canción** (`audio__create_song`, `audio__render_edit`); en los stems el campo
viene poblado pero devuelve **404**. Hay que comprobarlo, no confiar en que esté
presente. `flowmusic_download_song` ya hace ese chequeo.

### Verificación

Un stem mal etiquetado se detecta midiendo energía por bandas:

```bash
for f in *.m4a; do
  lo=$(ffmpeg -hide_banner -i "$f" -af "lowpass=f=250,astats=measure_perchannel=none" -f null - 2>&1 | grep "RMS level" | head -1 | awk '{print $NF}')
  hi=$(ffmpeg -hide_banner -i "$f" -af "highpass=f=250,astats=measure_perchannel=none" -f null - 2>&1 | grep "RMS level" | head -1 | awk '{print $NF}')
  printf "%-28s <250Hz %9s  >250Hz %9s\n" "$f" "$lo" "$hi"
done
```

En un set sano: **bass** con graves dominando ~14 dB, **drums** ~10 dB (bombo),
**vocals** y **other** con agudos dominando.

## Navegador

Lo que la API no hace. Reglas: pestaña propia, un paso a la vez, y **jamás**
tocar un botón de reproducción.

### Generar una canción

1. `https://www.flowmusic.app/` → campo **"Ask Producer…"**.
2. Escribir el prompt y enviar. El Producer lo reescribe a un bloque `Sound` y
   genera **dos takes**.
3. Tarda ~30–40 s. Esperá con pausas largas; no recargues.
4. La URL pasa a `/session/{uuid}` — ese es el id de la sesión.

Para que los stems salgan limpios, pedí separación explícita en el prompt
("clear separation between bass, drums, guitar and keys").

### Separar stems

Menú `···` del clip → **Split stems**. Tarda ~30 s. Al terminar aparecen los 4
canales con M/S. Después ya podés volver al MCP.

### Spaces (applets)

Los spaces son applets React que corren en `jitterbug.riffusion.com` dentro de
un iframe sandbox. Dos cosas aprendidas a los golpes:

- **No les entra el teclado sintético** desde el frame padre. Usá el árbol de
  accesibilidad, o abrí el applet standalone.
- **Standalone se cuelga en "Loading…"**: su SDK habla por `postMessage` con el
  host, y fuera de flowmusic.app no hay quien conteste. Para operarlos, tienen
  que estar embebidos.

## Mapa de la API

Base: **`https://www.flowmusic.app/__api`** (proxy same-origin). Pegarle directo
a `wb.flowmusic.app` da CORS desde el browser. Auth: `Authorization: Bearer` con
el `access_token` de la cookie `sb-sb-auth-token.*` (Supabase, chunked, 1 h de
vida, con `refresh_token` adentro).

| Método | Ruta | Notas |
|---|---|---|
| GET | `/users/me` | identidad |
| GET | `/billing/credits` | saldo real |
| GET | `/clips/auth-user` | clips del usuario; los stems son clips con `op_type: audio__split_stems` |
| GET | `/clips/user/{id}`, `/clips/favorites` | catálogo |
| PATCH | `/clips/{id}` | renombrar, etc. |
| GET | `/stems/clip/{id}` | stems en base64 — **sin bass** |
| GET | `/download/audio/{clipId}` | audio; **403 en bass** |
| POST | `/batch-download-clip` | descarga múltiple |
| POST | `/conversation` | mandar mensaje al Producer |
| POST | `/conversation/create` | nueva sesión |
| GET | `/conversations`, `/conversations/{id}` | historial |
| GET | `/operations/{id}` | debug de operación |

Operaciones internas: `audio__create_song`, `audio__split_stems`,
`audio__render_edit`, `audio__apply_effect`, `audio__convert_format`,
`image__create_image`, `video__create_video_clip`, `lyrics__create`,
`code__create_space`.

Hay override de backend por cookie `backend_origin`, validado contra
`*.flowmusic.app` (entornos `wb-snake`, `wb-yoshi`, `wb-zelda`).

El cliente completo está en `lib/flowmusic.py`; para algo no cubierto por una
tool, `FlowMusic.call(method, path, body)` llega a cualquier endpoint de la
tabla respetando el throttle.
