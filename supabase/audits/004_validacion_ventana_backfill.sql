-- Validación de una ventana de backfill v2.
-- Ajustar únicamente las dos fechas antes de ejecutar.

with parametros as (
  select
    date '2026-07-21' as fecha_desde,
    date '2026-07-22' as fecha_hasta
),
v1 as (
  select
    i.fecha_comprobante,
    case i.sociedad
      when 'Endron Empresa' then 1::bigint
      when 'Endron Prueba' then 2::bigint
      when 'Nich Empresa' then 3::bigint
      when 'Capay' then 6::bigint
    end as id_division,
    i.id_sucursal::bigint as id_sucursal,
    count(*) as lineas,
    coalesce(sum(i.cantidad) filter (where i.cantidad > 0), 0) as vendidas,
    coalesce(abs(sum(i.cantidad) filter (where i.cantidad < 0)), 0) as devueltas,
    coalesce(sum(i.cantidad), 0) as netas
  from public.ventas_items i
  cross join parametros p
  where i.fecha_comprobante between p.fecha_desde and p.fecha_hasta
    and i.id_sucursal is not null
  group by i.fecha_comprobante, i.sociedad, i.id_sucursal
),
v2 as (
  select
    i.fecha_comprobante,
    i.id_division,
    i.id_sucursal,
    count(*) as lineas,
    coalesce(sum(i.cantidad) filter (where i.cantidad > 0), 0) as vendidas,
    coalesce(abs(sum(i.cantidad) filter (where i.cantidad < 0)), 0) as devueltas,
    coalesce(sum(i.cantidad), 0) as netas
  from centum_sync.ventas_items_v2 i
  cross join parametros p
  where i.fecha_comprobante between p.fecha_desde and p.fecha_hasta
    and exists (
      select 1
      from centum_sync.ventas_lotes_v2 l
      where l.estado = 'procesado'
        and l.id_ejecucion = i.id_ejecucion_ultima
        and l.id_division = i.id_division
        and l.id_sucursal = i.id_sucursal
        and i.fecha_comprobante between l.fecha_desde and l.fecha_hasta
    )
  group by i.fecha_comprobante, i.id_division, i.id_sucursal
)
select
  coalesce(v1.fecha_comprobante, v2.fecha_comprobante) as fecha_comprobante,
  coalesce(v1.id_division, v2.id_division) as id_division,
  coalesce(v1.id_sucursal, v2.id_sucursal) as id_sucursal,
  coalesce(v1.lineas, 0) as lineas_v1,
  coalesce(v2.lineas, 0) as lineas_v2,
  coalesce(v2.lineas, 0) - coalesce(v1.lineas, 0) as diferencia_lineas,
  coalesce(v1.vendidas, 0) as vendidas_v1,
  coalesce(v2.vendidas, 0) as vendidas_v2,
  coalesce(v2.vendidas, 0) - coalesce(v1.vendidas, 0) as diferencia_vendidas,
  coalesce(v1.devueltas, 0) as devueltas_v1,
  coalesce(v2.devueltas, 0) as devueltas_v2,
  coalesce(v2.devueltas, 0) - coalesce(v1.devueltas, 0) as diferencia_devueltas,
  coalesce(v1.netas, 0) as netas_v1,
  coalesce(v2.netas, 0) as netas_v2,
  coalesce(v2.netas, 0) - coalesce(v1.netas, 0) as diferencia_netas
from v1
full outer join v2
  using (fecha_comprobante, id_division, id_sucursal)
where coalesce(v1.lineas, 0) <> coalesce(v2.lineas, 0)
   or coalesce(v1.vendidas, 0) <> coalesce(v2.vendidas, 0)
   or coalesce(v1.devueltas, 0) <> coalesce(v2.devueltas, 0)
   or coalesce(v1.netas, 0) <> coalesce(v2.netas, 0)
order by fecha_comprobante, id_division, id_sucursal;
