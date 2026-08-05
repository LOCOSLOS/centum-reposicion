-- Cierre liviano de calidad del historico de ventas v2.
-- Issue relacionado: #3.
--
-- Complementa:
--   006: cobertura acumulada y conciliacion de ejecuciones/lotes.
--   007: validacion profunda JSON vs canonico sobre una muestra de 12 meses.
--
-- No abre respuestas JSON ni recalcula vistas agregadas.

with
parametros as (
  select
    date '2024-07-01' as fecha_desde,
    (now() at time zone 'America/Argentina/Buenos_Aires')::date - 1
      as fecha_hasta
),
ejecuciones_periodo as materialized (
  select
    e.id_ejecucion,
    e.fecha_desde,
    e.fecha_hasta
  from centum_sync.carga_ejecuciones_v2 e
  cross join parametros p
  where e.fecha_hasta >= p.fecha_desde
    and e.fecha_desde <= p.fecha_hasta
),
items_periodo as materialized (
  select
    i.id_division,
    i.id_sucursal,
    i.id_venta,
    i.linea_ordinal,
    i.id_articulo,
    i.fecha_comprobante,
    i.codigo,
    i.cantidad,
    i.id_ejecucion_ultima,
    e.fecha_desde as fecha_desde_ejecucion,
    e.fecha_hasta as fecha_hasta_ejecucion
  from centum_sync.ventas_items_v2 i
  join ejecuciones_periodo e
    on e.id_ejecucion = i.id_ejecucion_ultima
),
resumen_items as (
  select
    count(*) as lineas,
    count(*) filter (
      where fecha_comprobante is null
    ) as sin_fecha,
    count(*) filter (
      where id_articulo is null
    ) as sin_articulo,
    count(*) filter (
      where id_sucursal is null
    ) as sin_sucursal,
    count(*) filter (
      where id_venta is null or btrim(id_venta) = ''
    ) as sin_venta,
    count(*) filter (
      where linea_ordinal is null or linea_ordinal <= 0
    ) as ordinal_invalido,
    count(*) filter (
      where fecha_comprobante is not null
        and fecha_comprobante not between
          fecha_desde_ejecucion and fecha_hasta_ejecucion
    ) as fuera_de_ventana,
    count(*) filter (where cantidad > 0) as lineas_venta,
    count(*) filter (where cantidad < 0) as lineas_devolucion,
    count(*) filter (where cantidad = 0) as lineas_cero,
    coalesce(sum(cantidad) filter (where cantidad > 0), 0)
      as unidades_vendidas,
    coalesce(abs(sum(cantidad) filter (where cantidad < 0)), 0)
      as unidades_devueltas,
    coalesce(sum(cantidad), 0) as unidades_netas,
    count(*) filter (
      where upper(coalesce(codigo, '')) like 'ENVIO%'
    ) as lineas_servicio_envio
  from items_periodo
),
restricciones as (
  select
    count(*) filter (
      where c.contype = 'p'
        and pg_get_constraintdef(c.oid) =
          'PRIMARY KEY (id_division, id_sucursal, id_venta, linea_ordinal)'
    ) as pk_canonica,
    count(*) filter (
      where c.contype = 'f'
        and pg_get_constraintdef(c.oid) like
          'FOREIGN KEY (id_division, id_sucursal, id_venta)%'
    ) as fk_cabecera
  from pg_constraint c
  where c.conrelid = 'centum_sync.ventas_items_v2'::regclass
),
controles (orden, control, estado, encontrados, esperado, detalle) as (
  select
    1,
    'ventana_cierre',
    'INFO',
    r.lineas,
    null::bigint,
    concat(p.fecha_desde, ' a ', p.fecha_hasta)
  from resumen_items r
  cross join parametros p

  union all

  select
    2,
    'clave_canonica_y_fk_activas',
    case
      when pk_canonica = 1 and fk_cabecera >= 1 then 'OK'
      else 'REVISAR'
    end,
    (pk_canonica + fk_cabecera)::bigint,
    2::bigint,
    concat(
      'PK canonica=', pk_canonica,
      ', FK a cabecera=', fk_cabecera,
      '. La PK impide duplicados y la FK impide items huerfanos.'
    )
  from restricciones

  union all

  select
    3,
    'campos_criticos_nulos_o_invalidos',
    case
      when sin_fecha + sin_articulo + sin_sucursal + sin_venta
        + ordinal_invalido = 0
      then 'OK'
      else 'REVISAR'
    end,
    (
      sin_fecha + sin_articulo + sin_sucursal + sin_venta + ordinal_invalido
    )::bigint,
    0::bigint,
    concat(
      'sin_fecha=', sin_fecha,
      ', sin_articulo=', sin_articulo,
      ', sin_sucursal=', sin_sucursal,
      ', sin_venta=', sin_venta,
      ', ordinal_invalido=', ordinal_invalido
    )
  from resumen_items

  union all

  select
    4,
    'lineas_fuera_de_ventana',
    case when fuera_de_ventana = 0 then 'OK' else 'REVISAR' end,
    fuera_de_ventana,
    0::bigint,
    'La fecha del comprobante debe pertenecer a la ejecucion autoritativa'
  from resumen_items

  union all

  select
    5,
    'ventas_y_devoluciones',
    'INFO',
    lineas,
    null::bigint,
    concat(
      'lineas_venta=', lineas_venta,
      ', lineas_devolucion=', lineas_devolucion,
      ', lineas_cero=', lineas_cero,
      ', unidades_vendidas=', unidades_vendidas,
      ', unidades_devueltas=', unidades_devueltas,
      ', unidades_netas=', unidades_netas
    )
  from resumen_items

  union all

  select
    6,
    'servicio_envio_identificado',
    'INFO',
    lineas_servicio_envio,
    null::bigint,
    'Se conserva en ventas y se excluye del modelo de reposicion'
  from resumen_items
)
select
  control,
  estado,
  encontrados,
  esperado,
  detalle
from controles
order by orden;
