# Mapa de la API de Google Labs Flow

Reconstruido observando el tráfico del frontend. No hay API pública ni contrato
estable: todo esto puede cambiar sin aviso.

## Autenticación en dos saltos

```
cookie __Secure-next-auth.session-token        (dura meses)
  │
  ├─► GET labs.google/fx/api/auth/session ──► access_token  (bearer ya29…, horas)
  │
  └─► Authorization: Bearer ──► aisandbox-pa.googleapis.com/v1/*
```

La cookie vive en `labs.google.cookies.json` en la raíz del repo y está en
`.gitignore` — es la sesión Google del usuario. El bearer se re-deriva de la
cookie en cada corrida y se cachea en `.flow-token.json` hasta que vence.

Cuando la cookie caduca, todas las tools fallan con error de autenticación. La
única solución es que el usuario reexporte las cookies desde el navegador.

## Endpoints

### labs.google/fx — frontend (usa la cookie)

| Ruta | Para qué |
|---|---|
| `/api/auth/session` | Derivar el bearer; también trae usuario y vencimiento |
| `/api/trpc/flow.projectInitialData` | Estado inicial del proyecto |
| `/api/trpc/videoFx.getFlowAppConfig` | Flags de la app |

### aisandbox-pa.googleapis.com/v1 — backend (usa el bearer)

| Ruta | Para qué | reCAPTCHA |
|---|---|---|
| `credits` | Saldo y tier | no |
| `flowAppletAgent/applets` | Catálogo de applets | no |
| `flowAppletAgent/applets/{id}/versions/{v}` | Código fuente y sesión de creación | no |
| `flowAppletAgent/savedSharedApplets` | Applets guardados de otros | no |
| `flowCreationAgent/sessions` | Agente que crea applets | no |
| `flow/appConfig` | Config, flags de upsampling | no |
| `flow/models/statuses` | Salud de los modelos | no |
| `projects/{id}/flowMedia:batchGenerateImage` | **Generar imágenes** | no |
| `flow/upsampleImage` | **Upscale 2K/4K** | **sí** |
| `flow/uploadImage` | Subir referencias | probablemente |

## reCAPTCHA: qué protege y qué no

Sólo las rutas que **gastan cuota** validan reCAPTCHA Enterprise. Verificado
hookeando `grecaptcha.enterprise.execute`: una generación de imagen completa no
lo invoca ni una vez. Por eso el driver genera sin problema desde un browser
automatizado, y el upscale no.

El token **no va en un header**: viaja en el body.

```json
{
  "mediaId": "00000000-0000-0000-0000-000000000000",
  "targetResolution": "UPSAMPLE_IMAGE_RESOLUTION_2K",
  "clientContext": {
    "recaptchaContext": {
      "token": "0cAFcWeA…",
      "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
    },
    "projectId": "…",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_ONE",
    "sessionId": ";1786646591140"
  }
}
```

El request se manda con `content-type: text/plain;charset=UTF-8`. Mandar
`application/json` dispararía un preflight CORS que el endpoint no espera.

Site key: `6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV`.

### Por qué un browser automatizado no alcanza

Los tokens que emite un Chromium lanzado por Playwright reciben score bajo y el
backend responde `403 PUBLIC_ERROR_UNUSUAL_ACTIVITY`. **No depende del
`action`**: cinco valores distintos (vacío, `UPSAMPLE`, `upsample`,
`upsampleImage`, `PINHOLE`) dieron el mismo rechazo, probados con un `mediaId`
falso para que la operación falle antes de gastar créditos.

La salida es `cdp_url` apuntando a un Chrome normal:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

## mediaId

El `mediaId` que acepta `upsampleImage` es el UUID de
`media[].image.generatedImage.mediaId` en la respuesta de
`flowMedia:batchGenerateImage`. Esa misma respuesta trae otros campos también
llamados `mediaId` con un media-key largo en base64 (`CAMSJDc1…`) que el backend
**no** acepta.

## El SDK que ven los applets

Los applets se compilan en el browser con esbuild.wasm e importan
`{ Flow } from 'flow-sdk'`:

```js
Flow.generate.image({ prompt, modelDisplayName, aspectRatio, referenceImageMediaIds })
  → { mediaId, base64, mimeType }
Flow.generate.text(prompt, { images, systemInstruction })  → { text }
Flow.media.select({ filter })
Flow.upload({ base64, mimeType, name })
Flow.save({ base64, mimeType, name })
Flow.download({ base64, mimeType, filename })
```

El SDK no está expuesto en `window`: el applet corre en un iframe aislado
titulado `Flow App`, que sí es same-origin y por eso se puede conducir por DOM.

## Por qué se conduce la UI y no se replica el protocolo

Podría replicarse `flowMedia:batchGenerateImage` directamente, pero conducir el
applet publicado tiene dos ventajas que importan más que la velocidad: es inmune
a cambios internos del payload, y respeta la lógica de prompts que vive en cada
applet — los `promptBuilder.ts` que arman el prompt final a partir de los
controles son justamente el valor de la herramienta.
