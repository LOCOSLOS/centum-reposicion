-- Auditoria por bloques de respuestas JSON de ventas v2.
-- Issue relacionado: #3.
--
-- Ejecutar bloques pequenos para no superar el timeout del SQL Editor de
-- Supabase. Cambiar fecha_desde y cantidad_meses; fecha_hasta se calcula sola
-- y nunca supera ayer en horario de Argentina.

with
parametros as (
  select
    date '2024-07-01' as fecha_desde,
    1::integer as cantidad_meses
),
ventana as (
  select
    fecha_desde,
    least(
      (
        fecha_desde
        + make_interval(months => cantidad_meses)
        - interval '1 day'
      )::date,
      (now() at time zone 'America/Argentina/Buenos_Aires')::date - 1
    ) as fecha_hasta
  from parametros
),
lotes_mes as materialized (
  select l.*
  from centum_sync.ventas_lotes_v2 l
  cross join ventana p
  where l.estado = 'procesado'
    and l.fecha_hasta >= p.fecha_desde
    and l.fecha_desde <= p.fecha_hasta
),
lotes_conteo_respuesta as (
  select
    l.id_lote,
    l.id_ejecucion,
    l.id_division,
    l.id_sucursal,
    l.fecha_desde,
    l.fecha_hasta,
    l.comprobantes as comprobantes_registrados,
    l.lineas as lineas_registradas,
    case
      when jsonb_typeof(l.respuesta #> '{Ventas,Items}') = 'array'
      then jsonb_array_length(l.respuesta #> '{Ventas,Items}')
      else 0
    end as comprobantes_respuesta,
    coalesce((
      select sum(
        case
          when jsonb_typeof(v.item -> 'VentaArticulos') = 'array'
          then jsonb_array_length(v.item -> 'VentaArticulos')
          else 0
        end
      )
      from jsonb_array_elements(
        case
          when jsonb_typeof(l.respuesta #> '{Ventas,Items}') = 'array'
          then l.respuesta #> '{Ventas,Items}'
          else '[]'::jsonb
        end
      ) as v(item)
    ), 0) as lineas_respuesta
  from lotes_mes l
),
lotes_con_diferencias as (
  select *
  from lotes_conteo_respuesta
  where comprobantes_registrados <> comprobantes_respuesta
     or lineas_registradas <> lineas_respuesta
),
ventas_en_lotes as materialized (
  select
    l.id_division,
    l.id_sucursal,
    l.id_ejecucion,
    l.id_lote,
    l.procesado_en,
    v.item ->> 'IdVenta' as id_venta,
    v.item as raw_data
  from lotes_mes l
  cross join lateral jsonb_array_elements(
    case
      when jsonb_typeof(l.respuesta #> '{Ventas,Items}') = 'array'
      then l.respuesta #> '{Ventas,Items}'
      else '[]'::jsonb
    end
  ) as v(item)
  cross join ventana p
  where nullif(v.item ->> 'IdVenta', '') is not null
    and nullif(left(v.item ->> 'FechaDocumento', 10), '')::date
      between p.fecha_desde and p.fecha_hasta
),
ventas_ultimas_respuestas as materialized (
  select distinct on (id_division, id_sucursal, id_venta)
    id_division,
    id_sucursal,
    id_ejecucion,
    id_venta,
    raw_data
  from ventas_en_lotes
  order by
    id_division,
    id_sucursal,
    id_venta,
    procesado_en desc nulls last,
    id_lote desc
),
documentos_no_autoritativos as (
  select
    v.id_division,
    v.id_sucursal,
    v.id_venta,
    v.id_ejecucion as id_ejecucion_esperada,
    r.id_ejecucion_ultima as id_ejecucion_guardada,
    case
      when r.id_venta is null then 'cabecera_ausente'
      when r.id_ejecucion_ultima <> v.id_ejecucion then 'ejecucion_anterior'
      when r.raw_data is distinct from v.raw_data then 'json_anterior'
    end as motivo
  from ventas_ultimas_respuestas v
  left join centum_sync.ventas_raw_v2 r
    on r.id_division = v.id_division
   and r.id_sucursal = v.id_sucursal
   and r.id_venta = v.id_venta
  where r.id_venta is null
     or r.id_ejecucion_ultima <> v.id_ejecucion
     or r.raw_data is distinct from v.raw_data
),
lineas_ultimas_respuestas as materialized (
  select
    v.id_division,
    v.id_sucursal,
    v.id_ejecucion,
    v.id_venta,
    a.ordinalidad::integer as linea_ordinal,
    a.item as raw_item
  from ventas_ultimas_respuestas v
  cross join lateral jsonb_array_elements(
    case
      when jsonb_typeof(v.raw_data -> 'VentaArticulos') = 'array'
      then v.raw_data -> 'VentaArticulos'
      else '[]'::jsonb
    end
  ) with ordinality as a(item, ordinalidad)
),
items_documentos_auditados as materialized (
  select i.*
  from centum_sync.ventas_items_v2 i
  cross join ventana p
  where i.fecha_comprobante between p.fecha_desde and p.fecha_hasta
),
lineas_no_autoritativas as (
  select
    coalesce(v.id_division, i.id_division) as id_division,
    coalesce(v.id_sucursal, i.id_sucursal) as id_sucursal,
    coalesce(v.id_venta, i.id_venta) as id_venta,
    coalesce(v.linea_ordinal, i.linea_ordinal) as linea_ordinal,
    case
      when i.id_venta is null then 'linea_ausente'
      when v.id_venta is null then 'linea_obsoleta'
      when i.id_ejecucion_ultima <> v.id_ejecucion then 'ejecucion_anterior'
      when i.raw_item is distinct from v.raw_item then 'json_anterior'
    end as motivo
  from lineas_ultimas_respuestas v
  full outer join items_documentos_auditados i
    on i.id_division = v.id_division
   and i.id_sucursal = v.id_sucursal
   and i.id_venta = v.id_venta
   and i.linea_ordinal = v.linea_ordinal
  where i.id_venta is null
     or v.id_venta is null
     or i.id_ejecucion_ultima <> v.id_ejecucion
     or i.raw_item is distinct from v.raw_item
),
controles (orden, control, estado, encontrados, esperado, detalle) as (
  select
    1,
    'ventana_json_auditada',
    'INFO',
    count(*),
    null::bigint,
    concat(p.fecha_desde, ' a ', p.fecha_hasta, '; lotes procesados')
  from lotes_mes l
  cross join ventana p
  group by p.fecha_desde, p.fecha_hasta

  union all

  select
    2,
    'lotes_vs_respuesta_cruda',
    case when count(*) = 0 then 'OK' else 'REVISAR' end,
    count(*),
    0::bigint,
    'El conteo guardado debe coincidir con Ventas.Items y VentaArticulos'
  from lotes_con_diferencias

  union all

  select
    3,
    'ultima_version_de_cabeceras',
    case when count(*) = 0 then 'OK' else 'REVISAR' end,
    count(*),
    0::bigint,
    'La cabecera canonica debe coincidir con la ultima respuesta procesada'
  from documentos_no_autoritativos

  union all

  select
    4,
    'ultima_version_de_lineas',
    case when count(*) = 0 then 'OK' else 'REVISAR' end,
    count(*),
    0::bigint,
    'Las lineas canonicas deben coincidir con el ultimo VentaArticulos recibido'
  from lineas_no_autoritativas
)
select
  control,
  estado,
  encontrados,
  esperado,
  detalle
from controles
order by orden;
