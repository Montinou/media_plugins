---
description: Verificar la sesión de Suno y guiar la renovación si hace falta
---

# /suno:auth

Chequea la precondición de sesión de Suno. Es todo local: no hace una sola
request al servicio.

## Pasos

1. Llamá `suno_auth_status`.

2. Interpretá y contá al usuario, en minutos y no en segundos crudos:

   - **`valid: true`** — informá handle, plan y cuánto queda. Listo.
   - **`valid: false`** — el token venció. Aclarale que **para trabajar por
     navegador no es un bloqueo**:

     > La sesión de Suno figura vencida en el archivo de cookies. Si vamos a
     > operar en el navegador, con que abras `https://suno.com/` en Chrome
     > logueado alcanza: se renueva sola. Solo si querés diagnóstico local
     > reexportá `suno.com.cookies.json`.

   - **Error de autenticación** (falta el archivo o no tiene `__session`) — pedí
     el export:

     > 1. Abrí `https://suno.com/` en Chrome y confirmá que estás logueado.
     > 2. Exportá las cookies del dominio a JSON.
     > 3. Guardalo como `suno.com.cookies.json` en la raíz del repo.

3. Reportá siempre dos cosas del resultado, porque explican el diseño del plugin:

   - **`can_refresh`** — casi siempre `false`: falta la cookie `__client` de
     Clerk, así que no hay renovación programática posible.
   - **`has_cf_clearance`** — normalmente `false`: sin eso, cualquier request de
     script choca con Cloudflare.

   Por eso este plugin **no tiene cliente HTTP** y se opera por navegador.

4. Higiene tras cada renovación:

   ```bash
   chmod 600 suno.com.cookies.json
   git check-ignore -v suno.com.cookies.json
   ```

   Si no está ignorado, avisá fuerte antes de seguir.

## Qué no hacer

- No armes un cliente HTTP contra Suno, por más cómodo que parezca.
- No le pidas al usuario que pegue el token en el chat.
- No intentes loguearte vos ni completar formularios de login.
