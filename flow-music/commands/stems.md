---
description: Bajar los stems de un tema de Flow Music, bass incluido, y verificarlos
argument-hint: "[título o source_clip_id] [carpeta destino opcional]"
---

# /flowmusic:stems

Baja los cuatro stems (`vocals`, `drums`, `bass`, `other`) de un tema y verifica
que cada archivo contenga lo que dice.

Argumentos: `$ARGUMENTS` — título (o parte) o `source_clip_id`, y opcionalmente
la carpeta destino. Si viene vacío, listá y preguntá.

## Pasos

1. **Precondición.** `flowmusic_auth_status`. Si no se cumple, ejecutá
   `/flowmusic:auth` y frená acá.

2. **Ubicá el tema.** `flowmusic_list_stems` lista los que ya tienen stems.

   - Sin argumento → mostrá la lista y preguntá cuál.
   - Con argumento que no aparece → decilo claro: el tema existe pero **no tiene
     stems todavía**, y hay que correr **Split stems** en la web
     (`https://www.flowmusic.app/`, menú `···` del clip → *Split stems*, ~30 s).
     Eso el MCP no lo dispara.
   - Ambiguo → mostrá los candidatos y preguntá.

3. **Mostrá antes de bajar.** `flowmusic_stem_urls` con el tema elegido.
   Confirmá con el usuario el destino si no es `~/Downloads`.

4. **Bajá.** `flowmusic_download_stems`. Van secuenciales y espaciadas: no
   paralelices ni reintentes rápido si una falla.

5. **Verificá.** No confíes en el nombre del archivo:

   ```bash
   cd <carpeta destino>
   for f in *_bass.m4a *_drums.m4a *_vocals.m4a *_other.m4a; do
     [ -f "$f" ] || continue
     lo=$(ffmpeg -hide_banner -i "$f" -af "lowpass=f=250,astats=measure_perchannel=none" -f null - 2>&1 | grep "RMS level" | head -1 | awk '{print $NF}')
     hi=$(ffmpeg -hide_banner -i "$f" -af "highpass=f=250,astats=measure_perchannel=none" -f null - 2>&1 | grep "RMS level" | head -1 | awk '{print $NF}')
     printf "%-30s <250Hz %9s  >250Hz %9s\n" "$f" "$lo" "$hi"
   done
   ```

   Esperado: **bass** con graves dominando ~14 dB y **drums** ~10 dB; **vocals**
   y **other** al revés. Si el bass no domina en graves, decilo — algo salió mal.

6. **Informá** rutas, tamaños y el resultado de la verificación. Si faltó algún
   stem, nombralo explícitamente en lugar de dejarlo pasar.

## Recordatorios

- **No reproduzcas** ninguno de los archivos para "chequear".
- Si el bass falla con 403 por la vía del bucket, **pará**: no busques otra ruta.
- ffmpeg es necesario para el paso 5; si no está, informalo y entregá igual los
  archivos, aclarando que quedaron sin verificar.
