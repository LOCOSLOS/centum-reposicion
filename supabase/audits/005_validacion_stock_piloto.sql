-- Validación del piloto de stock para Casa Central (6455).

select
  id_ejecucion,
  estado,
  sucursales_esperadas,
  sucursales_procesadas,
  registros_recibidos,
  registros_normalizados,
  cambios_registrados,
  iniciada_en,
  finalizada_en,
  mensaje_error
from centum_sync.stock_ejecuciones
order by iniciada_en desc
limit 5;

select
  id_sucursal,
  count(*) as filas_actuales,
  count(distinct id_articulo) as articulos,
  count(distinct id_seccion_sucursal) as secciones,
  count(*) filter (where existencias = 0) as filas_en_cero,
  count(*) filter (where existencias < 0) as filas_negativas,
  sum(existencias) as existencias_totales,
  bool_and(es_deposito_central) as marcado_como_deposito
from centum_sync.stock_actual
where id_sucursal = 6455
group by id_sucursal;

select
  id_articulo,
  count(*) as secciones,
  sum(existencias) as existencias_totales
from centum_sync.stock_actual
where id_sucursal = 6455
group by id_articulo
having count(*) > 1
order by secciones desc, id_articulo
limit 50;

select
  tipo_cambio,
  count(*) as filas
from centum_sync.stock_historial
where id_sucursal = 6455
group by tipo_cambio
order by tipo_cambio;
