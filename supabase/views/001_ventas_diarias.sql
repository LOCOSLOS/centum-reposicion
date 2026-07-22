-- Vistas iniciales para el tablero de ventas.
-- No modifican las tablas de origen.
-- Las cantidades negativas se mantienen separadas hasta confirmar cómo Centum
-- representa devoluciones y anulaciones.

create or replace view public.vw_ventas_diarias_articulo_sucursal
with (security_invoker = true)
as
select
  i.fecha_comprobante,
  i.sociedad,
  i.id_sucursal,
  max(i.sucursal_nombre) as sucursal_nombre,
  i.id_articulo,
  max(coalesce(m.sku, i.codigo)) as sku,
  max(coalesce(m.descripcion, i.nombre)) as articulo_nombre,
  max(m.rubro) as rubro,
  max(m.subrubro) as subrubro,
  max(m.grupo_articulo) as grupo_articulo,
  max(m.color) as color,
  max(m.talle) as talle,
  max(m.estado_parseo_variante) as estado_parseo_variante,
  count(*) as lineas,
  count(distinct i.id_venta) as comprobantes,
  coalesce(
    sum(coalesce(i.cantidad, 0)) filter (where i.cantidad > 0),
    0
  ) as unidades_positivas,
  coalesce(
    abs(sum(coalesce(i.cantidad, 0)) filter (where i.cantidad < 0)),
    0
  ) as unidades_negativas,
  sum(coalesce(i.cantidad, 0)) as unidades_netas,
  sum(coalesce(i.subtotal, 0)) as subtotal_registrado,
  sum(coalesce(i.total, 0)) as total_registrado,
  sum(
    coalesce(i.costo_reposicion, 0) * coalesce(i.cantidad, 0)
  ) as costo_reposicion_total,
  min(i.actualizado_en) as primera_actualizacion,
  max(i.actualizado_en) as ultima_actualizacion
from public.ventas_items i
left join public.vw_maestro_articulos_normalizado m
  on m.id_articulo = i.id_articulo::bigint
where i.fecha_comprobante is not null
  and i.sociedad is not null
  and i.id_sucursal is not null
  and i.id_articulo is not null
group by
  i.fecha_comprobante,
  i.sociedad,
  i.id_sucursal,
  i.id_articulo;

comment on view public.vw_ventas_diarias_articulo_sucursal is
  'Ventas consolidadas por fecha, sociedad, sucursal y artículo. Provisional hasta validar duplicados, devoluciones y anulaciones.';

create or replace view public.vw_ventas_resumen_articulo_sucursal
with (security_invoker = true)
as
select
  sociedad,
  id_sucursal,
  max(sucursal_nombre) as sucursal_nombre,
  id_articulo,
  max(sku) as sku,
  max(articulo_nombre) as articulo_nombre,
  max(rubro) as rubro,
  max(subrubro) as subrubro,
  max(grupo_articulo) as grupo_articulo,
  max(color) as color,
  max(talle) as talle,
  max(estado_parseo_variante) as estado_parseo_variante,
  coalesce(sum(unidades_netas) filter (
    where fecha_comprobante >= current_date - 6
  ), 0) as unidades_netas_7d,
  coalesce(sum(unidades_netas) filter (
    where fecha_comprobante >= current_date - 27
  ), 0) as unidades_netas_28d,
  coalesce(sum(unidades_netas) filter (
    where fecha_comprobante >= current_date - 55
  ), 0) as unidades_netas_56d,
  coalesce(sum(total_registrado) filter (
    where fecha_comprobante >= current_date - 27
  ), 0) as venta_total_28d,
  count(distinct fecha_comprobante) filter (
    where fecha_comprobante >= current_date - 27
      and unidades_positivas > 0
  ) as dias_con_venta_28d,
  max(fecha_comprobante) filter (
    where unidades_positivas > 0
  ) as fecha_ultima_venta,
  max(ultima_actualizacion) as ultima_actualizacion
from public.vw_ventas_diarias_articulo_sucursal
group by sociedad, id_sucursal, id_articulo;

comment on view public.vw_ventas_resumen_articulo_sucursal is
  'Resumen móvil de 7, 28 y 56 días por artículo y sucursal para el tablero inicial.';

