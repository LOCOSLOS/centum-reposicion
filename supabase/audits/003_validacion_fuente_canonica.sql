-- Validación posterior a instalar la fuente canónica transitoria.
-- Todas las consultas son de solo lectura.

-- 1. Cantidad de líneas por fuente y fecha.
select
  fecha_comprobante,
  fuente,
  count(*) as lineas,
  sum(cantidad) as unidades_netas
from centum_sync.vw_ventas_items_canonica
group by fecha_comprobante, fuente
order by fecha_comprobante desc, fuente;

-- 2. No debe quedar ninguna línea v1 dentro de una cobertura v2 procesada.
select
  c.fecha_comprobante,
  c.id_division,
  c.id_sucursal,
  count(*) as lineas_v1_solapadas
from centum_sync.vw_ventas_items_canonica c
where c.fuente = 'v1'
  and exists (
    select 1
    from centum_sync.ventas_lotes_v2 l
    where l.estado = 'procesado'
      and l.id_division = c.id_division
      and l.id_sucursal = c.id_sucursal
      and c.fecha_comprobante between l.fecha_desde and l.fecha_hasta
  )
group by c.fecha_comprobante, c.id_division, c.id_sucursal
order by c.fecha_comprobante, c.id_division, c.id_sucursal;

-- 3. Las líneas v2 confirmadas deben coincidir con las visibles en la fuente.
with v2_confirmada as (
  select count(*) as lineas
  from centum_sync.ventas_items_v2 i
  where exists (
    select 1
    from centum_sync.ventas_lotes_v2 l
    where l.estado = 'procesado'
      and l.id_ejecucion = i.id_ejecucion_ultima
      and l.id_division = i.id_division
      and l.id_sucursal = i.id_sucursal
      and i.fecha_comprobante between l.fecha_desde and l.fecha_hasta
  )
),
canonica_v2 as (
  select count(*) as lineas
  from centum_sync.vw_ventas_items_canonica
  where fuente = 'v2'
)
select
  v2_confirmada.lineas as lineas_v2_confirmadas,
  canonica_v2.lineas as lineas_v2_canonicas,
  canonica_v2.lineas - v2_confirmada.lineas as diferencia
from v2_confirmada
cross join canonica_v2;

-- 4. El histórico sin sucursal debe conservarse íntegro desde v1.
with v1 as (
  select count(*) as lineas, sum(cantidad) as unidades_netas
  from public.ventas_items
  where id_sucursal is null
),
canonica as (
  select count(*) as lineas, sum(cantidad) as unidades_netas
  from centum_sync.vw_ventas_items_canonica
  where id_sucursal is null
)
select
  v1.lineas as lineas_v1,
  canonica.lineas as lineas_canonicas,
  canonica.lineas - v1.lineas as diferencia_lineas,
  v1.unidades_netas as unidades_v1,
  canonica.unidades_netas as unidades_canonicas,
  canonica.unidades_netas - v1.unidades_netas as diferencia_unidades
from v1
cross join canonica;

-- 5. Totales de las vistas operativas después del cambio de fuente.
select
  count(*) as filas_diarias,
  sum(unidades_vendidas) as unidades_vendidas,
  sum(unidades_devueltas) as unidades_devueltas,
  sum(unidades_netas) as unidades_netas,
  min(fecha_comprobante) as fecha_minima,
  max(fecha_comprobante) as fecha_maxima
from public.vw_ventas_diarias_articulo_sucursal;
