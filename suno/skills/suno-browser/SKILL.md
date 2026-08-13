---
name: suno-browser
description: Use when driving suno.com in a browser — generating songs, browsing the library, downloading, or any Suno task outside the Studio. Covers why Suno must never be scripted over HTTP, Cloudflare and account-safety rules, session handling, and the browser interaction patterns that actually work.
---

# Suno en el navegador

**En Suno se opera por navegador, siempre.** No es una preferencia de estilo:
es la única forma que no arriesga la cuenta del usuario.

## Por qué no hay cliente HTTP

Tres razones concretas, todas verificadas:

1. **No se puede renovar la sesión.** Auth es **Clerk** (`auth.suno.com`), JWT
   RS256 con 1 hora de vida. El export de cookies del navegador trae
   `__client_uat` (un timestamp) pero **no `__client`**, que es la cookie con la
   que Clerk emite tokens nuevos. Un script se muere a la hora, siempre.
2. **Cloudflare.** No hay `cf_clearance` en las cookies exportadas. Requests
   desde un script llegan sin clearance y con fingerprint de bot: es
   exactamente el patrón que dispara challenges.
3. **Los ToS prohíben el acceso automatizado.** Bajar la música propia desde la
   UI está bien; scriptearlo pone en juego la cuenta, la suscripción y el
   catálogo del usuario.

Si te tienta armar un cliente porque "sería más cómodo": el export multitrack
es **un click**. Automatizarlo aporta poco y arriesga mucho.

**Nunca** resuelvas un CAPTCHA ni un challenge de Cloudflare. Si aparece uno,
pará y decíselo al usuario.

## Sesión

`suno_auth_status` es local y no toca la red. Devuelve handle, plan y expiración.

- Token vencido **no es un bloqueo** para trabajar por navegador: basta con que
  el usuario abra `https://suno.com/` con la sesión iniciada y se renueva sola.
- Solo pedí reexportar `suno.com.cookies.json` si necesitás el diagnóstico local.
- El archivo es una sesión completa: `chmod 600`, gitignoreado, jamás en el chat.

## Reglas de comportamiento

1. **Jamás toques play.** Suno tiene reproductor persistente abajo y autoplay en
   varias vistas. Ningún control de reproducción, en ninguna vista, nunca.
2. **Ritmo humano.** Un paso a la vez, con esperas reales entre acciones. Nada
   de ráfagas de clicks ni de recargas repetidas. Si algo tarda, esperá.
3. **Pestaña propia** (`tabs_create_mcp`). No pises pestañas del usuario, y
   cerrá las tuyas al terminar salvo que pida dejarlas.
4. **Confirmá lo que consume créditos o modifica la cuenta**: generar, extender,
   crear personas, publicar, borrar. Y todo lo irreversible: publicar, borrar,
   cambiar visibilidad.
5. **Nunca publiques** una canción sin pedido explícito. Suno tiene feed público:
   publicar es exponer material del usuario.
6. **No aceptes términos ni consentimientos** por tu cuenta.
7. **Verificá las descargas** con `suno_inspect_multitrack` / `suno_verify_stem`
   en vez de reproducir.

## Mapa de la app

| Ruta | Qué es |
|---|---|
| `/` → `/discover` | feed público |
| `/create` | generador principal |
| `/studio` | DAW multipista (ver skill `suno-studio`) |
| `/library` | canciones del usuario |
| `/explore` | descubrimiento |
| `/me` | perfil |

CDNs de audio: `cdn1.suno.ai`, `cdn2.suno.ai`, `cdn-o.suno.com`.
El front es Next.js con ~99 chunks de nombre hasheado; la landing pública no
expone rutas de API.

## Patrones que funcionan

- **Esperar de verdad.** Después de navegar o de disparar una generación, esperá
  con pausas de varios segundos y volvé a mirar. Suno muestra estados
  intermedios ("heavy traffic", placeholders) que se resuelven solos.
- **Leer antes de clickear.** `get_page_text` o `read_page` para entender el
  estado; `find` para localizar controles por descripción en vez de adivinar
  coordenadas.
- **Verificar el efecto de cada click** con un screenshot antes del siguiente.
  Los menús de Suno se cierran solos y un click a ciegas puede caer en otra cosa.
- **Descargas pesadas**: aparecen como `.crdownload` y pueden tardar minutos.
  Monitoreá el tamaño del archivo en vez de reintentar la acción.

## Fuera del Studio

Base de lo que ofrece `/create`; profundizar acá es trabajo pendiente y conviene
explorar en vivo antes de afirmar detalles:

- Prompt de descripción, o modo **Custom** con letra y estilo por separado.
- Selector de modelo, instrumental on/off, personas y estilos guardados.
- Sobre una canción existente: extender, remasterizar, crear cover, editar letra.
- Descarga individual desde la propia canción (audio y, según plan, WAV).

**Cuando el usuario pida algo de esta zona, explorá la UI en vivo y confirmá lo
que ves antes de dar por buena cualquier afirmación de esta sección.** Preferí
`suno-studio` para todo lo que sea stems.
