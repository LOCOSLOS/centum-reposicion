# Operación y validación diaria del stock

## Operación normal

El workflow `QKKdZL5xHFVNkiFh` comienza todos los días a las 03:00 ART. Una ejecución completa tarda aproximadamente 12 minutos con el volumen validado de julio de 2026.

No es necesario abrir el editor de n8n durante una corrida normal. La fuente de verdad para confirmar el resultado es Supabase, no el estado visual de la ejecución.

## Control rápido

```sql
select
  id_ejecucion,
  estado,
  sucursales_esperadas,
  sucursales_procesadas,
  registros_recibidos,
  registros_normalizados,
  cambios_registrados,
  iniciada_en at time zone 'America/Argentina/Buenos_Aires' as iniciada_art,
  finalizada_en at time zone 'America/Argentina/Buenos_Aires' as finalizada_art,
  mensaje_error
from centum_sync.stock_ejecuciones
order by iniciada_en desc
limit 10;
```

Resultado esperado para la corrida más reciente:

- `estado = completada`;
- `sucursales_esperadas = 12`;
- `sucursales_procesadas = 12`;
- `registros_recibidos = registros_normalizados`;
- `finalizada_en` no nulo;
- `mensaje_error` nulo.

## Control por sucursal

Reemplazar `<ID_EJECUCION>` por el ID de n8n:

```sql
select
  id_sucursal,
  estado,
  registros_recibidos,
  registros_normalizados,
  cambios_registrados,
  procesado_en at time zone 'America/Argentina/Buenos_Aires' as procesado_art,
  mensaje_error
from centum_sync.stock_lotes
where id_ejecucion = '<ID_EJECUCION>'
order by id_sucursal;
```

Debe devolver exactamente estos 12 IDs:

```text
6084, 6455, 6457, 6458, 6761, 8774,
9254, 9258, 9281, 9292, 9302, 9308
```

## Control consolidado de integridad

```sql
with ultima as (
  select id_ejecucion
  from centum_sync.stock_ejecuciones
  order by iniciada_en desc
  limit 1
)
select
  e.id_ejecucion,
  e.estado,
  e.sucursales_esperadas,
  e.sucursales_procesadas,
  count(l.*) as lotes,
  count(*) filter (where l.estado = 'procesado') as lotes_procesados,
  count(*) filter (where l.estado = 'con_error') as lotes_con_error,
  sum(l.registros_recibidos) as registros_recibidos_lotes,
  sum(l.registros_normalizados) as registros_normalizados_lotes,
  sum(l.cambios_registrados) as cambios_lotes
from ultima u
join centum_sync.stock_ejecuciones e using (id_ejecucion)
left join centum_sync.stock_lotes l using (id_ejecucion)
group by
  e.id_ejecucion,
  e.estado,
  e.sucursales_esperadas,
  e.sucursales_procesadas;
```

Los totales de lotes deben coincidir con la cabecera.

## Control de vigencia de `stock_actual`

```sql
select
  id_sucursal,
  count(*) as filas,
  min(observado_en) at time zone 'America/Argentina/Buenos_Aires' as primera_observacion_art,
  max(observado_en) at time zone 'America/Argentina/Buenos_Aires' as ultima_observacion_art,
  count(distinct id_ejecucion_ultima) as ejecuciones_presentes
from centum_sync.stock_actual
group by id_sucursal
order by id_sucursal;
```

Esta consulta ayuda a detectar una sucursal que no haya sido actualizada recientemente. Después de una ejecución completa, cada sucursal debe presentar una sola ejecución vigente y una fecha de observación correspondiente a esa corrida, porque la función hace upsert de todas las filas aunque el historial solo registre cambios reales.

## Ejecución manual

Una ejecución manual solo corresponde cuando:

- faltó una corrida automática;
- una ejecución quedó parcial;
- se modificó el workflow y existe un plan de validación;
- se requiere una recuperación aprobada.

Antes de ejecutarla:

1. Confirmar que no haya otra corrida en curso.
2. Revisar el último registro de `stock_ejecuciones`.
3. Registrar el motivo de la intervención.
4. Ejecutar una sola vez.
5. Validar cabecera y 12 lotes en Supabase.

La función es idempotente respecto de `stock_actual`; aun así, no se deben lanzar reejecuciones innecesarias porque generan carga sobre Centum, n8n y Postgres.

## Recuperación de una corrida parcial

No borrar filas ni recargar a ciegas.

1. Identificar el ID de ejecución parcial.
2. Consultar `stock_lotes` y determinar las sucursales faltantes.
3. Confirmar si una ejecución completa posterior ya reemplazó el estado.
4. Si existe una ejecución posterior completa, conservar la parcial como auditoría.
5. Si no existe, preparar una recuperación controlada y obtener aprobación antes de escribir.

## Cambios al workflow

Antes de cambiar nodos, horarios o sucursales:

1. Exportar un respaldo JSON.
2. Mantener el workflow inactivo durante cambios estructurales.
3. No modificar simultáneamente el flujo Excel.
4. Probar primero de forma controlada.
5. Validar datos en Supabase.
6. Activar solo después de una confirmación explícita.

Las credenciales deben permanecer exclusivamente en n8n o en archivos locales ignorados por Git.
