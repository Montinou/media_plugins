---
name: suno-studio
description: Use when working in Suno Studio (suno.com/studio) — the multitrack DAW. Covers loading projects, the Legacy vs 2.0 upgrade prompt, per-track effect prompting, and Export → Multitrack to get WAV stems including bass. Read before driving the Studio in a browser.
---

# Suno Studio

`suno.com/studio` es un **DAW multipista**, no un generador. Es la mejor vía que
hay para obtener stems: 7 pistas en WAV sin pérdida, alineadas, en un click.

## Antes de entrar

1. `suno_auth_status` — local, sin red. Si el token venció, pedile al usuario
   que abra `https://suno.com/` en Chrome con la sesión iniciada (al navegar se
   renueva sola).
2. Pestaña propia. Nunca pises otra en la que el usuario esté trabajando.
3. **Regla dura: no toques ningún control de reproducción.** El Studio arranca
   con audio cargado y un play involuntario suena fuerte del otro lado.

## Entrar a un proyecto

Dos caminos:

- **Proyecto guardado** — "Pick up where you left off", o `New empty project`.
- **Cualquier canción** — botón `Edit in Studio` en la lista de la derecha.

Los proyectos viejos traen badge **Legacy**. Al abrirlos aparece un diálogo:

| Opción | Efecto |
|---|---|
| `Open in Studio 1.2 (Legacy)` | abre tal cual, **no crea nada** |
| `Open in Studio 2.0` | **crea una copia** actualizada; no sobreescribe el original |

**Preguntale al usuario cuál quiere.** Studio 2.0 es la versión útil, pero deja
un proyecto nuevo en su cuenta: eso es una modificación de su biblioteca y no es
tuya para decidir.

## La interfaz (2.0)

```
┌ SUNO  [proyecto]  undo/redo   ▸ transporte   87 BPM  4/4   Export  Library
├ 1  <canción original>   S  A   ▓▓▓ waveform ▓▓▓
├ 2  Vocals              S  A   ▓▓▓
├ 3  Backing Vocals      S  A   ▓▓▓
├ 4  Drums               S  A   ▓▓▓
├ 5  Bass                S  A   ▓▓▓
├ 6  Bass                S  A   ▓▓▓
├ 7  Guitar              S  A   ▓▓▓
├ 8  Synth               S  A   ▓▓▓
├ + Add New Track
└ Mstr (master)                  [prompt v5.5]   + Add Track Effects
```

- **Suno separa solo** al cargar la canción. No hay que pedir un "split stems"
  aparte como en Flow Music.
- Cada track: **S** (solo), **A**, fader y waveform sobre la timeline.
- Abajo, un prompt en **BETA** que actúa sobre el track seleccionado y genera
  efectos o material en lenguaje natural — *"build a gritty delay and put it on
  this track"*, *"generate an 8-bar drum loop and drop it here"* — con selector
  de modelo (**v5.5**). Consume créditos: confirmá antes.
- `Add Track Effects` para la cadena del track.

## Export → Multitrack (los stems)

`Export` arriba a la derecha, tres opciones:

| Opción | Qué hace |
|---|---|
| `Full Song` | mezcla completa |
| `Selected Time Range` | solo el rango marcado |
| **`Multitrack`** | **zip con un WAV por track** |

`Multitrack` es la vía oficial. No hay nada que rodear.

### Qué esperar

- **Tarda y pesa.** Un proyecto de ~3 min dio **421 MB**. La descarga aparece
  como `.crdownload` y crece por un par de minutos: **esperá con paciencia**, no
  vuelvas a apretar Export ni recargues.
- **PCM float32, 48 kHz, estéreo.** Sin pérdida.
- Todos los archivos pesan **exactamente lo mismo**: están alineados desde 0.
- Nombres con prefijo de pista: `0 <canción>.wav`, `1 Vocals.wav`,
  `2 Backing Vocals.wav`, `3 Drums.wav`, `4 Bass.wav`, `6 Guitar.wav`,
  `7 Synth.wav`.

Hay además un **"Bulk-export presets"** para dejar presets configurados.

### Después de bajar

Verificá antes de cantar victoria:

1. `suno_inspect_multitrack` con la ruta del zip — tracks, tamaños, alineación
   y stems faltantes, sin extraer nada.
2. `suno_verify_stem` sobre el bass extraído: debe dar **dominancia grave**
   (en una medición real: 17,3 dB). Las voces, dominancia aguda.

Nunca "verifiques" reproduciendo.

## Comparación con Flow Music

| | Flow Music | Suno Studio |
|---|---|---|
| Stems | 4 | 7 |
| Formato | m4a AAC | WAV float32 48 kHz |
| Bass | bloqueado por la vía oficial | incluido |
| Separación | hay que pedirla | automática al cargar |
| Edición | no hay | DAW con efectos y generación por track |

Para trabajar con stems, Suno es netamente superior. Si el usuario tiene ambas,
recomendá Suno salvo que ya tenga el material en Flow Music.
