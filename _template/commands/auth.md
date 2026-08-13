---
description: Verificar la sesión del servicio y guiar la renovación de credenciales
---

# /example:auth

Chequea la precondición de autenticación y, si no se cumple, guía al usuario
para renovarla. No genera nada ni gasta créditos.

## Pasos

1. Llamá `example_auth_status`. Es local: no toca la red.

2. Interpretá y contale al usuario en unidades humanas (minutos, no segundos):

   - **válida** — informá a quién pertenece y cuánto le queda. Terminá ahí.
   - **vencida pero renovable** — decilo y confirmalo con una tool que salga a
     la red. Si funciona, está resuelto.
   - **vencida y no renovable, o falta el archivo** — pasá al punto 3.

3. Pedí la renovación con instrucciones concretas:

   > Necesito que reexportes las cookies de `<servicio>`:
   > 1. Abrí `<url>` en Chrome y confirmá que estás logueado.
   > 2. Exportá las cookies del dominio a JSON (extensión tipo *Cookie-Editor*).
   > 3. Guardalo en `~/.config/<servicio>/cookies.json`.
   >
   > Avisame cuando esté y sigo.

4. Cuando confirme, volvé a verificar de punta a punta.

5. Higiene, una sola vez tras cada renovación:

   ```bash
   chmod 600 ~/.config/<servicio>/cookies.json
   ```

   Si el archivo quedó dentro de un repo, verificá que esté ignorado:

   ```bash
   git check-ignore -v <ruta>
   ```

   Si no lo está, **avisá fuerte**: hay una sesión completa a punto de entrar al
   control de versiones.

## Qué no hacer

- No reintentes las tools mientras la sesión esté vencida.
- No le pidas al usuario que pegue el token ni el contenido del archivo en el chat.
- No intentes loguearte vos ni completar formularios de login.
