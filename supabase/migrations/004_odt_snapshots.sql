-- Snapshots idempotentes de ordenes de traspaso obtenidas desde Drive.
-- Conserva cada version distinta de los dos reportes y permite reconstruir
-- despachos, recepciones y pendientes por NumeroDocumento + Clave.

begin;

create schema if not exists centum_sync;

create table if not exists centum_sync.odt_ejecuciones (
  id_ejecucion text primary key,
  workflow_id text not null default '4B0rMSpQjslHoulA',
  estado text not null default 'iniciada'
    check (estado in ('iniciada', 'completada', 'con_error')),
  reportes_esperados integer not null default 2
    check (reportes_esperados = 2),
  reportes_procesados integer not null default 0,
  importaciones_nuevas integer not null default 0,
  importaciones_reutilizadas integer not null default 0,
  iniciada_en timestamptz not null default now(),
  finalizada_en timestamptz,
  mensaje_error text
);

create table if not exists centum_sync.odt_importaciones (
  id_importacion bigint generated always as identity primary key,
  tipo_reporte text not null
    check (tipo_reporte in ('stock_en_transito', 'odt_efectivas_35_dias')),
  archivo_id text not null,
  archivo_nombre text not null,
  archivo_modificado_en timestamptz not null,
  huella_contenido text not null,
  observado_en timestamptz not null,
  resumen jsonb not null,
  registros_leidos integer not null check (registros_leidos >= 0),
  registros_validos integer not null check (registros_validos >= 0),
  documentos_leidos integer not null check (documentos_leidos >= 0),
  creado_en timestamptz not null default now(),
  unique (tipo_reporte, huella_contenido)
);

create index if not exists odt_importaciones_fecha_idx
  on centum_sync.odt_importaciones (tipo_reporte, observado_en desc);

create table if not exists centum_sync.odt_ejecucion_importaciones (
  id_ejecucion text not null
    references centum_sync.odt_ejecuciones (id_ejecucion) on delete restrict,
  tipo_reporte text not null
    check (tipo_reporte in ('stock_en_transito', 'odt_efectivas_35_dias')),
  id_importacion bigint not null
    references centum_sync.odt_importaciones (id_importacion) on delete restrict,
  importacion_nueva boolean not null,
  vinculada_en timestamptz not null default now(),
  primary key (id_ejecucion, tipo_reporte),
  unique (id_ejecucion, id_importacion)
);

create table if not exists centum_sync.odt_documentos (
  id_importacion bigint not null
    references centum_sync.odt_importaciones (id_importacion) on delete restrict,
  numero_documento text not null,
  fecha_documento text not null,
  sucursal_desde_nombre text not null,
  sucursal_hacia_nombre text not null,
  lineas integer not null check (lineas > 0),
  unidades_despachadas numeric,
  unidades_recibidas numeric not null,
  unidades_pendientes numeric,
  primary key (id_importacion, numero_documento)
);

create index if not exists odt_documentos_numero_idx
  on centum_sync.odt_documentos (numero_documento, id_importacion);

create table if not exists centum_sync.odt_detalle (
  id_importacion bigint not null,
  numero_documento text not null,
  clave text not null,
  nombre text not null,
  fila_csv integer not null check (fila_csv > 0),
  fecha_documento text not null,
  sucursal_desde_nombre text not null,
  sucursal_hacia_nombre text not null,
  cantidad_despachada numeric,
  cantidad_recibida numeric not null,
  cantidad_pendiente numeric,
  estado_linea text not null,
  primary key (id_importacion, numero_documento, clave),
  foreign key (id_importacion, numero_documento)
    references centum_sync.odt_documentos (id_importacion, numero_documento)
    on delete restrict
);

create index if not exists odt_detalle_clave_idx
  on centum_sync.odt_detalle (numero_documento, clave, id_importacion);

create or replace function centum_sync.ingestar_snapshot_odt(
  p_id_ejecucion text,
  p_observado_en timestamptz,
  p_tipo_reporte text,
  p_archivo jsonb,
  p_resumen jsonb,
  p_lineas jsonb
)
returns table (
  id_importacion bigint,
  tipo_reporte text,
  importacion_nueva boolean,
  registros_persistidos integer,
  documentos_persistidos integer,
  reportes_procesados integer,
  ejecucion_completada boolean
)
language plpgsql
security invoker
set search_path = pg_catalog, public, centum_sync
as $$
declare
  v_id_importacion bigint;
  v_huella text;
  v_importacion_nueva boolean := false;
  v_filas integer;
  v_documentos integer;
  v_reportes integer;
  v_inconsistencias integer;
begin
  if p_id_ejecucion is null or btrim(p_id_ejecucion) = '' then
    raise exception 'id_ejecucion es obligatorio';
  end if;

  if p_tipo_reporte not in ('stock_en_transito', 'odt_efectivas_35_dias') then
    raise exception 'tipo_reporte no soportado: %', p_tipo_reporte;
  end if;

  if p_archivo is null or jsonb_typeof(p_archivo) <> 'object' then
    raise exception 'archivo debe ser un objeto JSON';
  end if;

  if nullif(p_archivo ->> 'id', '') is null
     or nullif(p_archivo ->> 'nombre', '') is null
     or nullif(p_archivo ->> 'modificado_en', '') is null then
    raise exception 'archivo requiere id, nombre y modificado_en';
  end if;

  if p_resumen is null or jsonb_typeof(p_resumen) <> 'object' then
    raise exception 'resumen debe ser un objeto JSON';
  end if;

  if p_resumen ->> 'estado' <> 'VALIDACION_OK'
     or coalesce((p_resumen ->> 'registros_invalidos')::integer, 0) <> 0
     or coalesce((p_resumen ->> 'claves_duplicadas')::integer, 0) <> 0 then
    raise exception 'el reporte no supero la validacion previa';
  end if;

  if p_lineas is null or jsonb_typeof(p_lineas) <> 'array' then
    raise exception 'lineas debe ser un array JSON';
  end if;

  v_filas := jsonb_array_length(p_lineas);
  if v_filas <> coalesce((p_resumen ->> 'registros_leidos')::integer, -1) then
    raise exception 'registros_leidos (%) no coincide con el array (%)',
      p_resumen ->> 'registros_leidos', v_filas;
  end if;

  select count(*)::integer
  into v_inconsistencias
  from jsonb_array_elements(p_lineas) as origen(item)
  where coalesce((item ->> 'valido')::boolean, false) is false
     or nullif(item ->> 'numero_documento', '') is null
     or nullif(item ->> 'clave', '') is null
     or nullif(item ->> 'fecha_documento', '') is null
     or nullif(item ->> 'sucursal_desde_nombre', '') is null
     or nullif(item ->> 'sucursal_hacia_nombre', '') is null
     or nullif(item ->> 'nombre', '') is null
     or (item ->> 'cantidad_validacion_recepcion') is null
     or (item ->> 'cantidad_validacion_recepcion')::numeric < 0
     or (
       p_tipo_reporte = 'stock_en_transito'
       and (
         (item ->> 'cantidad_validacion_despacho') is null
         or (item ->> 'cantidad_validacion_despacho')::numeric < 0
         or (item ->> 'cantidad_validacion_recepcion')::numeric
            > (item ->> 'cantidad_validacion_despacho')::numeric
         or (item ->> 'cantidad_pendiente_transito')::numeric
            <> greatest(
              (item ->> 'cantidad_validacion_despacho')::numeric
              - (item ->> 'cantidad_validacion_recepcion')::numeric,
              0
            )
       )
     );

  if v_inconsistencias > 0 then
    raise exception 'hay % lineas invalidas o inconsistentes', v_inconsistencias;
  end if;

  select count(*)::integer
  into v_inconsistencias
  from (
    select item ->> 'numero_documento', item ->> 'clave'
    from jsonb_array_elements(p_lineas) as origen(item)
    group by item ->> 'numero_documento', item ->> 'clave'
    having count(*) > 1
  ) duplicadas;

  if v_inconsistencias > 0 then
    raise exception 'hay % claves NumeroDocumento + Clave duplicadas',
      v_inconsistencias;
  end if;

  select count(*)::integer
  into v_inconsistencias
  from (
    select item ->> 'numero_documento'
    from jsonb_array_elements(p_lineas) as origen(item)
    group by item ->> 'numero_documento'
    having count(distinct concat_ws(
      '|',
      item ->> 'fecha_documento',
      item ->> 'sucursal_desde_nombre',
      item ->> 'sucursal_hacia_nombre'
    )) > 1
  ) documentos_inconsistentes;

  if v_inconsistencias > 0 then
    raise exception 'hay % documentos con cabeceras inconsistentes',
      v_inconsistencias;
  end if;

  select md5(coalesce(jsonb_agg(
    jsonb_strip_nulls(jsonb_build_object(
      'numero_documento', item ->> 'numero_documento',
      'clave', item ->> 'clave',
      'nombre', item ->> 'nombre',
      'fecha_documento', item ->> 'fecha_documento',
      'sucursal_desde_nombre', item ->> 'sucursal_desde_nombre',
      'sucursal_hacia_nombre', item ->> 'sucursal_hacia_nombre',
      'cantidad_validacion_despacho', item -> 'cantidad_validacion_despacho',
      'cantidad_validacion_recepcion', item -> 'cantidad_validacion_recepcion',
      'cantidad_pendiente_transito', item -> 'cantidad_pendiente_transito',
      'estado_linea', item ->> 'estado_linea'
    )) order by item ->> 'numero_documento', item ->> 'clave'
  )::text, '[]'))
  into v_huella
  from jsonb_array_elements(p_lineas) as origen(item);

  insert into centum_sync.odt_ejecuciones (
    id_ejecucion, workflow_id, estado, reportes_esperados, iniciada_en,
    finalizada_en, mensaje_error
  ) values (
    p_id_ejecucion, '4B0rMSpQjslHoulA', 'iniciada', 2, now(), null, null
  )
  on conflict (id_ejecucion) do update set
    estado = case
      when centum_sync.odt_ejecuciones.estado = 'completada'
        then 'completada'
      else 'iniciada'
    end,
    mensaje_error = null;

  insert into centum_sync.odt_importaciones (
    tipo_reporte, archivo_id, archivo_nombre, archivo_modificado_en,
    huella_contenido, observado_en, resumen, registros_leidos,
    registros_validos, documentos_leidos
  ) values (
    p_tipo_reporte,
    p_archivo ->> 'id',
    p_archivo ->> 'nombre',
    (p_archivo ->> 'modificado_en')::timestamptz,
    v_huella,
    p_observado_en,
    p_resumen,
    (p_resumen ->> 'registros_leidos')::integer,
    (p_resumen ->> 'registros_validos')::integer,
    (p_resumen ->> 'documentos_leidos')::integer
  )
  on conflict on constraint
    odt_importaciones_tipo_reporte_huella_contenido_key do nothing
  returning centum_sync.odt_importaciones.id_importacion
  into v_id_importacion;

  if v_id_importacion is not null then
    v_importacion_nueva := true;
  else
    select i.id_importacion
    into v_id_importacion
    from centum_sync.odt_importaciones i
    where i.tipo_reporte = p_tipo_reporte
      and i.huella_contenido = v_huella;
  end if;

  if v_importacion_nueva then
    insert into centum_sync.odt_documentos (
      id_importacion, numero_documento, fecha_documento,
      sucursal_desde_nombre, sucursal_hacia_nombre, lineas,
      unidades_despachadas, unidades_recibidas, unidades_pendientes
    )
    select
      v_id_importacion,
      item ->> 'numero_documento',
      min(item ->> 'fecha_documento'),
      min(item ->> 'sucursal_desde_nombre'),
      min(item ->> 'sucursal_hacia_nombre'),
      count(*)::integer,
      case when p_tipo_reporte = 'stock_en_transito'
        then sum((item ->> 'cantidad_validacion_despacho')::numeric)
      end,
      sum((item ->> 'cantidad_validacion_recepcion')::numeric),
      case when p_tipo_reporte = 'stock_en_transito'
        then sum((item ->> 'cantidad_pendiente_transito')::numeric)
      end
    from jsonb_array_elements(p_lineas) as origen(item)
    group by item ->> 'numero_documento';

    insert into centum_sync.odt_detalle (
      id_importacion, numero_documento, clave, nombre, fila_csv,
      fecha_documento, sucursal_desde_nombre, sucursal_hacia_nombre,
      cantidad_despachada, cantidad_recibida, cantidad_pendiente,
      estado_linea
    )
    select
      v_id_importacion,
      item ->> 'numero_documento',
      item ->> 'clave',
      item ->> 'nombre',
      (item ->> 'fila_csv')::integer,
      item ->> 'fecha_documento',
      item ->> 'sucursal_desde_nombre',
      item ->> 'sucursal_hacia_nombre',
      case when p_tipo_reporte = 'stock_en_transito'
        then (item ->> 'cantidad_validacion_despacho')::numeric
      end,
      (item ->> 'cantidad_validacion_recepcion')::numeric,
      case when p_tipo_reporte = 'stock_en_transito'
        then (item ->> 'cantidad_pendiente_transito')::numeric
      end,
      item ->> 'estado_linea'
    from jsonb_array_elements(p_lineas) as origen(item);
  end if;

  insert into centum_sync.odt_ejecucion_importaciones (
    id_ejecucion, tipo_reporte, id_importacion, importacion_nueva
  ) values (
    p_id_ejecucion, p_tipo_reporte, v_id_importacion, v_importacion_nueva
  )
  on conflict on constraint odt_ejecucion_importaciones_pkey do nothing;

  select count(*)::integer
  into v_reportes
  from centum_sync.odt_ejecucion_importaciones ei
  where ei.id_ejecucion = p_id_ejecucion;

  update centum_sync.odt_ejecuciones e
  set
    reportes_procesados = resumen.procesados,
    importaciones_nuevas = resumen.nuevas,
    importaciones_reutilizadas = resumen.reutilizadas,
    estado = case when resumen.procesados = e.reportes_esperados
      then 'completada' else 'iniciada' end,
    finalizada_en = case when resumen.procesados = e.reportes_esperados
      then now() else null end
  from (
    select
      count(*)::integer as procesados,
      count(*) filter (where ei.importacion_nueva)::integer as nuevas,
      count(*) filter (where not ei.importacion_nueva)::integer as reutilizadas
    from centum_sync.odt_ejecucion_importaciones ei
    where ei.id_ejecucion = p_id_ejecucion
  ) resumen
  where e.id_ejecucion = p_id_ejecucion;

  select count(*)::integer
  into v_documentos
  from centum_sync.odt_documentos d
  where d.id_importacion = v_id_importacion;

  return query select
    v_id_importacion,
    p_tipo_reporte,
    v_importacion_nueva,
    v_filas,
    v_documentos,
    v_reportes,
    v_reportes = 2;
end;
$$;

create or replace view centum_sync.vw_odt_control_por_ejecucion as
with pares as (
  select
    ei.id_ejecucion,
    max(ei.id_importacion) filter (
      where ei.tipo_reporte = 'stock_en_transito'
    ) as id_stock,
    max(ei.id_importacion) filter (
      where ei.tipo_reporte = 'odt_efectivas_35_dias'
    ) as id_efectivas
  from centum_sync.odt_ejecucion_importaciones ei
  group by ei.id_ejecucion
)
select
  p.id_ejecucion,
  stock.numero_documento,
  stock.clave,
  stock.fecha_documento,
  stock.sucursal_desde_nombre,
  stock.sucursal_hacia_nombre,
  stock.nombre,
  stock.cantidad_despachada,
  stock.cantidad_recibida as cantidad_recibida_stock,
  efectivas.cantidad_recibida as cantidad_recibida_efectiva,
  stock.cantidad_pendiente as cantidad_pendiente_stock,
  greatest(
    stock.cantidad_despachada
      - greatest(stock.cantidad_recibida, coalesce(efectivas.cantidad_recibida, 0)),
    0
  ) as cantidad_pendiente_control,
  efectivas.id_importacion is not null as encontrada_en_efectivas
from pares p
join centum_sync.odt_detalle stock
  on stock.id_importacion = p.id_stock
left join centum_sync.odt_detalle efectivas
  on efectivas.id_importacion = p.id_efectivas
 and efectivas.numero_documento = stock.numero_documento
 and efectivas.clave = stock.clave;

create or replace view centum_sync.vw_odt_stock_transiciones as
with secuencia as (
  select
    i.observado_en,
    d.*,
    lag(d.cantidad_despachada) over ventana as cantidad_despachada_anterior,
    lag(d.cantidad_recibida) over ventana as cantidad_recibida_anterior,
    lag(d.cantidad_pendiente) over ventana as cantidad_pendiente_anterior,
    lag(d.estado_linea) over ventana as estado_linea_anterior
  from centum_sync.odt_importaciones i
  join centum_sync.odt_detalle d using (id_importacion)
  where i.tipo_reporte = 'stock_en_transito'
  window ventana as (
    partition by d.numero_documento, d.clave
    order by i.observado_en, i.id_importacion
  )
)
select
  *,
  cantidad_despachada is distinct from cantidad_despachada_anterior
    or cantidad_recibida is distinct from cantidad_recibida_anterior
    or cantidad_pendiente is distinct from cantidad_pendiente_anterior
    or estado_linea is distinct from estado_linea_anterior
    as cambio_detectado
from secuencia;

comment on table centum_sync.odt_importaciones is
  'Una fila por contenido distinto de cada CSV de ODT; la huella evita duplicados.';

comment on table centum_sync.odt_detalle is
  'Detalle historico por importacion y clave NumeroDocumento + Clave.';

comment on view centum_sync.vw_odt_stock_transiciones is
  'Compara cada linea de stock en transito contra su snapshot anterior.';

commit;
