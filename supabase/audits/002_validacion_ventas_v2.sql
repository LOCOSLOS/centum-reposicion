-- Validación reutilizable de la ingesta de ventas v2 contra la tabla anterior.
-- Cambiar solamente la fecha en el CTE parametros para revisar otro día.

-- 1. Estado de las ejecuciones recientes.
select
  id_ejecucion,
  fecha_desde,
  fecha_hasta,
  estado,
  lotes_esperados,
  lotes_procesados,
  comprobantes_procesados,
  lineas_procesadas,
  iniciada_en,
  finalizada_en,
  mensaje_error
from centum_sync.carga_ejecuciones_v2
order by iniciada_en desc
limit 10;

-- 2. Resumen de conciliación por división y sucursal.
with parametros as (
  select date '2026-07-17' as fecha
),
v1 as (
  select
    case i.sociedad
      when 'Endron Empresa' then 1
      when 'Endron Prueba' then 2
      when 'Nich Empresa' then 3
      when 'Capay' then 6
    end as id_division,
    i.id_sucursal,
    count(distinct i.id_venta) as comprobantes,
    count(*) as lineas,
    coalesce(sum(i.cantidad) filter (where i.cantidad > 0), 0) as vendidas,
    coalesce(abs(sum(i.cantidad) filter (where i.cantidad < 0)), 0) as devueltas,
    coalesce(sum(i.cantidad), 0) as netas
  from public.ventas_items i
  cross join parametros p
  where i.fecha_comprobante = p.fecha
    and i.id_sucursal is not null
  group by i.sociedad, i.id_sucursal
),
v2 as (
  select
    i.id_division,
    i.id_sucursal,
    count(distinct i.id_venta) as comprobantes,
    count(*) as lineas,
    coalesce(sum(i.cantidad) filter (where i.cantidad > 0), 0) as vendidas,
    coalesce(abs(sum(i.cantidad) filter (where i.cantidad < 0)), 0) as devueltas,
    coalesce(sum(i.cantidad), 0) as netas
  from centum_sync.ventas_items_v2 i
  cross join parametros p
  where i.fecha_comprobante = p.fecha
  group by i.id_division, i.id_sucursal
),
comparacion as (
  select
    coalesce(v1.id_division, v2.id_division) as id_division,
    coalesce(v1.id_sucursal, v2.id_sucursal) as id_sucursal,
    coalesce(v1.comprobantes, 0) as comprobantes_v1,
    coalesce(v2.comprobantes, 0) as comprobantes_v2,
    coalesce(v1.lineas, 0) as lineas_v1,
    coalesce(v2.lineas, 0) as lineas_v2,
    coalesce(v1.vendidas, 0) as vendidas_v1,
    coalesce(v2.vendidas, 0) as vendidas_v2,
    coalesce(v1.devueltas, 0) as devueltas_v1,
    coalesce(v2.devueltas, 0) as devueltas_v2,
    coalesce(v1.netas, 0) as netas_v1,
    coalesce(v2.netas, 0) as netas_v2
  from v1
  full join v2
    on v2.id_division = v1.id_division
   and v2.id_sucursal = v1.id_sucursal
)
select
  count(*) as combinaciones_comparadas,
  count(*) filter (
    where comprobantes_v1 <> comprobantes_v2
       or lineas_v1 <> lineas_v2
       or vendidas_v1 <> vendidas_v2
       or devueltas_v1 <> devueltas_v2
       or netas_v1 <> netas_v2
  ) as combinaciones_con_diferencias,
  sum(lineas_v1) as lineas_v1,
  sum(lineas_v2) as lineas_v2,
  sum(vendidas_v1) as vendidas_v1,
  sum(vendidas_v2) as vendidas_v2,
  sum(devueltas_v1) as devueltas_v1,
  sum(devueltas_v2) as devueltas_v2,
  sum(netas_v1) as netas_v1,
  sum(netas_v2) as netas_v2
from comparacion;

-- 3. Líneas repetidas legítimas dentro de un comprobante.
with parametros as (
  select date '2026-07-17' as fecha
)
select
  i.id_division,
  i.id_sucursal,
  max(i.sucursal_nombre) as sucursal,
  i.id_venta,
  i.id_articulo,
  max(i.codigo) as sku,
  count(*) as veces_en_comprobante,
  array_agg(i.linea_ordinal order by i.linea_ordinal) as ordinales,
  array_agg(i.cantidad order by i.linea_ordinal) as cantidades,
  sum(i.cantidad) as cantidad_total
from centum_sync.ventas_items_v2 i
cross join parametros p
where i.fecha_comprobante = p.fecha
group by
  i.id_division,
  i.id_sucursal,
  i.id_venta,
  i.id_articulo
having count(*) > 1
order by
  i.id_division,
  i.id_sucursal,
  i.id_venta,
  i.id_articulo;

-- 4. Ejecuciones que quedaron abiertas por una interrupción o error.
select
  id_ejecucion,
  fecha_desde,
  fecha_hasta,
  iniciada_en,
  lotes_esperados,
  lotes_procesados
from centum_sync.carga_ejecuciones_v2
where estado = 'iniciada'
order by iniciada_en;

-- Corrección puntual confirmada para las pruebas fallidas del 22/07/2026.
-- Ejecutar solamente después de revisar el SELECT anterior.
--
-- update centum_sync.carga_ejecuciones_v2
-- set estado = 'con_error',
--     finalizada_en = now(),
--     mensaje_error = 'Prueba manual interrumpida antes de completar los lotes'
-- where id_ejecucion in ('1803', '1807')
--   and estado = 'iniciada';

