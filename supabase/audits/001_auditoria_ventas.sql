-- Auditoría inicial de ventas_items y ventas_raw.
-- Todas las consultas son de solo lectura.
-- Revisar los resultados antes de crear restricciones o cargar el histórico.

-- 1. Volumen y cobertura general.
select
  'ventas_raw' as tabla,
  count(*) as filas,
  min(fecha_comprobante) as fecha_desde,
  max(fecha_comprobante) as fecha_hasta,
  count(distinct sociedad) as sociedades,
  count(distinct id_sucursal) as sucursales
from public.ventas_raw
union all
select
  'ventas_items' as tabla,
  count(*) as filas,
  min(fecha_comprobante) as fecha_desde,
  max(fecha_comprobante) as fecha_hasta,
  count(distinct sociedad) as sociedades,
  count(distinct id_sucursal) as sucursales
from public.ventas_items;

-- 2. Nulos en campos necesarios para consolidar las ventas.
select
  count(*) as filas,
  count(*) filter (where id_venta is null or btrim(id_venta) = '') as sin_id_venta,
  count(*) filter (where id_articulo is null) as sin_id_articulo,
  count(*) filter (where fecha_comprobante is null) as sin_fecha,
  count(*) filter (where sociedad is null or btrim(sociedad) = '') as sin_sociedad,
  count(*) filter (where id_sucursal is null) as sin_sucursal,
  count(*) filter (where codigo is null or btrim(codigo) = '') as sin_codigo,
  count(*) filter (where cantidad is null) as sin_cantidad,
  count(*) filter (where precio is null) as sin_precio,
  count(*) filter (where precio_neto is null) as sin_precio_neto,
  count(*) filter (where costo_reposicion is null) as sin_costo_reposicion
from public.ventas_items;

-- 3. Duplicados del identificador interno. El resultado esperado es cero filas.
select id, count(*) as repeticiones
from public.ventas_items
group by id
having count(*) > 1
order by repeticiones desc, id
limit 100;

-- 4. Posibles comprobantes duplicados en ventas_raw.
-- La clave propuesta debe validarse con estos resultados.
select
  sociedad,
  id_sucursal,
  id_venta,
  count(*) as repeticiones,
  min(creado_en) as primera_carga,
  max(actualizado_en) as ultima_actualizacion
from public.ventas_raw
group by sociedad, id_sucursal, id_venta
having count(*) > 1
order by repeticiones desc, sociedad, id_sucursal, id_venta
limit 200;

-- 5. Repetición de artículo dentro del mismo comprobante.
-- No implica necesariamente un error: puede representar dos renglones legítimos.
select
  sociedad,
  id_sucursal,
  id_venta,
  id_articulo,
  count(*) as lineas,
  sum(cantidad) as cantidad_total,
  min(precio) as precio_minimo,
  max(precio) as precio_maximo,
  min(porcentaje_descuento) as descuento_minimo,
  max(porcentaje_descuento) as descuento_maximo
from public.ventas_items
group by sociedad, id_sucursal, id_venta, id_articulo
having count(*) > 1
order by lineas desc, sociedad, id_sucursal, id_venta
limit 200;

-- 6. Filas exactamente repetidas en sus campos comerciales.
select
  sociedad,
  id_sucursal,
  id_venta,
  id_articulo,
  fecha_comprobante,
  codigo,
  cantidad,
  precio,
  precio_neto,
  porcentaje_descuento,
  subtotal,
  total,
  count(*) as repeticiones
from public.ventas_items
group by
  sociedad,
  id_sucursal,
  id_venta,
  id_articulo,
  fecha_comprobante,
  codigo,
  cantidad,
  precio,
  precio_neto,
  porcentaje_descuento,
  subtotal,
  total
having count(*) > 1
order by repeticiones desc
limit 200;

-- 7. Ítems que no encuentran su cabecera.
select
  i.sociedad,
  i.id_sucursal,
  i.id_venta,
  count(*) as lineas
from public.ventas_items i
where not exists (
  select 1
  from public.ventas_raw r
  where r.id_venta = i.id_venta
    and r.sociedad is not distinct from i.sociedad
    and r.id_sucursal is not distinct from i.id_sucursal
)
group by i.sociedad, i.id_sucursal, i.id_venta
order by lineas desc
limit 200;

-- 8. Cabeceras sin ítems.
select
  r.sociedad,
  r.id_sucursal,
  r.id_venta,
  r.tipo_comprobante,
  r.numero_comprobante,
  r.fecha_comprobante
from public.ventas_raw r
where not exists (
  select 1
  from public.ventas_items i
  where i.id_venta = r.id_venta
    and i.sociedad is not distinct from r.sociedad
    and i.id_sucursal is not distinct from r.id_sucursal
)
order by r.fecha_comprobante desc nulls last
limit 200;

-- 9. Cobertura temporal por sociedad y sucursal.
select
  sociedad,
  id_sucursal,
  max(sucursal_nombre) as sucursal_nombre,
  min(fecha_comprobante) as fecha_desde,
  max(fecha_comprobante) as fecha_hasta,
  count(distinct fecha_comprobante) as dias_con_registros,
  (max(fecha_comprobante) - min(fecha_comprobante) + 1) as dias_calendario,
  (max(fecha_comprobante) - min(fecha_comprobante) + 1)
    - count(distinct fecha_comprobante) as dias_sin_registros
from public.ventas_items
where fecha_comprobante is not null
group by sociedad, id_sucursal
order by sociedad, id_sucursal;

-- 10. Tipos de comprobante disponibles en la cabecera.
select
  coalesce(tipo_comprobante, '<SIN TIPO>') as tipo_comprobante,
  count(*) as comprobantes,
  min(fecha_comprobante) as fecha_desde,
  max(fecha_comprobante) as fecha_hasta,
  sum(importe_total) as importe_total,
  sum(importe_neto) as importe_neto
from public.ventas_raw
group by coalesce(tipo_comprobante, '<SIN TIPO>')
order by comprobantes desc;

-- 11. Distribución de signos. Ayuda a identificar devoluciones y anulaciones.
select
  count(*) filter (where cantidad > 0) as lineas_positivas,
  count(*) filter (where cantidad = 0) as lineas_en_cero,
  count(*) filter (where cantidad < 0) as lineas_negativas,
  min(cantidad) as cantidad_minima,
  max(cantidad) as cantidad_maxima,
  count(*) filter (where precio < 0) as precios_negativos,
  count(*) filter (where precio_neto < 0) as precios_netos_negativos,
  count(*) filter (where costo_reposicion < 0) as costos_negativos,
  count(*) filter (where total < 0) as totales_negativos
from public.ventas_items;

-- 12. Muestra de cantidades negativas con el comprobante asociado.
select
  i.id,
  i.sociedad,
  i.id_sucursal,
  i.id_venta,
  i.id_articulo,
  i.codigo,
  i.nombre,
  i.cantidad,
  i.precio,
  i.total,
  r.tipo_comprobante,
  r.numero_comprobante,
  i.fecha_comprobante
from public.ventas_items i
left join lateral (
  select r.tipo_comprobante, r.numero_comprobante
  from public.ventas_raw r
  where r.id_venta = i.id_venta
    and r.sociedad is not distinct from i.sociedad
    and r.id_sucursal is not distinct from i.id_sucursal
  order by r.actualizado_en desc nulls last, r.id desc
  limit 1
) r on true
where i.cantidad < 0 or i.total < 0
order by i.fecha_comprobante desc nulls last, i.id desc
limit 200;

-- 13. Comparación entre el total de cabecera y la suma de líneas.
-- Diferencias pueden ser válidas por redondeos o impuestos; deben interpretarse
-- con ejemplos reales antes de fijar una tolerancia.
with raw_unica as (
  select distinct on (sociedad, id_sucursal, id_venta)
    sociedad,
    id_sucursal,
    id_venta,
    numero_comprobante,
    tipo_comprobante,
    importe_total,
    importe_neto
  from public.ventas_raw
  order by
    sociedad,
    id_sucursal,
    id_venta,
    actualizado_en desc nulls last,
    id desc
),
items_por_venta as (
  select
    sociedad,
    id_sucursal,
    id_venta,
    count(*) as lineas,
    sum(subtotal) as subtotal_lineas,
    sum(total) as total_lineas
  from public.ventas_items
  group by sociedad, id_sucursal, id_venta
)
select
  r.sociedad,
  r.id_sucursal,
  r.id_venta,
  r.tipo_comprobante,
  r.numero_comprobante,
  i.lineas,
  r.importe_total as total_cabecera,
  i.total_lineas,
  i.total_lineas - r.importe_total as diferencia_total,
  r.importe_neto as neto_cabecera,
  i.subtotal_lineas,
  i.subtotal_lineas - r.importe_neto as diferencia_neto
from raw_unica r
join items_por_venta i
  on i.id_venta = r.id_venta
  and i.sociedad is not distinct from r.sociedad
  and i.id_sucursal is not distinct from r.id_sucursal
where
  i.total_lineas is distinct from r.importe_total
  or i.subtotal_lineas is distinct from r.importe_neto
order by abs(coalesce(i.total_lineas - r.importe_total, 0)) desc
limit 200;

-- 14. Unicidad confirmatoria del maestro de artículos.
select
  count(*) as filas,
  count(distinct id_articulo) as idarticulos_unicos,
  count(distinct sku) as sku_unicos,
  count(*) filter (where id_articulo is null) as sin_idarticulo,
  count(*) filter (where sku is null or btrim(sku) = '') as sin_sku
from centum_sync.maestro_articulos;

-- 15. Duplicados de las claves declaradas como únicas en el maestro.
select 'id_articulo' as campo, id_articulo::text as valor, count(*) as repeticiones
from centum_sync.maestro_articulos
group by id_articulo
having count(*) > 1
union all
select 'sku' as campo, sku as valor, count(*) as repeticiones
from centum_sync.maestro_articulos
group by sku
having count(*) > 1
order by repeticiones desc, campo, valor
limit 200;

-- 16. Ítems de venta que no encuentran su artículo en el maestro.
-- El resultado esperado, según la validación funcional, es cero filas.
select
  i.id_articulo,
  max(i.codigo) as codigo,
  max(i.nombre) as nombre,
  count(*) as lineas_de_venta
from public.ventas_items i
left join centum_sync.maestro_articulos m
  on m.id_articulo = i.id_articulo::bigint
where i.id_articulo is not null
  and m.id_articulo is null
group by i.id_articulo
order by lineas_de_venta desc
limit 200;

-- 17. Cobertura del patrón utilizado para separar color y talle.
select
  count(*) as articulos,
  count(*) filter (
    where descripcion like '% C:% T:%'
  ) as patron_completo,
  count(*) filter (
    where descripcion is null or btrim(descripcion) = ''
  ) as sin_descripcion,
  count(*) filter (
    where descripcion is not null
      and descripcion not like '% C:%'
  ) as sin_marcador_color,
  count(*) filter (
    where descripcion is not null
      and descripcion not like '% T:%'
  ) as sin_marcador_talle,
  count(*) filter (
    where descripcion ~ '(Ã|Â|�)'
      or subrubro ~ '(Ã|Â|�)'
      or grupo_articulo ~ '(Ã|Â|�)'
  ) as posible_codificacion_incorrecta
from centum_sync.maestro_articulos;

-- 18. Muestra de descripciones que necesitan revisión manual.
select
  id_articulo,
  sku,
  descripcion,
  grupo_articulo,
  rubro,
  subrubro,
  case
    when descripcion is null or btrim(descripcion) = '' then 'sin_descripcion'
    when descripcion not like '% C:%' then 'sin_color'
    when descripcion not like '% T:%' then 'sin_talle'
    when descripcion ~ '(Ã|Â|�)'
      or subrubro ~ '(Ã|Â|�)'
      or grupo_articulo ~ '(Ã|Â|�)' then 'posible_codificacion_incorrecta'
    else 'revisar'
  end as motivo
from centum_sync.maestro_articulos
where descripcion is null
  or descripcion not like '% C:% T:%'
  or descripcion ~ '(Ã|Â|�)'
  or subrubro ~ '(Ã|Â|�)'
  or grupo_articulo ~ '(Ã|Â|�)'
order by updated_at desc, id_articulo
limit 200;

