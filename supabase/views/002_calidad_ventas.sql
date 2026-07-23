-- Resumen de líneas que no pueden asignarse a una sucursal.
-- Se conservan para totales generales y control de calidad, pero no deben
-- utilizarse en cálculos de reposición por local.

create or replace view public.vw_ventas_sin_sucursal_resumen
with (security_invoker = true)
as
select
  fecha_comprobante,
  sociedad,
  count(*) as lineas,
  coalesce(
    sum(cantidad) filter (where cantidad > 0),
    0
  ) as unidades_vendidas,
  coalesce(
    abs(sum(cantidad) filter (where cantidad < 0)),
    0
  ) as unidades_devueltas,
  sum(coalesce(cantidad, 0)) as unidades_netas,
  min(actualizado_en) as primera_actualizacion,
  max(actualizado_en) as ultima_actualizacion
from centum_sync.vw_ventas_items_canonica
where id_sucursal is null
group by fecha_comprobante, sociedad;

comment on view public.vw_ventas_sin_sucursal_resumen is
  'Líneas históricas sin sucursal recuperable, excluidas del análisis por local pero preservadas para auditoría y totales generales.';

