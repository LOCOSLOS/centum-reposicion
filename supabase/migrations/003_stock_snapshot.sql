-- Persistencia de stock por sucursal, sección y artículo.
-- No modifica las tablas ni vistas de ventas.

begin;

create table if not exists centum_sync.stock_ejecuciones (
  id_ejecucion text primary key,
  workflow text not null default 'Centum Stock v2',
  estado text not null default 'iniciada'
    check (estado in ('iniciada', 'completada', 'con_error')),
  sucursales_esperadas integer not null check (sucursales_esperadas > 0),
  sucursales_procesadas integer not null default 0,
  registros_recibidos integer not null default 0,
  registros_normalizados integer not null default 0,
  cambios_registrados integer not null default 0,
  iniciada_en timestamptz not null default now(),
  finalizada_en timestamptz,
  mensaje_error text
);

create table if not exists centum_sync.stock_lotes (
  id_ejecucion text not null
    references centum_sync.stock_ejecuciones (id_ejecucion) on delete restrict,
  id_sucursal bigint not null,
  estado text not null default 'procesado'
    check (estado in ('procesado', 'con_error')),
  registros_recibidos integer not null,
  registros_normalizados integer not null,
  cambios_registrados integer not null,
  procesado_en timestamptz not null default now(),
  mensaje_error text,
  primary key (id_ejecucion, id_sucursal)
);

create table if not exists centum_sync.stock_actual (
  id_sucursal bigint not null,
  id_seccion_sucursal bigint not null default 0,
  id_articulo bigint not null,
  existencias numeric not null default 0,
  cantidad_ordenes_compra numeric not null default 0,
  cantidad_pedidos_venta numeric not null default 0,
  stock_comprometido numeric not null default 0,
  stock_ideal numeric not null default 0,
  stock_minimo numeric not null default 0,
  stock_critico numeric not null default 0,
  stock_excesivo numeric not null default 0,
  codigo_articulo_propio_sucursal text,
  es_deposito_central boolean not null default false,
  observado_en timestamptz not null,
  id_ejecucion_ultima text not null
    references centum_sync.stock_ejecuciones (id_ejecucion) on delete restrict,
  actualizado_en timestamptz not null default now(),
  primary key (id_sucursal, id_seccion_sucursal, id_articulo)
);

create index if not exists stock_actual_articulo_idx
  on centum_sync.stock_actual (id_articulo, id_sucursal);

create index if not exists stock_actual_quiebre_idx
  on centum_sync.stock_actual (id_sucursal, existencias)
  where existencias <= 0;

create table if not exists centum_sync.stock_historial (
  id_stock_historial bigint generated always as identity primary key,
  id_sucursal bigint not null,
  id_seccion_sucursal bigint not null,
  id_articulo bigint not null,
  existencias numeric not null,
  cantidad_ordenes_compra numeric not null,
  cantidad_pedidos_venta numeric not null,
  stock_comprometido numeric not null,
  stock_ideal numeric not null,
  stock_minimo numeric not null,
  stock_critico numeric not null,
  stock_excesivo numeric not null,
  tipo_cambio text not null check (tipo_cambio in ('inicial', 'cambio')),
  observado_en timestamptz not null,
  id_ejecucion text not null
    references centum_sync.stock_ejecuciones (id_ejecucion) on delete restrict,
  registrado_en timestamptz not null default now()
);

create index if not exists stock_historial_articulo_fecha_idx
  on centum_sync.stock_historial (
    id_articulo, id_sucursal, observado_en desc
  );

create or replace function centum_sync.ingestar_stock_snapshot(
  p_id_ejecucion text,
  p_id_sucursal bigint,
  p_observado_en timestamptz,
  p_sucursales_esperadas integer,
  p_registros jsonb
)
returns table (
  registros_recibidos integer,
  registros_normalizados integer,
  cambios_registrados integer,
  ejecucion_completada boolean
)
language plpgsql
security invoker
set search_path = pg_catalog, public, centum_sync
as $$
declare
  v_recibidos integer := 0;
  v_normalizados integer := 0;
  v_cambios integer := 0;
  v_sucursales_procesadas integer := 0;
begin
  if p_id_ejecucion is null or btrim(p_id_ejecucion) = '' then
    raise exception 'id_ejecucion es obligatorio';
  end if;

  if p_id_sucursal is null then
    raise exception 'id_sucursal es obligatorio';
  end if;

  if p_sucursales_esperadas is null or p_sucursales_esperadas <= 0 then
    raise exception 'sucursales_esperadas debe ser mayor que cero';
  end if;

  if p_registros is null or jsonb_typeof(p_registros) <> 'array' then
    raise exception 'registros debe ser un array JSON';
  end if;

  v_recibidos := jsonb_array_length(p_registros);

  insert into centum_sync.stock_ejecuciones (
    id_ejecucion, workflow, estado, sucursales_esperadas, iniciada_en
  ) values (
    p_id_ejecucion, 'Centum Stock v2', 'iniciada',
    p_sucursales_esperadas, now()
  )
  on conflict (id_ejecucion) do update set
    sucursales_esperadas = excluded.sucursales_esperadas,
    estado = 'iniciada',
    finalizada_en = null,
    mensaje_error = null;

  with entrada as (
    select
      coalesce(nullif(item ->> 'IdSucursalFisica', '')::bigint, p_id_sucursal)
        as id_sucursal,
      coalesce(nullif(item ->> 'IdSeccionSucursal', '')::bigint, 0)
        as id_seccion_sucursal,
      nullif(item ->> 'IdArticulo', '')::bigint as id_articulo,
      coalesce(nullif(item ->> 'Existencias', '')::numeric, 0) as existencias,
      coalesce(nullif(item ->> 'CantidadOrdenesCompra', '')::numeric, 0)
        as cantidad_ordenes_compra,
      coalesce(nullif(item ->> 'CantidadPedidosVenta', '')::numeric, 0)
        as cantidad_pedidos_venta,
      coalesce(nullif(item ->> 'StockComprometido', '')::numeric, 0)
        as stock_comprometido,
      coalesce(nullif(item ->> 'StockIdeal', '')::numeric, 0) as stock_ideal,
      coalesce(nullif(item ->> 'StockMinimo', '')::numeric, 0) as stock_minimo,
      coalesce(nullif(item ->> 'StockCritico', '')::numeric, 0) as stock_critico,
      coalesce(nullif(item ->> 'StockExcesivo', '')::numeric, 0)
        as stock_excesivo,
      nullif(item ->> 'CodigoArticuloPropioSucursal', '')
        as codigo_articulo_propio_sucursal
    from jsonb_array_elements(p_registros) as origen(item)
    where nullif(item ->> 'IdArticulo', '') is not null
  ),
  deduplicada as (
    select distinct on (id_sucursal, id_seccion_sucursal, id_articulo)
      *
    from entrada
    where id_sucursal = p_id_sucursal
    order by
      id_sucursal,
      id_seccion_sucursal,
      id_articulo,
      existencias desc
  ),
  cambios as materialized (
    select
      d.*,
      case when actual.id_articulo is null then 'inicial' else 'cambio' end
        as tipo_cambio
    from deduplicada d
    left join centum_sync.stock_actual actual
      using (id_sucursal, id_seccion_sucursal, id_articulo)
    where actual.id_articulo is null
       or actual.existencias is distinct from d.existencias
       or actual.cantidad_ordenes_compra
          is distinct from d.cantidad_ordenes_compra
       or actual.cantidad_pedidos_venta
          is distinct from d.cantidad_pedidos_venta
       or actual.stock_comprometido is distinct from d.stock_comprometido
       or actual.stock_ideal is distinct from d.stock_ideal
       or actual.stock_minimo is distinct from d.stock_minimo
       or actual.stock_critico is distinct from d.stock_critico
       or actual.stock_excesivo is distinct from d.stock_excesivo
  ),
  historial as (
    insert into centum_sync.stock_historial (
      id_sucursal, id_seccion_sucursal, id_articulo,
      existencias, cantidad_ordenes_compra, cantidad_pedidos_venta,
      stock_comprometido, stock_ideal, stock_minimo, stock_critico,
      stock_excesivo, tipo_cambio, observado_en, id_ejecucion
    )
    select
      id_sucursal, id_seccion_sucursal, id_articulo,
      existencias, cantidad_ordenes_compra, cantidad_pedidos_venta,
      stock_comprometido, stock_ideal, stock_minimo, stock_critico,
      stock_excesivo, tipo_cambio, p_observado_en, p_id_ejecucion
    from cambios
    returning 1
  ),
  actualizada as (
    insert into centum_sync.stock_actual (
      id_sucursal, id_seccion_sucursal, id_articulo,
      existencias, cantidad_ordenes_compra, cantidad_pedidos_venta,
      stock_comprometido, stock_ideal, stock_minimo, stock_critico,
      stock_excesivo, codigo_articulo_propio_sucursal,
      es_deposito_central, observado_en, id_ejecucion_ultima, actualizado_en
    )
    select
      id_sucursal, id_seccion_sucursal, id_articulo,
      existencias, cantidad_ordenes_compra, cantidad_pedidos_venta,
      stock_comprometido, stock_ideal, stock_minimo, stock_critico,
      stock_excesivo, codigo_articulo_propio_sucursal,
      id_sucursal = 6455, p_observado_en, p_id_ejecucion, now()
    from deduplicada
    on conflict (id_sucursal, id_seccion_sucursal, id_articulo) do update set
      existencias = excluded.existencias,
      cantidad_ordenes_compra = excluded.cantidad_ordenes_compra,
      cantidad_pedidos_venta = excluded.cantidad_pedidos_venta,
      stock_comprometido = excluded.stock_comprometido,
      stock_ideal = excluded.stock_ideal,
      stock_minimo = excluded.stock_minimo,
      stock_critico = excluded.stock_critico,
      stock_excesivo = excluded.stock_excesivo,
      codigo_articulo_propio_sucursal =
        excluded.codigo_articulo_propio_sucursal,
      es_deposito_central = excluded.es_deposito_central,
      observado_en = excluded.observado_en,
      id_ejecucion_ultima = excluded.id_ejecucion_ultima,
      actualizado_en = now()
    returning 1
  )
  select
    (select count(*)::integer from deduplicada),
    (select count(*)::integer from historial)
  into v_normalizados, v_cambios;

  insert into centum_sync.stock_lotes (
    id_ejecucion, id_sucursal, estado,
    registros_recibidos, registros_normalizados, cambios_registrados,
    procesado_en, mensaje_error
  ) values (
    p_id_ejecucion, p_id_sucursal, 'procesado',
    v_recibidos, v_normalizados, v_cambios, now(), null
  )
  on conflict (id_ejecucion, id_sucursal) do update set
    estado = 'procesado',
    registros_recibidos = excluded.registros_recibidos,
    registros_normalizados = excluded.registros_normalizados,
    cambios_registrados = excluded.cambios_registrados,
    procesado_en = now(),
    mensaje_error = null;

  select
    count(*) filter (where lote.estado = 'procesado')::integer
  into v_sucursales_procesadas
  from centum_sync.stock_lotes lote
  where lote.id_ejecucion = p_id_ejecucion;

  update centum_sync.stock_ejecuciones e
  set
    sucursales_procesadas = resumen.sucursales,
    registros_recibidos = resumen.recibidos,
    registros_normalizados = resumen.normalizados,
    cambios_registrados = resumen.cambios,
    estado = case
      when resumen.sucursales = e.sucursales_esperadas
        then 'completada'
      else 'iniciada'
    end,
    finalizada_en = case
      when resumen.sucursales = e.sucursales_esperadas then now()
      else null
    end
  from (
    select
      count(*) filter (where lote.estado = 'procesado')::integer as sucursales,
      coalesce(sum(lote.registros_recibidos), 0)::integer as recibidos,
      coalesce(sum(lote.registros_normalizados), 0)::integer as normalizados,
      coalesce(sum(lote.cambios_registrados), 0)::integer as cambios
    from centum_sync.stock_lotes lote
    where lote.id_ejecucion = p_id_ejecucion
  ) resumen
  where e.id_ejecucion = p_id_ejecucion;

  return query select
    v_recibidos,
    v_normalizados,
    v_cambios,
    v_sucursales_procesadas = p_sucursales_esperadas;
end;
$$;

comment on table centum_sync.stock_actual is
  'Último stock conocido por sucursal, sección y artículo; 6455 es depósito central.';

comment on table centum_sync.stock_historial is
  'Historial de estados iniciales y cambios reales de stock; no copia estados idénticos.';

commit;
