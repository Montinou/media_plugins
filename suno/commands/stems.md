---
description: Sacar los stems de un tema de Suno vía Studio (Export → Multitrack) y verificarlos
argument-hint: "[nombre del tema o proyecto]"
---

# /suno:stems

Obtiene los stems de un tema de Suno usando el Studio, que es la vía oficial y
la que da mejor calidad: 7 pistas en WAV sin pérdida, alineadas.

Argumento: `$ARGUMENTS` — nombre del tema o del proyecto. Si viene vacío,
mostrá lo que haya y preguntá.

## Pasos

1. **Precondición.** `suno_auth_status`. Si venció, pedile al usuario que abra
   `https://suno.com/` logueado en Chrome (para navegador alcanza con eso).

2. **Abrí el Studio** en una pestaña propia: `https://suno.com/studio`.
   Leé la skill `suno-studio` antes de operar.

3. **Cargá el tema.** `Edit in Studio` sobre la canción, o el proyecto guardado.
   Si sale el diálogo de **Legacy**, *preguntale al usuario* si quiere
   `Studio 2.0` (crea una copia en su cuenta) o `1.2 Legacy` (no crea nada).
   No elijas por él.

4. **Verificá que cargó**: deben aparecer los tracks separados (Vocals, Backing
   Vocals, Drums, Bass, Guitar, Synth) con sus waveforms.
   **No toques ningún play.**

5. **Exportá**: `Export` → `Multitrack`.

6. **Esperá.** Baja un zip grande (cientos de MB; ~421 MB para 3 min). Monitoreá
   el `.crdownload` por tamaño:

   ```bash
   ls -l ~/Downloads/*.crdownload 2>/dev/null
   ```

   No vuelvas a apretar Export ni recargues la página mientras tanto.

7. **Verificá sin extraer todo:**

   ```
   suno_inspect_multitrack  zip_path=~/Downloads/<nombre>.zip
   ```

   Chequeá `aligned: true` y `stems_missing` vacío.

8. **Control de contenido** sobre el bass:

   ```bash
   unzip -o -q ~/Downloads/<nombre>.zip "*Bass.wav" -d /tmp/suno-check
   ```

   luego `suno_verify_stem` sobre ese archivo: debe dar **dominancia grave**
   (referencia real: 17,3 dB). Si da dominancia aguda, algo salió mal — decilo.

9. **Informá** ruta del zip, cantidad de tracks, formato, alineación y el
   resultado de la verificación.

## Recordatorios

- **Nunca reproduzcas** para verificar. Medí.
- Si creaste una copia del proyecto en el paso 3, **decíselo al usuario** al
  final para que decida si la conserva.
- No borres el zip ni archivos previos del usuario por tu cuenta.
