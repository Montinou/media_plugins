---
name: example
description: Use when working with <servicio> — describí acá las tareas concretas que dispara esta skill (bajar assets, generar, revisar cuenta) y los términos que el usuario va a nombrar. Esta línea decide si la skill se carga, así que escribila pensando en qué va a decir el usuario, no en cómo se llama el plugin.
---

# <Servicio>

Una o dos líneas: qué es el servicio y qué resuelve este plugin.

Aclará desde el principio cómo se reparte el trabajo, porque casi nunca es todo
por un solo lado:

- **MCP (`<servicio>_*`)** — qué se hace por API.
- **Navegador** — qué sólo se puede hacer en la UI.

## Precondición: autenticación

**Antes de la primera operación de cada sesión, llamá `<servicio>_auth_status`.**
Es local, gratis y no toca la red.

| Resultado | Qué hacer |
|---|---|
| `valid: true` | seguir |
| `valid: false` (renovable) | seguir; se renueva sola |
| `valid: false` (no renovable) | **parar y pedir renovación al usuario** |
| tool falla con `AUTENTICACIÓN:` | ídem |

Pedí la renovación con instrucciones concretas: qué exportar, de dónde, con qué
nombre y adónde. **Nunca** reintentes una tool que falló por autenticación ni
pruebes otras "a ver si andan": un 401 repetido es lo que hace que marquen una
cuenta.

## Cuidados de comportamiento

Adaptá esta lista, pero no la borres — es el motivo de que el plugin sea seguro:

1. **Ritmo pausado.** Nada de ráfagas, reintentos rápidos ni paralelismo.
2. **No reproduzcas audio.** Verificá midiendo (`ffprobe`, `astats`), no escuchando.
3. **No evadas un bloqueo.** Un 403 o un CAPTCHA es una decisión del proveedor.
4. **Confirmá antes de gastar** créditos o de cualquier acción irreversible.
5. **Verificá lo que entregás** en vez de confiar en el nombre del archivo.
6. **No borres nada del usuario.**

## Flujos

Paso a paso de las operaciones típicas. Incluí lo que sólo se aprende
operando: cuánto tarda cada cosa, qué estados intermedios muestra la UI, qué
falla y por qué.

## Mapa de la API

Base, autenticación, y la tabla de endpoints con lo que devuelve cada uno.
Anotá las trampas: campos que existen pero mienten, endpoints que niegan algo a
propósito, límites reales.

## Packs

Si el plugin admite atajos específicos de un proyecto, explicá cómo se activan
(`<SERVICIO>_PACK`) y qué aportan. **El core funciona sin ningún pack**: si una
tool sólo anda con pack, está mal diseñada.
