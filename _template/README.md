# _template — armar un plugin nuevo

Esqueleto **funcional** de un plugin de este marketplace. No es pseudocódigo:
corre tal cual. Probalo antes de tocar nada:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{}}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python3 _template/mcp/server.py
```

`_template` empieza con guion bajo y **no está listado en el marketplace**, así
que no se instala por accidente.

## Las dos capas

Antes de escribir una línea, ubicá cada cosa en su lugar:

| Capa | Qué va | ¿Sirve para cualquiera? |
|---|---|---|
| **core** — `lib/`, `mcp/`, `skills/`, `commands/` | auth, ritmo, endpoints, tools | **sí** |
| **pack** — `packs/<proyecto>/` | ids de tus herramientas, presets, prompts | **no**, es tuyo |

**Si otra persona no puede usarlo tal cual, es un pack.** Ver
[`packs/README.md`](./packs/README.md).

El core tiene que funcionar sin ningún pack. Un pack agrega atajos, no
capacidades.

## Receta

```bash
cp -R _template mi-servicio
cd mi-servicio
```

1. **`lib/service.py`** — cambiá `SERVICE`, `BASE`, `COOKIE_FILENAME`. Adaptá
   `auth_status()` al esquema real (si hay JWT, decodificalo y devolvé
   `expires_in_seconds`). Dejá `_throttle` como está.
2. **`mcp/server.py`** — cambiá `SERVER_NAME`, reemplazá las tools de ejemplo.
   La capa JSON-RPC no se toca.
3. **`.claude-plugin/plugin.json`** y **`.mcp.json`** — nombre, descripción,
   comandos.
4. **`skills/<servicio>/SKILL.md`** — cuándo usar el plugin, precondición de
   auth, cuidados, mapa de la API, flujos de navegador.
5. **`commands/auth.md`** — el flujo de renovación de credenciales.
6. **`hooks/preflight.py`** — chequeo local de sesión al arrancar.
7. **`doctor.py`** — verificación de instalación.
8. Agregá la entrada en `../.claude-plugin/marketplace.json`.

Verificá con `python3 mi-servicio/doctor.py`.

## Reglas que no son negociables

Están en el core porque son la diferencia entre una cuenta sana y una bloqueada:

- **Ritmo pausado.** `_throttle` en toda request. Nada de ráfagas, reintentos
  rápidos ni descargas en paralelo.
- **Credenciales fuera del repo.** `~/.config/<plugin>/`, permisos `600`, y en
  `.gitignore`. Nunca en un pack, nunca en el chat.
- **Un path explícito que no existe es un error**, no una invitación a buscar en
  otro lado: usar la cuenta equivocada en silencio es peor que fallar.
- **Los errores de auth no se reintentan.** Se le pide al usuario que reexporte.
- **No se evade la detección de bots**, ni CAPTCHAs, ni un 403. Si una puerta
  está cerrada a propósito, está cerrada.
- **Confirmar antes de gastar créditos** o de cualquier acción irreversible.
- **Nunca reproducir audio** para "verificar": medir con `ffprobe`/`ffmpeg`.

## Decidir MCP o navegador

No todo servicio merece un cliente HTTP. Antes de escribirlo, respondé:

1. **¿La sesión se puede renovar sin el navegador?** Si el export de cookies no
   trae con qué refrescar, un cliente se muere en una hora. (Le pasa a `suno`.)
2. **¿Hay protección anti-bot?** Sin el clearance del navegador, las requests de
   script disparan challenges.
3. **¿Los términos permiten acceso automatizado?**
4. **¿Cuánto ahorra realmente?** Si la acción es un click, automatizarla aporta
   poco y arriesga la cuenta.

Con dos "no", el plugin va por navegador y el MCP se limita a diagnóstico local
y verificación de lo descargado — que es exactamente lo que hace `suno`.
Con cuatro "sí", cliente HTTP, como `flow-music`.
