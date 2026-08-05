-- Control liviano de la persistencia de snapshots de ordenes de traspaso.

with controles as (
  select
    'ejecucion_ultima'::text as control,
    case when e.estado = 'completada' and e.reportes_procesados = 2
      then 'OK' else 'REVISAR' end as estado,
    e.reportes_procesados::bigint as encontrados,
    2::bigint as esperado,
    concat(
      'id=', e.id_ejecucion,
      ', nuevas=', e.importaciones_nuevas,
      ', reutilizadas=', e.importaciones_reutilizadas
    ) as detalle,
    1 as orden
  from centum_sync.odt_ejecuciones e
  order by e.iniciada_en desc
  limit 1
), duplicados as (
  select count(*)::bigint as cantidad
  from (
    select d.id_importacion, d.numero_documento, d.clave
    from centum_sync.odt_detalle d
    group by d.id_importacion, d.numero_documento, d.clave
    having count(*) > 1
  ) x
), pendientes as (
  select count(*)::bigint as cantidad
  from centum_sync.odt_detalle d
  join centum_sync.odt_importaciones i using (id_importacion)
  where i.tipo_reporte = 'stock_en_transito'
    and d.cantidad_pendiente
      <> greatest(d.cantidad_despachada - d.cantidad_recibida, 0)
), huerfanas as (
  select count(*)::bigint as cantidad
  from centum_sync.odt_detalle d
  left join centum_sync.odt_documentos doc
    using (id_importacion, numero_documento)
  where doc.id_importacion is null
), base as (
  select * from controles
  union all
  select
    'claves_duplicadas',
    case when d.cantidad = 0 then 'OK' else 'REVISAR' end,
    d.cantidad,
    0,
    'La PK impide repetir NumeroDocumento + Clave dentro de un snapshot.',
    2
  from duplicados d
  union all
  select
    'pendiente_despachado_menos_recibido',
    case when p.cantidad = 0 then 'OK' else 'REVISAR' end,
    p.cantidad,
    0,
    'Pendiente debe ser max(despachado - recibido, 0).',
    3
  from pendientes p
  union all
  select
    'lineas_huerfanas',
    case when h.cantidad = 0 then 'OK' else 'REVISAR' end,
    h.cantidad,
    0,
    'Cada linea debe pertenecer a un documento de la misma importacion.',
    4
  from huerfanas h
  union all
  select
    'volumen_acumulado',
    'INFO',
    count(*)::bigint,
    null::bigint,
    concat(
      'importaciones=', count(distinct d.id_importacion),
      ', documentos=', count(distinct (d.id_importacion, d.numero_documento))
    ),
    5
  from centum_sync.odt_detalle d
)
select control, estado, encontrados, esperado, detalle
from base
order by orden;

-- Idempotencia esperada para dos ejecuciones consecutivas sin cambios:
-- la segunda debe quedar completada con importaciones_nuevas = 0
-- e importaciones_reutilizadas = 2.
select
  id_ejecucion,
  estado,
  reportes_procesados,
  importaciones_nuevas,
  importaciones_reutilizadas,
  iniciada_en,
  finalizada_en
from centum_sync.odt_ejecuciones
order by iniciada_en desc
limit 10;
