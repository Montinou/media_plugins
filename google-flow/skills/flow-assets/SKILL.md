---
name: flow-assets
description: Use when generating assets with Google Labs Flow — sprites, character turnarounds, map layers, dioramas — or when working with Flow applets, recipes, packs, appletId, projectId, or labs.google tools
---

# Generar assets con Google Labs Flow

Google Labs Flow no tiene API pública. El acceso se apoya en la sesión del
navegador del usuario, y las herramientas ("applets") se ejecutan conduciendo
la app real, no replicando su protocolo.

Las tools `flow_*` del MCP `google-flow` cubren todo el ciclo. Este documento
es para decidir **cuál usar y en qué orden**, y para las tres reglas que no se
negocian.

## Reglas que no se negocian

**1. Dryrun antes de cualquier batch nuevo.** `flow_dryrun_recipe` aplica todos
los controles sin generar. Una receta con un label mal escrito falla en la
variante 14 de 28 si no se verifica antes.

**2. No acelerar ni paralelizar.** Las pausas de `flow_driver.py` (`PACE_MS`,
`PACE_RUN_S`) están puestas a propósito. Google Labs no publica límites de uso,
y una cuenta marcada como automatizada se pierde con todo el trabajo que
dependía de ella. Nunca correr dos batches en paralelo ni bajar las pausas.

**3. No evadir la detección de automatización.** Si una ruta responde 403
`PUBLIC_ERROR_UNUSUAL_ACTIVITY`, la respuesta es usar un Chrome real vía
`cdp_url`, no falsear `navigator.webdriver` ni parchear el fingerprint. Evadir
la detección es exactamente lo que provoca el bloqueo que se quiere evitar.

| Racionalización | Realidad |
|---|---|
| "Son sólo 3 variantes, salteo el dryrun" | El dryrun tarda un minuto; una tanda fallida desperdicia diez. |
| "Bajo la pausa a 5s para esta corrida sola" | El riesgo no es por corrida, es acumulado sobre la cuenta. |
| "Dos batches en paralelo van más rápido" | Duplica la tasa de requests, que es justo lo que se mide. |
| "Un patch de stealth y el upscale anda" | Convierte un 403 recuperable en una cuenta marcada. |
| "El usuario tiene 234 créditos, gastar unos está bien" | Los créditos son suyos. Medir y reportar, no decidir por él. |

## Lo genérico y lo de cada cuenta

Las tools funcionan con cualquier cuenta. Lo que es propio de cada una
—`projectId`, `appletId`, vocabularios de los dropdowns— vive en un **pack**.

Antes de nada, `flow_pack_info`: dice si hay pack activo y qué trae. Si no hay,
`flow_scaffold_pack` genera uno leyendo la cuenta. Sin pack ni
`FLOW_PROJECT_ID`, las tools que abren un applet fallan a propósito: el plugin
no trae el proyecto de nadie hardcodeado.

## Flujo normal

```
flow_session_status        ¿la cookie sirve? ¿cuántos créditos hay?
flow_pack_info             ¿qué herramientas y recetas hay disponibles?
flow_dryrun_recipe         verificar la receta, costo cero
flow_batch_generate        con limit 2-3 primero, después la tanda completa
flow_upscale_local         nearest x2 para pixel art
```

Con un pack activo, las tools de generación aceptan `recipe_name` y no hace
falta armar la receta a mano.

Para una herramienta que no está en el pack:

```
flow_list_applets          conseguir el appletId
flow_get_applet_code       constants.ts trae los valores válidos de los dropdowns
flow_inspect_controls      los labels y el texto exacto del botón de generar
```

Esos dos últimos son los que se saltean y los que causan los fallos: **los
valores de dropdown salen de `constants.ts`, no de adivinar**, y los labels y el
botón salen de `flow_inspect_controls`, no del código. El JSX de los applets
varía demasiado para deducirlos con confianza.

## Costos

Medido comparando `/v1/credits` antes y después; cada corrida reporta el delta.

- **Generar imágenes: 0 créditos.** Las rutas de generación ni siquiera validan
  reCAPTCHA.
- **Upscale nativo 2K/4K: cuesta**, y exige Chrome real.

Si un `flow_generate` reporta un costo distinto de 0, decirlo explícitamente:
significa que Flow cambió de política y el usuario necesita saberlo antes de
lanzar un batch de 28.

## Upscale: local casi siempre

Para pixel art, `flow_upscale_local` con `nearest` y factor entero es **mejor**
que el 2K nativo, no un reemplazo pobre. El upscaler de Flow es generativo:
interpola justo los bordes duros que el pixel art necesita. Nearest con factor
entero es exacto y sin pérdida — una grilla de 1376x768 sale 2752x1536, por
encima de 2K, gratis.

El 2K nativo tiene sentido sólo para **arte pintado** (fondos, dioramas), donde
la interpolación juega a favor. Ahí requiere `cdp_url` y consume créditos: pedir
confirmación al usuario antes de llamarlo.

## Recetas

Una receta describe cómo manejar los controles de un applet. Esquema completo,
vocabularios de los applets de Aerthos y el detalle de `matrix` en
`references/recipes.md`.

```json
{
  "appletId": "00000000-0000-0000-0000-000000000000",
  "generateButton": "FORJAR GRILLA 8 DIRECCIONES",
  "controls": [
    { "type": "dropdown", "label": "Fondo Chroma", "value": "Magenta puro" }
  ],
  "matrix": {
    "Facción / Linaje": ["Imperio de Aethelria", "Clanes de Crkds"]
  }
}
```

`matrix` sólo la usa `flow_batch_generate`: expande el producto cartesiano y
saltea las variantes cuyo PNG ya existe, así que una tanda interrumpida se
retoma volviéndola a llamar.

## Cuando algo falla

| Síntoma | Causa | Qué hacer |
|---|---|---|
| Error de autenticación | cookie vencida | Pedir al usuario reexportar `labs.google.cookies.json` |
| `no encontré la opción X` | valor que no está en `constants.ts` | Releer constants con `flow_get_applet_code` |
| `no encontré un control con label X` | label sacado del código, no de la UI | Correr `flow_inspect_controls` |
| 403 `PUBLIC_ERROR_UNUSUAL_ACTIVITY` | ruta con costo desde browser automatizado | Usar `cdp_url` con Chrome real |
| El applet no montó | compila con esbuild.wasm en el browser | Subir `loadTimeoutMs`; suele tardar ~30s |
| `no sé con qué proyecto trabajar` | sin pack ni `FLOW_PROJECT_ID` | `flow_scaffold_pack`, o definir la variable |
| El botón de generar está deshabilitado | el applet necesita una imagen subida | No es automatizable todavía: falta el upload de referencias |

## Referencias

- `references/recipes.md` — esquema de recetas y cómo funciona `matrix`
- `references/api-map.md` — endpoints, auth de dos saltos, qué protege reCAPTCHA
- `packs/README.md` del plugin — qué es propio de cada cuenta y cómo generar un pack

El catálogo de herramientas concretas no está acá: vive en el `applets.md` de
cada pack, porque depende de la cuenta.
