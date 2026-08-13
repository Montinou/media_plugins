---
description: Estado de la sesión de Google Labs Flow, créditos y applets propios
---

Revisá el estado del puente a Google Labs Flow y reportá en pocas líneas:

1. Llamá a `flow_session_status` — usuario, vencimiento de la sesión y créditos.
2. Llamá a `flow_list_applets` con `mine_only: true` — cuántas herramientas
   propias hay y cuáles se tocaron más recientemente.

Si el paso 1 falla con error de autenticación, no sigas: decile al usuario que
la cookie venció y que hay que reexportar `labs.google.cookies.json` desde el
navegador a la raíz del repo.

No generes nada ni corras batches; esto es sólo un chequeo.
