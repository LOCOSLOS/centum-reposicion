-- Auditoria acumulada del historico de ventas v2 - fase 1 liviana.
-- Issue relacionado: #3.
--
-- Ejecutar completa desde el SQL Editor de Supabase. Esta fase consulta solo
-- las cabeceras de ejecucion y lotes; no abre respuestas JSON ni recalcula la
-- vista canonica. La auditoria de contenido se ejecuta por mes con 007.

with
parametros as (
  select
    date '2024-07-01' as fecha_desde,
    (now() at time zone 'America/Argentina/Buenos_Aires')::date - 1
      as fecha_hasta
),
combinaciones_esperadas (id_division, id_sucursal) as (
  values
    (2::bigint, 6455::bigint),
    (1::bigint, 6455::bigint),
    (2::bigint, 6457::bigint),
    (3::bigint, 6457::bigint),
    (2::bigint, 6084::bigint),
    (1::bigint, 6084::bigint),
    (2::bigint, 6761::bigint),
    (3::bigint, 6761::bigint),
    (2::bigint, 6458::bigint),
    (1::bigint, 6458::bigint),
    (2::bigint, 8774::bigint),
    (1::bigint, 8774::bigint),
    (2::bigint, 9254::bigint),
    (6::bigint, 9254::bigint),
    (2::bigint, 9258::bigint),
    (3::bigint, 9258::bigint),
    (2::bigint, 9261::bigint),
    (1::bigint, 9261::bigint),
    (2::bigint, 9281::bigint),
    (1::bigint, 9281::bigint),
    (2::bigint, 9292::bigint),
    (3::bigint, 9292::bigint),
    (2::bigint, 9302::bigint),
    (1::bigint, 9302::bigint),
    (2::bigint, 9308::bigint),
    (1::bigint, 9308::bigint)
),
ejecuciones_reconciliadas as materialized (
  select
    e.id_ejecucion,
    e.estado,
    e.fecha_desde,
    e.fecha_hasta,
    e.lotes_esperados,
    e.lotes_procesados,
    e.comprobantes_procesados,
    e.lineas_procesadas,
    count(l.id_lote) as lotes_reales,
    count(l.id_lote) filter (where l.estado = 'procesado')
      as lotes_procesados_reales,
    count(l.id_lote) filter (where l.estado = 'recibido')
      as lotes_recibidos,
    count(l.id_lote) filter (where l.estado = 'con_error')
      as lotes_con_error,
    count(distinct (l.id_division, l.id_sucursal)) filter (
      where l.estado = 'procesado'
        and exists (
          select 1
          from combinaciones_esperadas c
          where c.id_division = l.id_division
            and c.id_sucursal = l.id_sucursal
        )
    ) as combinaciones_esperadas_procesadas,
    coalesce(sum(l.comprobantes) filter (where l.estado = 'procesado'), 0)
      as comprobantes_reales,
    coalesce(sum(l.lineas) filter (where l.estado = 'procesado'), 0)
      as lineas_reales
  from centum_sync.carga_ejecuciones_v2 e
  cross join parametros p
  left join centum_sync.ventas_lotes_v2 l
    on l.id_ejecucion = e.id_ejecucion
  where e.fecha_hasta >= p.fecha_desde
    and e.fecha_desde <= p.fecha_hasta
  group by
    e.id_ejecucion,
    e.estado,
    e.fecha_desde,
    e.fecha_hasta,
    e.lotes_esperados,
    e.lotes_procesados,
    e.comprobantes_procesados,
    e.lineas_procesadas
),
ejecuciones_reconciliadas_validas as materialized (
  select *
  from ejecuciones_reconciliadas
  where estado = 'completada'
    and lotes_esperados is not null
    and lotes_procesados = lotes_esperados
    and lotes_reales = lotes_esperados
    and lotes_procesados_reales = lotes_esperados
    and lotes_recibidos = 0
    and lotes_con_error = 0
    and comprobantes_procesados = comprobantes_reales
    and lineas_procesadas = lineas_reales
),
ejecuciones_validas as materialized (
  select *
  from ejecuciones_reconciliadas_validas
  where lotes_esperados = 26
    and combinaciones_esperadas_procesadas = 26
),
ejecuciones_completadas_inconsistentes as (
  select e.*
  from ejecuciones_reconciliadas e
  where e.estado = 'completada'
    and not exists (
      select 1
      from ejecuciones_reconciliadas_validas v
      where v.id_ejecucion = e.id_ejecucion
    )
),
dias_sin_cobertura as (
  select d.fecha::date
  from parametros p
  cross join lateral generate_series(
    p.fecha_desde,
    p.fecha_hasta,
    interval '1 day'
  ) as d(fecha)
  where not exists (
    select 1
    from ejecuciones_validas e
    where d.fecha::date between e.fecha_desde and e.fecha_hasta
  )
),
dias_sin_cobertura_detalle as (
  select
    d.fecha,
    coalesce(string_agg(
      concat(
        'id=', e.id_ejecucion,
        ' estado=', e.estado,
        ' lotes=', e.lotes_procesados, '/', e.lotes_esperados,
        ' reales=', e.lotes_procesados_reales, '/', e.lotes_reales,
        ' combinaciones=', e.combinaciones_esperadas_procesadas
      ),
      '; ' order by e.id_ejecucion
    ) filter (where e.id_ejecucion is not null), 'sin ejecuciones')
      as ejecuciones_candidatas
  from dias_sin_cobertura d
  left join ejecuciones_reconciliadas e
    on d.fecha between e.fecha_desde and e.fecha_hasta
  group by d.fecha
),
ejecuciones_no_completadas as (
  select *
  from ejecuciones_reconciliadas
  where estado <> 'completada'
),
controles (orden, control, estado, encontrados, esperado, detalle) as (
  select
    1,
    'ventana_auditada',
    'INFO',
    (p.fecha_hasta - p.fecha_desde + 1)::bigint,
    null::bigint,
    concat(p.fecha_desde, ' a ', p.fecha_hasta)
  from parametros p

  union all

  select
    2,
    'dias_cubiertos_por_ejecucion_valida_26_26',
    case when count(*) = 0 then 'OK' else 'REVISAR' end,
    count(*),
    0::bigint,
    concat(
      coalesce(string_agg(
        concat(fecha, ' [', ejecuciones_candidatas, ']'),
        '; ' order by fecha
      ), 'ninguna'),
      '. Deben tener una ejecucion completada, reconciliada y 26/26.'
    )
  from dias_sin_cobertura_detalle

  union all

  select
    3,
    'ejecuciones_completadas_inconsistentes',
    case when count(*) = 0 then 'OK' else 'REVISAR' end,
    count(*),
    0::bigint,
    coalesce(string_agg(
      concat(
        'id=', id_ejecucion,
        ' [', fecha_desde, ' a ', fecha_hasta, ']',
        ' lotes=', lotes_procesados, '/', lotes_esperados,
        ' reales=', lotes_procesados_reales, '/', lotes_reales,
        ' combinaciones=', combinaciones_esperadas_procesadas,
        ' comprobantes=', comprobantes_procesados, '/', comprobantes_reales,
        ' lineas=', lineas_procesadas, '/', lineas_reales,
        ' recibidos=', lotes_recibidos,
        ' errores=', lotes_con_error
      ),
      '; ' order by fecha_desde, id_ejecucion
    ), 'ninguna')
  from ejecuciones_completadas_inconsistentes

  union all

  select
    4,
    'ejecuciones_validas',
    'INFO',
    count(*),
    null::bigint,
    concat(
      'primera=', min(fecha_desde),
      ', ultima=', max(fecha_hasta),
      ', comprobantes=', coalesce(sum(comprobantes_reales), 0),
      ', lineas=', coalesce(sum(lineas_reales), 0)
    )
  from ejecuciones_validas

  union all

  select
    5,
    'ejecuciones_no_completadas_historicas',
    'INFO',
    count(*),
    null::bigint,
    concat(
      'iniciadas=', count(*) filter (where estado = 'iniciada'),
      ', con_error=', count(*) filter (where estado = 'con_error'),
      '. No bloquean si dias_sin_cobertura=0.'
    )
  from ejecuciones_no_completadas
)
select
  control,
  estado,
  encontrados,
  esperado,
  detalle
from controles
order by orden;
