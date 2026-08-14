---
description: Get the stems of a Suno track via Studio (Export → Multitrack) and verify them
argument-hint: "[track or project name]"
---

# /suno:stems

Gets the stems of a Suno track using the Studio, which is the official
route and gives the best quality: 7 lossless WAV tracks, aligned.

Argument: `$ARGUMENTS` — track or project name. If empty, show what's
available and ask.

## Steps

1. **Precondition.** `suno_auth_status`. If expired, ask the user to open
   `https://suno.com/` logged in on Chrome (for browser work, that's enough).

2. **Open the Studio** in its own tab: `https://suno.com/studio`.
   Read the `suno-studio` skill before operating.

3. **Load the track.** `Edit in Studio` on the song, or the saved
   project. If the **Legacy** dialog comes up, *ask the user* whether they
   want `Studio 2.0` (creates a copy in their account) or `1.2 Legacy`
   (creates nothing). Don't choose for them.

4. **Verify it loaded**: the separated tracks should appear (Vocals,
   Backing Vocals, Drums, Bass, Guitar, Synth) with their waveforms.
   **Don't touch any play control.**

5. **Export**: `Export` → `Multitrack`.

6. **Wait.** A large zip downloads (hundreds of MB; ~421 MB for 3 min).
   Monitor the `.crdownload` by size:

   ```bash
   ls -l ~/Downloads/*.crdownload 2>/dev/null
   ```

   Don't press Export again or reload the page in the meantime.

7. **Verify without extracting everything:**

   ```
   suno_inspect_multitrack  zip_path=~/Downloads/<name>.zip
   ```

   Check `aligned: true` and `stems_missing` empty.

8. **Content check** on the bass:

   ```bash
   unzip -o -q ~/Downloads/<name>.zip "*Bass.wav" -d /tmp/suno-check
   ```

   then `suno_verify_stem` on that file: it should show **low-end
   dominance** (real reference: 17.3 dB). If it shows high-end dominance,
   something went wrong — say so.

9. **Report** the zip path, track count, format, alignment, and the
   verification result.

## Reminders

- **Never play** to verify. Measure.
- If you created a copy of the project in step 3, **tell the user** at
  the end so they can decide whether to keep it.
- Don't delete the zip or the user's prior files on your own.
