# Revisión del workflow diario de ventas

Última actualización: 22 de julio de 2026.

Workflow revisado: `Centum → Postgres/Supabase: Sync Ventas Diario`.

## Funcionamiento confirmado

- Se ejecuta diariamente a las 02:00 ART y consulta el día anterior.
- Recorre 13 sucursales.
- Para cada sucursal genera una llamada a la división compartida `2` (`Endron Prueba`) y otra a su división propia (`1`, `3` o `6`).
- Cada llamada envía `IdSucursal` e `IdDivisionEmpresaGrupoEconomico` a Centum.
- El nodo `Normaliza Token` conserva la sucursal, división y fechas del elemento actual del loop.
- Las ventas devueltas se guardan en `public.ventas_raw` y sus líneas en `public.ventas_items`.
- No existe un valor predeterminado `6455/01` fuera de que esa sucursal aparece primero en la lista.

## Validación de la sucursal 01

La concentración observada en `Endron Prueba / 01` es compatible con ventas mayoristas reales:

- 28 de mayo: 858 unidades en 2 comprobantes;
- 17 de julio: 572 unidades en 4 comprobantes;
- 14 de julio: 320 unidades en 2 comprobantes.

No existe evidencia de que el workflow esté agrupando las demás sucursales dentro de `01`. La división compartida aparece separada en 11 sucursales con movimientos.

## Riesgos preventivos pendientes

Estos puntos no prueban que los datos actuales sean incorrectos, pero deben resolverse antes del backfill histórico:

1. La sucursal y la división guardadas provienen del elemento consultado; no se contrastan contra campos de la venta devuelta por Centum.
2. `ventas_raw` utiliza `ON CONFLICT (id_venta)` y no guarda `id_division`.
3. `ventas_items` utiliza `ON CONFLICT (id_venta, id_articulo)`. La validación v2 confirmó que esta clave ya provoca pérdida de información: el 17 de julio de 2026 sobrescribió 14 segundas líneas legítimas del mismo artículo dentro de un comprobante, equivalentes a 13 unidades vendidas y una devuelta.
4. El workflow genera una sentencia SQL por cabecera y por línea, lo que puede resultar lento durante una carga histórica grande.
5. Las primeras 1.199 líneas, correspondientes al 25 y 26 de mayo, no tienen sucursal y no pueden recuperarla desde la cabecera.

## Reglas comerciales confirmadas

- `Endron Prueba` contiene ventas reales y debe incluirse.
- El SKU `Envio` representa un servicio: se conserva en ventas pero debe excluirse de reposición.
- Las prendas de segunda selección permanecen incluidas por el momento.

## Ajuste implementado en paralelo

Antes de cargar 12 o 24 meses de histórico, se preparó una segunda versión del workflow y una migración de Supabase que:

- guarden explícitamente `id_division`;
- registren un identificador de ejecución;
- definan una clave estable para cabeceras y líneas;
- permitan cargas masivas idempotentes;
- conserven las respuestas originales para auditoría;
- se prueben en paralelo sin alterar el workflow activo.

La versión paralela fue instalada y validada manualmente el 22 de julio de 2026. Los resultados, incluida la causa confirmada de las líneas perdidas por la clave anterior, se encuentran en [`VALIDACION_INGESTA_V2_2026-07-22.md`](VALIDACION_INGESTA_V2_2026-07-22.md).

