# Google Labs Flow API map

Reconstructed by observing the frontend's traffic. There's no public API or
stable contract: all of this can change without notice.

## Two-hop authentication

```
cookie __Secure-next-auth.session-token        (lasts months)
  │
  ├─► GET labs.google/fx/api/auth/session ──► access_token  (bearer ya29…, hours)
  │
  └─► Authorization: Bearer ──► aisandbox-pa.googleapis.com/v1/*
```

The cookie lives in `labs.google.cookies.json` at the repo root and is in
`.gitignore` — it's the user's Google session. The bearer is re-derived from
the cookie on every run and cached in `.flow-token.json` until it expires.

When the cookie expires, every tool fails with an auth error. The only fix
is for the user to re-export the cookies from the browser.

## Endpoints

### labs.google/fx — frontend (uses the cookie)

| Route | What for |
|---|---|
| `/api/auth/session` | Derive the bearer; also returns user and expiration |
| `/api/trpc/flow.projectInitialData` | Initial project state |
| `/api/trpc/videoFx.getFlowAppConfig` | App flags |

### aisandbox-pa.googleapis.com/v1 — backend (uses the bearer)

| Route | What for | reCAPTCHA |
|---|---|---|
| `credits` | Balance and tier | no |
| `flowAppletAgent/applets` | Applet catalog | no |
| `flowAppletAgent/applets/{id}/versions/{v}` | Source code and creation session | no |
| `flowAppletAgent/savedSharedApplets` | Other users' saved applets | no |
| `flowCreationAgent/sessions` | Agent that creates applets | no |
| `flow/appConfig` | Config, upsampling flags | no |
| `flow/models/statuses` | Model health | no |
| `projects/{id}/flowMedia:batchGenerateImage` | **Generate images** | no |
| `flow/upsampleImage` | **2K/4K upscale** | **yes** |
| `flow/uploadImage` | Upload references | probably |

## reCAPTCHA: what it protects and what it doesn't

Only the routes that **spend quota** validate reCAPTCHA Enterprise. Verified
by hooking `grecaptcha.enterprise.execute`: a full image generation never
invokes it once. That's why the driver generates just fine from an automated
browser, and upscale doesn't.

The token **doesn't go in a header**: it travels in the body.

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

The request is sent with `content-type: text/plain;charset=UTF-8`. Sending
`application/json` would trigger a CORS preflight the endpoint doesn't expect.

Site key: `6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV`.

### Why an automated browser isn't enough

Tokens issued by a Chromium launched by Playwright get a low score and the
backend responds `403 PUBLIC_ERROR_UNUSUAL_ACTIVITY`. **It doesn't depend on
the `action`**: five different values (empty, `UPSAMPLE`, `upsample`,
`upsampleImage`, `PINHOLE`) got the same rejection, tested with a fake
`mediaId` so the operation fails before spending credits.

The way out is `cdp_url` pointing at a regular Chrome:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

## mediaId

The `mediaId` that `upsampleImage` accepts is the UUID from
`media[].image.generatedImage.mediaId` in `flowMedia:batchGenerateImage`'s
response. That same response carries other fields also called `mediaId`
with a long base64 media-key (`CAMSJDc1…`) that the backend does **not**
accept.

## The SDK the applets see

Applets compile in the browser with esbuild.wasm and import
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

The SDK isn't exposed on `window`: the applet runs in an isolated iframe
titled `Flow App`, which is same-origin and so can be driven through the DOM.

## Why the UI is driven instead of replicating the protocol

`flowMedia:batchGenerateImage` could be replicated directly, but driving the
published applet has two advantages that matter more than speed: it's
immune to internal payload changes, and it respects the prompt logic that
lives inside each applet — the `promptBuilder.ts` files that assemble the
final prompt from the controls are exactly the tool's value.
