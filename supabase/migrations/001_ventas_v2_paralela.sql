-- Estructura paralela para probar la ingesta v2 sin modificar public.ventas_raw
-- ni public.ventas_items. Ejecutar desde el SQL Editor de Supabase.

begin;

create schema if not exists centum_sync;

create table if not exists centum_sync.carga_ejecuciones_v2 (
  id_ejecucion text primary key,
  workflow text not null default 'Centum Sync Ventas Diario v2',
  modo text not null default 'diario',
  fecha_desde date not null,
  fecha_hasta date not null,
  estado text not null default 'iniciada'
    check (estado in ('iniciada', 'completada', 'con_error')),
  lotes_esperados integer,
  lotes_procesados integer not null default 0,
  comprobantes_procesados integer not null default 0,
  lineas_procesadas integer not null default 0,
  iniciada_en timestamptz not null default now(),
  finalizada_en timestamptz,
  mensaje_error text,
  metadata jsonb not null default '{}'::jsonb,
  check (fecha_hasta >= fecha_desde)
);

create table if not exists centum_sync.ventas_lotes_v2 (
  id_lote bigint generated always as identity primary key,
  id_ejecucion text not null
    references centum_sync.carga_ejecuciones_v2 (id_ejecucion) on delete restrict,
  id_division bigint not null,
  sociedad text not null,
  id_sucursal bigint not null,
  sucursal_nombre text not null,
  fecha_desde date not null,
  fecha_hasta date not null,
  estado text not null default 'recibido'
    check (estado in ('recibido', 'procesado', 'con_error')),
  respuesta jsonb not null,
  comprobantes integer not null default 0,
  lineas integer not null default 0,
  recibido_en timestamptz not null default now(),
  procesado_en timestamptz,
  mensaje_error text,
  unique (id_ejecucion, id_division, id_sucursal, fecha_desde, fecha_hasta),
  check (fecha_hasta >= fecha_desde)
);

create table if not exists centum_sync.ventas_raw_v2 (
  id_division bigint not null,
  id_sucursal bigint not null,
  id_venta text not null,
  id_ejecucion_ultima text not null
    references centum_sync.carga_ejecuciones_v2 (id_ejecucion) on delete restrict,
  sociedad text not null,
  sucursal_nombre text not null,
  periodo text,
  fecha_comprobante date,
  tipo_comprobante text,
  numero_comprobante text,
  cliente_id text,
  cliente_nombre text,
  importe_total numeric,
  importe_neto numeric,
  impuestos numeric,
  raw_data jsonb not null,
  creado_en timestamptz not null default now(),
  actualizado_en timestamptz not null default now(),
  primary key (id_division, id_sucursal, id_venta)
);

create table if not exists centum_sync.ventas_items_v2 (
  id_division bigint not null,
  id_sucursal bigint not null,
  id_venta text not null,
  linea_ordinal integer not null check (linea_ordinal > 0),
  id_ejecucion_ultima text not null
    references centum_sync.carga_ejecuciones_v2 (id_ejecucion) on delete restrict,
  id_linea_origen text,
  id_articulo bigint,
  sociedad text not null,
  sucursal_nombre text not null,
  periodo text,
  fecha_comprobante date,
  codigo text,
  nombre text,
  cantidad numeric not null default 0,
  precio numeric not null default 0,
  precio_neto numeric not null default 0,
  costo_reposicion numeric not null default 0,
  porcentaje_descuento numeric not null default 0,
  iva_tasa numeric not null default 0,
  subtotal numeric not null default 0,
  total numeric not null default 0,
  raw_item jsonb not null,
  creado_en timestamptz not null default now(),
  actualizado_en timestamptz not null default now(),
  primary key (id_division, id_sucursal, id_venta, linea_ordinal),
  foreign key (id_division, id_sucursal, id_venta)
    references centum_sync.ventas_raw_v2 (id_division, id_sucursal, id_venta)
    on delete cascade
);

create index if not exists ventas_raw_v2_fecha_idx
  on centum_sync.ventas_raw_v2 (fecha_comprobante, id_sucursal, id_division);

create index if not exists ventas_items_v2_articulo_fecha_idx
  on centum_sync.ventas_items_v2 (id_articulo, fecha_comprobante, id_sucursal);

create index if not exists ventas_items_v2_ejecucion_idx
  on centum_sync.ventas_items_v2 (id_ejecucion_ultima);

create or replace function centum_sync.ingestar_lote_ventas_v2(
  p_id_ejecucion text,
  p_id_division bigint,
  p_sociedad text,
  p_id_sucursal bigint,
  p_sucursal_nombre text,
  p_fecha_desde date,
  p_fecha_hasta date,
  p_respuesta jsonb
)
returns table (comprobantes integer, lineas integer)
language plpgsql
security invoker
set search_path = pg_catalog, public, centum_sync
as $$
declare
  v_id_lote bigint;
  v_comprobantes integer := 0;
  v_lineas integer := 0;
begin
  if p_id_ejecucion is null or btrim(p_id_ejecucion) = '' then
    raise exception 'id_ejecucion es obligatorio';
  end if;

  if p_respuesta is null then
    raise exception 'respuesta es obligatoria';
  end if;

  insert into centum_sync.carga_ejecuciones_v2 (
    id_ejecucion, fecha_desde, fecha_hasta, estado
  ) values (
    p_id_ejecucion, p_fecha_desde, p_fecha_hasta, 'iniciada'
  )
  on conflict (id_ejecucion) do nothing;

  insert into centum_sync.ventas_lotes_v2 (
    id_ejecucion, id_division, sociedad, id_sucursal, sucursal_nombre,
    fecha_desde, fecha_hasta, estado, respuesta, recibido_en,
    comprobantes, lineas, procesado_en, mensaje_error
  ) values (
    p_id_ejecucion, p_id_division, p_sociedad, p_id_sucursal, p_sucursal_nombre,
    p_fecha_desde, p_fecha_hasta, 'recibido', p_respuesta, now(),
    0, 0, null, null
  )
  on conflict (id_ejecucion, id_division, id_sucursal, fecha_desde, fecha_hasta)
  do update set
    sociedad = excluded.sociedad,
    sucursal_nombre = excluded.sucursal_nombre,
    estado = 'recibido',
    respuesta = excluded.respuesta,
    recibido_en = now(),
    comprobantes = 0,
    lineas = 0,
    procesado_en = null,
    mensaje_error = null
  returning id_lote into v_id_lote;

  insert into centum_sync.ventas_raw_v2 (
    id_division, id_sucursal, id_venta, id_ejecucion_ultima,
    sociedad, sucursal_nombre, periodo, fecha_comprobante,
    tipo_comprobante, numero_comprobante, cliente_id, cliente_nombre,
    importe_total, importe_neto, impuestos, raw_data, actualizado_en
  )
  select
    p_id_division,
    p_id_sucursal,
    venta.item ->> 'IdVenta',
    p_id_ejecucion,
    p_sociedad,
    p_sucursal_nombre,
    left(venta.item ->> 'FechaDocumento', 7),
    nullif(left(venta.item ->> 'FechaDocumento', 10), '')::date,
    case
      when nullif(venta.item #>> '{TipoComprobanteVenta,Codigo}', '') is null then null
      else concat(
        venta.item #>> '{TipoComprobanteVenta,Codigo}',
        '-',
        coalesce(venta.item #>> '{NumeroDocumento,LetraDocumento}', '')
      )
    end,
    case
      when nullif(venta.item #>> '{NumeroDocumento,LetraDocumento}', '') is null then null
      else concat(
        venta.item #>> '{NumeroDocumento,LetraDocumento}', '-',
        lpad(coalesce(venta.item #>> '{NumeroDocumento,PuntoVenta}', ''), 4, '0'), '-',
        lpad(coalesce(venta.item #>> '{NumeroDocumento,Numero}', ''), 8, '0')
      )
    end,
    nullif(venta.item ->> 'IdCliente', ''),
    nullif(venta.item ->> 'RazonSocialCliente', ''),
    coalesce(nullif(venta.item ->> 'Total', '')::numeric, 0),
    coalesce(nullif(venta.item ->> 'NetoGravado', '')::numeric, 0),
    coalesce(nullif(venta.item ->> 'IVA', '')::numeric, 0)
      + coalesce(nullif(venta.item ->> 'RegimenesEspeciales', '')::numeric, 0)
      + coalesce(nullif(venta.item ->> 'ImpuestosInternos', '')::numeric, 0),
    venta.item,
    now()
  from jsonb_array_elements(
    coalesce(p_respuesta #> '{Ventas,Items}', '[]'::jsonb)
  ) as venta(item)
  where nullif(venta.item ->> 'IdVenta', '') is not null
  on conflict (id_division, id_sucursal, id_venta) do update set
    id_ejecucion_ultima = excluded.id_ejecucion_ultima,
    sociedad = excluded.sociedad,
    sucursal_nombre = excluded.sucursal_nombre,
    periodo = excluded.periodo,
    fecha_comprobante = excluded.fecha_comprobante,
    tipo_comprobante = excluded.tipo_comprobante,
    numero_comprobante = excluded.numero_comprobante,
    cliente_id = excluded.cliente_id,
    cliente_nombre = excluded.cliente_nombre,
    importe_total = excluded.importe_total,
    importe_neto = excluded.importe_neto,
    impuestos = excluded.impuestos,
    raw_data = excluded.raw_data,
    actualizado_en = now();

  get diagnostics v_comprobantes = row_count;

  -- Si Centum modifica la cantidad u orden de las líneas de un comprobante,
  -- reemplazamos el detalle completo recibido para no dejar ordinales obsoletos.
  delete from centum_sync.ventas_items_v2 destino
  using (
    select distinct venta.item ->> 'IdVenta' as id_venta
    from jsonb_array_elements(
      coalesce(p_respuesta #> '{Ventas,Items}', '[]'::jsonb)
    ) as venta(item)
    where nullif(venta.item ->> 'IdVenta', '') is not null
  ) origen
  where destino.id_division = p_id_division
    and destino.id_sucursal = p_id_sucursal
    and destino.id_venta = origen.id_venta;

  insert into centum_sync.ventas_items_v2 (
    id_division, id_sucursal, id_venta, linea_ordinal,
    id_ejecucion_ultima, id_linea_origen, id_articulo,
    sociedad, sucursal_nombre, periodo, fecha_comprobante,
    codigo, nombre, cantidad, precio, precio_neto, costo_reposicion,
    porcentaje_descuento, iva_tasa, subtotal, total, raw_item, actualizado_en
  )
  select
    p_id_division,
    p_id_sucursal,
    venta.item ->> 'IdVenta',
    articulo.ordinalidad::integer,
    p_id_ejecucion,
    coalesce(
      nullif(articulo.item ->> 'IdVentaArticulo', ''),
      nullif(articulo.item ->> 'IdVentaItem', ''),
      nullif(articulo.item ->> 'Id', '')
    ),
    nullif(articulo.item ->> 'IdArticulo', '')::bigint,
    p_sociedad,
    p_sucursal_nombre,
    left(venta.item ->> 'FechaDocumento', 7),
    nullif(left(venta.item ->> 'FechaDocumento', 10), '')::date,
    nullif(articulo.item ->> 'Codigo', ''),
    nullif(articulo.item ->> 'Nombre', ''),
    coalesce(nullif(articulo.item ->> 'Cantidad', '')::numeric, 0),
    coalesce(nullif(articulo.item ->> 'Precio', '')::numeric, 0),
    coalesce(nullif(articulo.item ->> 'PrecioNeto', '')::numeric, 0),
    coalesce(nullif(articulo.item ->> 'CostoReposicion', '')::numeric, 0),
    coalesce(nullif(articulo.item ->> 'PorcentajeDescuento1', '')::numeric, 0),
    coalesce(nullif(articulo.item #>> '{CategoriaImpuestoIVA,Tasa}', '')::numeric, 0),
    coalesce(nullif(articulo.item ->> 'SubtotalSinImpuestos', '')::numeric, 0),
    coalesce(nullif(articulo.item ->> 'Total', '')::numeric, 0),
    articulo.item,
    now()
  from jsonb_array_elements(
    coalesce(p_respuesta #> '{Ventas,Items}', '[]'::jsonb)
  ) as venta(item)
  cross join lateral jsonb_array_elements(
    coalesce(venta.item -> 'VentaArticulos', '[]'::jsonb)
  ) with ordinality as articulo(item, ordinalidad)
  where nullif(venta.item ->> 'IdVenta', '') is not null
  on conflict (id_division, id_sucursal, id_venta, linea_ordinal) do update set
    id_ejecucion_ultima = excluded.id_ejecucion_ultima,
    id_linea_origen = excluded.id_linea_origen,
    id_articulo = excluded.id_articulo,
    sociedad = excluded.sociedad,
    sucursal_nombre = excluded.sucursal_nombre,
    periodo = excluded.periodo,
    fecha_comprobante = excluded.fecha_comprobante,
    codigo = excluded.codigo,
    nombre = excluded.nombre,
    cantidad = excluded.cantidad,
    precio = excluded.precio,
    precio_neto = excluded.precio_neto,
    costo_reposicion = excluded.costo_reposicion,
    porcentaje_descuento = excluded.porcentaje_descuento,
    iva_tasa = excluded.iva_tasa,
    subtotal = excluded.subtotal,
    total = excluded.total,
    raw_item = excluded.raw_item,
    actualizado_en = now();

  get diagnostics v_lineas = row_count;

  update centum_sync.ventas_lotes_v2
  set estado = 'procesado',
      comprobantes = v_comprobantes,
      lineas = v_lineas,
      procesado_en = now(),
      mensaje_error = null
  where id_lote = v_id_lote;

  update centum_sync.carga_ejecuciones_v2 ejecucion
  set lotes_procesados = resumen.lotes,
      comprobantes_procesados = resumen.comprobantes,
      lineas_procesadas = resumen.lineas
  from (
    select
      count(*) filter (where estado = 'procesado')::integer as lotes,
      coalesce(sum(comprobantes), 0)::integer as comprobantes,
      coalesce(sum(lineas), 0)::integer as lineas
    from centum_sync.ventas_lotes_v2
    where id_ejecucion = p_id_ejecucion
  ) resumen
  where ejecucion.id_ejecucion = p_id_ejecucion;

  return query select v_comprobantes, v_lineas;
end;
$$;

comment on table centum_sync.carga_ejecuciones_v2 is
  'Auditoria de cada ejecucion del workflow de ventas v2.';
comment on table centum_sync.ventas_lotes_v2 is
  'Respuesta completa de cada consulta division/sucursal para trazabilidad.';
comment on table centum_sync.ventas_raw_v2 is
  'Cabeceras de ventas v2; no reemplaza public.ventas_raw durante la prueba.';
comment on table centum_sync.ventas_items_v2 is
  'Lineas v2 identificadas por su posicion original dentro del comprobante.';

commit;

