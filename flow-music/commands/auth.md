---
description: Verificar la sesión de Flow Music y guiar la renovación de cookies si hace falta
---

# /flowmusic:auth

Chequea la precondición de autenticación de Flow Music y, si no se cumple, guía
al usuario para renovarla. No genera nada ni gasta créditos.

## Pasos

1. Llamá `flowmusic_auth_status`. Es local: no toca la red.

2. Interpretá:

   - **`valid: true`** — informá a quién pertenece la sesión y cuánto le queda
     (en minutos, no en segundos crudos). Terminá ahí.
   - **`valid: false` con `can_refresh: true`** — decí que el token venció pero
     se renueva solo, y confirmalo llamando `flowmusic_account`. Si eso funciona,
     está resuelto.
   - **`valid: false` con `can_refresh: false`, o error de autenticación** — pasá
     al punto 3.

3. Pedí la renovación con instrucciones concretas:

   > Necesito que reexportes las cookies de Flow Music:
   > 1. Abrí `https://www.flowmusic.app/` en Chrome y confirmá que estás logueado.
   > 2. Exportá las cookies del dominio a JSON (extensión tipo *Cookie-Editor* →
   >    Export → JSON).
   > 3. Guardá el archivo como `www.flowmusic.app.cookies.json` en la raíz del repo.
   >
   > Avisame cuando esté y sigo.

4. Cuando el usuario confirme, volvé a `flowmusic_auth_status` y luego
   `flowmusic_account` para verificar de punta a punta.

5. Higiene, una sola vez tras cada renovación:

   ```bash
   chmod 600 www.flowmusic.app.cookies.json
   git check-ignore -v www.flowmusic.app.cookies.json
   ```

   Si `git check-ignore` no lo reporta como ignorado, **avisá fuerte**: hay una
   sesión completa a punto de entrar al repo.

## Qué no hacer

- No reintentes las tools mientras la sesión esté vencida.
- No le pidas al usuario que pegue el token ni el contenido del archivo en el chat.
- No intentes loguearte vos ni completar formularios de login.
