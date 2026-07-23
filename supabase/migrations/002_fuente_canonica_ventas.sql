-- Fuente canónica transitoria durante el backfill de ventas v2.
-- No elimina ni modifica las tablas v1 o v2.

begin;

create or replace view centum_sync.vw_ventas_items_canonica
with (security_invoker = true)
as
with lotes_v2_procesados as (
  select distinct
    l.id_ejecucion,
    l.id_division,
    l.id_sucursal,
    l.fecha_desde,
    l.fecha_hasta
  from centum_sync.ventas_lotes_v2 l
  where l.estado = 'procesado'
),
items_v2_confirmados as (
  select
    i.id_division,
    i.id_sucursal,
    i.id_venta,
    i.linea_ordinal,
    i.id_articulo,
    i.sociedad,
    i.sucursal_nombre,
    i.fecha_comprobante,
    i.codigo,
    i.nombre,
    i.cantidad,
    i.subtotal,
    i.total,
    i.actualizado_en,
    i.id_ejecucion_ultima,
    'v2'::text as fuente
  from centum_sync.ventas_items_v2 i
  where exists (
    select 1
    from lotes_v2_procesados l
    where l.id_ejecucion = i.id_ejecucion_ultima
      and l.id_division = i.id_division
      and l.id_sucursal = i.id_sucursal
      and i.fecha_comprobante between l.fecha_desde and l.fecha_hasta
  )
),
items_v1_no_reemplazados as (
  select
    case i.sociedad
      when 'Endron Empresa' then 1::bigint
      when 'Endron Prueba' then 2::bigint
      when 'Nich Empresa' then 3::bigint
      when 'Capay' then 6::bigint
      else null::bigint
    end as id_division,
    i.id_sucursal::bigint as id_sucursal,
    i.id_venta::text as id_venta,
    null::integer as linea_ordinal,
    i.id_articulo::bigint as id_articulo,
    i.sociedad,
    i.sucursal_nombre,
    i.fecha_comprobante,
    i.codigo,
    i.nombre,
    i.cantidad,
    i.subtotal,
    i.total,
    i.actualizado_en,
    null::text as id_ejecucion_ultima,
    'v1'::text as fuente
  from public.ventas_items i
  where not exists (
    select 1
    from lotes_v2_procesados l
    where l.id_division = case i.sociedad
        when 'Endron Empresa' then 1::bigint
        when 'Endron Prueba' then 2::bigint
        when 'Nich Empresa' then 3::bigint
        when 'Capay' then 6::bigint
        else null::bigint
      end
      and l.id_sucursal = i.id_sucursal::bigint
      and i.fecha_comprobante between l.fecha_desde and l.fecha_hasta
  )
)
select * from items_v2_confirmados
union all
select * from items_v1_no_reemplazados;

comment on view centum_sync.vw_ventas_items_canonica is
  'Fuente transitoria: usa ventas v2 para lotes procesados y conserva v1 para combinaciones todavía no cubiertas por el backfill.';

commit;
