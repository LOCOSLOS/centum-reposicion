# Validación de la ingesta de ventas v2

Fecha de validación: 22 de julio de 2026.

## Estado operativo

- La migración `supabase/migrations/001_ventas_v2_paralela.sql` fue ejecutada correctamente en Supabase.
- El workflow `Centum → Supabase: Sync Ventas Diario v2 (PARALELO)` fue importado en n8n y permanece inactivo.
- El workflow diario anterior continúa activo.
- La v2 escribe únicamente en tablas paralelas del esquema `centum_sync`.
- No se realizó todavía el corte productivo ni el backfill histórico.

Antes de una futura activación debe restaurarse la fecha dinámica del día anterior en `Inicializa Ejecucion`, conservarse `lotesEsperados: 26` y verificarse que `Genera Consultas` finalice con `return consultas;`.

## Prueba controlada de una combinación

Se probó el 17 de julio de 2026 para:

- división `2`, `Endron Prueba`;
- sucursal `6455`, `01`;
- un único lote.

Resultado de la API:

- 5 cabeceras recibidas;
- 50 líneas recibidas.

Comparación sobre comprobantes con líneas:

| Métrica | v1 | v2 |
|---|---:|---:|
| Comprobantes | 4 | 4 |
| Líneas | 50 | 50 |
| Unidades vendidas | 572 | 572 |
| Unidades devueltas | 0 | 0 |
| Unidades netas | 572 | 572 |

La quinta cabecera recibida no contenía líneas. La diferencia entre cabeceras procesadas y comprobantes observables en `ventas_items_v2` es esperable para esa respuesta.

La misma combinación se ejecutó nuevamente. El total permaneció en 5 cabeceras y 50 líneas, por lo que la carga resultó idempotente.

## Prueba completa de las 26 consultas

La ejecución manual `1808` procesó las 13 sucursales con su división compartida y propia para el 17 de julio de 2026.

- estado: `completada`;
- lotes esperados: 26;
- lotes procesados: 26;
- cabeceras procesadas: 385;
- líneas procesadas: 792;
- duración aproximada: 1 minuto y 20 segundos;
- mensaje de error: ninguno.

La comparación por división y sucursal cubrió 22 combinaciones con movimientos. Siete presentaron diferencias entre la tabla anterior y la v2:

| Métrica | v1 | v2 | Diferencia v2 - v1 |
|---|---:|---:|---:|
| Líneas | 778 | 792 | 14 |
| Unidades vendidas | 1.270 | 1.283 | 13 |
| Unidades devueltas | 45 | 46 | 1 |
| Unidades netas | 1.225 | 1.237 | 12 |

Las diferencias se distribuyeron en:

- `05 - Local de Monroe`: 1 línea positiva;
- `16 - Local de Salguero`: 2 líneas positivas;
- `17 - Local de Boedo`: 1 línea positiva;
- `25 - Local Beltran`: 2 líneas positivas;
- `11 - Local de Gallardo`: 1 línea positiva;
- `20 - Local Membrillar`: 3 líneas positivas;
- `18 - E-Commerce`: 3 líneas positivas y 1 línea negativa.

## Causa confirmada

Se encontraron 14 casos en los que un mismo `id_articulo` aparece dos veces dentro del mismo `id_venta`. Cada caso contiene dos posiciones originales diferentes y cantidades legítimas:

- 13 casos con cantidades `[1, 1]`;
- 1 nota de crédito con cantidades `[-1, -1]`.

Esto explica exactamente las 14 líneas, las 13 unidades vendidas y la unidad devuelta que existen en v2 pero no en v1.

La ingesta anterior utilizaba:

```sql
on conflict (id_venta, id_articulo) do update
```

Por ese motivo, la segunda aparición del artículo reemplazaba a la primera. La auditoría inicial informaba cero repeticiones porque consultaba una tabla donde las repeticiones ya habían sido colapsadas durante la ingesta. La v2 conserva las líneas mediante la clave:

```text
id_division + id_sucursal + id_venta + linea_ordinal
```

La diferencia no es una duplicación generada por la v2: es información legítima que la tabla anterior perdía.

## Incidencias de la prueba

1. La primera versión de `ingestar_lote_ventas_v2` tenía una referencia ambigua a las columnas `comprobantes` y `lineas`. Se corrigió calificando las columnas con el alias de `ventas_lotes_v2`. La corrección se publicó en `main`.
2. Las ejecuciones manuales `1803` y `1807` quedaron en estado `iniciada` por fallos anteriores a la finalización. No contienen una carga parcial exitosa y deben marcarse como `con_error`, sin eliminarlas, para conservar la auditoría.

## Decisión y próximos pasos

La v2 superó las pruebas de ingesta, separación por sucursal, idempotencia y preservación de líneas repetidas. Sin embargo, no debe activarse todavía porque las vistas actuales consumen `public.ventas_items`, mientras la v2 escribe en `centum_sync.ventas_items_v2`.

Antes del corte productivo se debe:

1. restaurar y verificar la configuración diaria del workflow v2;
2. identificar todos los consumidores de `public.ventas_raw` y `public.ventas_items`;
3. adaptar las vistas del proyecto para consumir la fuente canónica v2;
4. preparar un backfill histórico controlado y medido, evitando ejecutar cientos de llamadas sin límites;
5. reconciliar varios días y todas las sucursales;
6. desactivar el workflow anterior;
7. activar la v2 antes de la siguiente ejecución de las 02:00;
8. conservar el workflow anterior inactivo como mecanismo de reversión.

Las consultas reutilizables de validación están en `supabase/audits/002_validacion_ventas_v2.sql`.

