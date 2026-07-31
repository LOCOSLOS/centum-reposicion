# Plan de backfill de ventas — hasta julio de 2024

## Objetivo

Extender gradualmente el histórico canónico de ventas hasta alcanzar cobertura continua desde julio de 2024 hasta la actualidad. Este alcance aporta aproximadamente 24 meses de información, suficientes para comparar dos ciclos estacionales y evaluar el forecasting inicial.

El 31 de julio de 2026 se descartó el objetivo provisional de cinco años. El backfill debe detenerse al completar julio de 2024; no se cargarán períodos anteriores salvo que una evaluación posterior demuestre una mejora medible que lo justifique.

## Workflow

- ID: `hbcKc5ElvaAxpwYJ`
- Nombre: `Centum → Supabase: Backfill Ventas v2 (MANUAL)`
- Estado: inactivo
- Trigger: manual
- Triggers programados: ninguno
- Lotes esperados por ventana: 26

Este workflow ya existía y fue utilizado para los backfills validados de julio de 2026. No se creó una copia adicional.

## Primera ventana validada

```text
fechaDesde: 2026-05-18
fechaHasta: 2026-05-24
lotesEsperados: 26
```

La ejecución `1841` terminó correctamente con 26 de 26 lotes y sin errores. Se recibieron 2.891 comprobantes, de los cuales 2.849 tuvieron líneas y 42 no tuvieron detalle. Se almacenaron 6.382 líneas canónicas: 5.975 positivas y 407 negativas, equivalentes a 6.052 unidades vendidas, 412 devueltas y 5.640 netas.

La auditoría confirmó cero grupos duplicados y cero líneas fuera del rango. Centum no informó actividad para el 24 de mayo; la cobertura efectiva fue del 18 al 23 de mayo. Esta ausencia quedó documentada y no se completó con datos inventados.

Después de esta primera prueba se validaron también las ejecuciones `1842`, `1843` y `1844`. La cobertura continua alcanzó desde el 17 de abril hasta el 24 de mayo de 2026, siempre con 26 de 26 lotes, sin errores y sin registros fuera de rango.

## Secuencia de ampliación

1. Ejecutar y validar del 18 al 24 de mayo de 2026. **Completado.**
2. Repetir la misma ventana para confirmar idempotencia solo si aparecen diferencias inesperadas.
3. Completar y validar del 1 al 17 de mayo de 2026. **Completado.**
4. Continuar hacia atrás en ventanas controladas. **En curso.**
5. Completar la cobertura continua hasta incluir todo julio de 2024.
6. Detener el backfill y realizar una auditoría acumulada de los aproximadamente 24 meses cargados.
7. Comparar modelos con ventanas de 12, 18 y 24 meses antes de decidir cualquier ampliación futura.

No se deben preparar múltiples ejecuciones simultáneas. La fecha de la siguiente ventana solo se modifica después de validar la anterior. Al cierre del 31 de julio de 2026 la cobertura continua validada llega hasta el 24 de enero de 2025 mediante la ejecución `1949`. La próxima ventana pendiente es del 10 al 23 de enero de 2025 y todavía no está configurada. El límite final acordado es completar julio de 2024 y detenerse allí.

## Criterios por ventana

- ejecución en estado `completada`;
- 26 lotes esperados y procesados;
- cero lotes con error;
- rango almacenado igual al solicitado;
- líneas recibidas iguales a las registradas por la auditoría;
- ausencia de duplicados por la clave v2;
- conservación de artículos repetidos legítimamente;
- conservación de notas de crédito y cantidades negativas;
- explicación de cualquier documento corregido por Centum;
- estabilidad después de una reejecución idempotente cuando corresponda.

## Convivencia con procesos diarios

Procesos automáticos actuales:

```text
02:00 ART — ventas diarias v2
03:00 ART — stock diario a Supabase
05:00 ART — reporte Excel de inventario
```

Las ejecuciones de backfill son manuales y no deben superponerse con estos procesos. Antes de iniciar una ventana se debe comprobar que no haya otra ejecución de ventas o stock activa.

## Consultas de control

La validación base se encuentra en [`../supabase/audits/004_validacion_ventana_backfill.sql`](../supabase/audits/004_validacion_ventana_backfill.sql).

También se debe revisar la cabecera:

```sql
select
  id_ejecucion,
  modo,
  fecha_desde,
  fecha_hasta,
  estado,
  lotes_esperados,
  lotes_procesados,
  comprobantes_procesados,
  lineas_procesadas,
  iniciada_en,
  finalizada_en,
  mensaje_error
from centum_sync.carga_ejecuciones_v2
where modo = 'backfill_piloto'
order by iniciada_en desc;
```

Los totales de comprobantes y líneas deben coincidir con la suma de los lotes de la misma ejecución.

## Respaldos

Antes de preparar la primera ventana histórica se exportaron:

- `n8n/workflows/Backfill_Ventas_v2_pre_historico_2026-07-24.json`;
- `n8n/workflows/Backfill_Ventas_v2_2026-05-18_a_2026-05-24.json`.

Las exportaciones contienen referencias a credenciales de n8n, no sus valores secretos. No deben editarse para insertar credenciales.

La configuración vigente del workflow manual también se conserva en:

- `n8n/workflows/Centum_Backfill_Ventas_v2_manual_actual.json`.

El nodo `Obtiene Ventas` tiene reintentos habilitados: tres intentos con diez segundos de espera. El workflow permanece inactivo y se ejecuta exclusivamente de forma manual.

## Límites y señales para detenerse

Pausar la expansión si ocurre cualquiera de estos casos:

- Centum no devuelve períodos antiguos;
- aparecen meses o sucursales sistemáticamente vacíos;
- cambia el contrato de respuesta;
- los tiempos crecen de forma no lineal;
- aparecen diferencias sin explicación contra ventanas solapadas;
- se observan errores recurrentes o presión excesiva sobre n8n/Postgres;
- cambian las divisiones o sucursales históricas y se requiere modelarlas explícitamente.

No se deben inventar sucursales, divisiones ni equivalencias históricas sin evidencia de Centum.
