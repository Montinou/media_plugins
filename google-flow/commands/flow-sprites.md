---
description: Generar grillas de sprites en 8 direcciones con el AERTHOS Sprite Forge
argument-hint: [facción o descripción de lo que se necesita]
---

Generá sprites de 8 direcciones con el AERTHOS Sprite Forge
(`00000000-0000-0000-0000-000000000000`).

Pedido del usuario: $ARGUMENTS

Seguí este orden:

1. Si el pedido no nombra facciones y acciones concretas, mirá los valores
   válidos con `flow_get_applet_code` sobre ese appletId y proponé una matriz
   antes de generar.
2. Armá la receta y verificala con `flow_dryrun_recipe`. Costo cero.
3. Corré `flow_batch_generate` con `limit: 2` y mostrale al usuario el
   resultado antes de lanzar la tanda completa.
4. Recién con su visto bueno, corré el batch entero.
5. Al terminar, ofrecé `flow_upscale_local` con `nearest` factor 2.

Reportá siempre el costo en créditos que devuelven las tools. Si da distinto de
cero, decilo explícitamente antes de seguir generando.
