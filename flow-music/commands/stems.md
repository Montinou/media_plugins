---
description: Download the stems of a Flow Music track, bass included, and verify them
argument-hint: "[title or source_clip_id] [optional destination folder]"
---

# /flowmusic:stems

Downloads the four stems (`vocals`, `drums`, `bass`, `other`) of a track and
verifies each file contains what it claims to.

Arguments: `$ARGUMENTS` — title (or part of it) or `source_clip_id`, and
optionally the destination folder. If empty, list and ask.

## Steps

1. **Precondition.** `flowmusic_auth_status`. If it isn't met, run
   `/flowmusic:auth` and stop here.

2. **Find the track.** `flowmusic_list_stems` lists the ones that already
   have stems.

   - No argument → show the list and ask which one.
   - Argument given that doesn't show up → say it clearly: the track exists
     but **doesn't have stems yet**, and you need to run **Split stems** on
     the web (`https://www.flowmusic.app/`, clip's `···` menu → *Split
     stems*, ~30 s). The MCP doesn't trigger that.
   - Ambiguous → show the candidates and ask.

3. **Show before downloading.** `flowmusic_stem_urls` with the chosen track.
   Confirm the destination with the user if it isn't `~/Downloads`.

4. **Download.** `flowmusic_download_stems`. They go sequentially and spaced
   out: don't parallelize or retry quickly if one fails.

5. **Verify.** Don't trust the file name:

   ```bash
   cd <destination folder>
   for f in *_bass.m4a *_drums.m4a *_vocals.m4a *_other.m4a; do
     [ -f "$f" ] || continue
     lo=$(ffmpeg -hide_banner -i "$f" -af "lowpass=f=250,astats=measure_perchannel=none" -f null - 2>&1 | grep "RMS level" | head -1 | awk '{print $NF}')
     hi=$(ffmpeg -hide_banner -i "$f" -af "highpass=f=250,astats=measure_perchannel=none" -f null - 2>&1 | grep "RMS level" | head -1 | awk '{print $NF}')
     printf "%-30s <250Hz %9s  >250Hz %9s\n" "$f" "$lo" "$hi"
   done
   ```

   Expected: **bass** with low end dominating ~14 dB and **drums** ~10 dB;
   **vocals** and **other** the other way around. If the bass doesn't
   dominate in low end, say so — something went wrong.

6. **Report** paths, sizes, and the verification result. If any stem was
   missing, name it explicitly instead of letting it slide.

## Reminders

- **Measure to check**, don't go by impression — step 5 is the check.
- If the bass fails with 403 through the bucket route, **stop**: don't look
  for another route.
- ffmpeg is required for step 5; if it isn't available, say so and deliver
  the files anyway, noting they went unverified.
