# Persistencia histórica de órdenes de traspaso

Fecha de validación: 5 de agosto de 2026.

## Resultado

El issue #4 quedó implementado y validado con datos reales. El workflow manual
`4B0rMSpQjslHoulA`, `ODT - Despachos Drive - Lectura y Validación (MANUAL)`,
continúa inactivo y ahora persiste snapshots idempotentes en Supabase.

El flujo conserva sus dos fuentes de Google Drive:

- `OT Stock en Transito V2.csv`;
- `ODTEfectivas35Dias.csv`.

La clave canónica es `NumeroDocumento + Clave`. Para el reporte de stock en
tránsito, la cantidad pendiente se valida siempre como:

```text
max(cantidad_despachada - cantidad_recibida, 0)
```

## Modelo instalado en Supabase

La migración [`../supabase/migrations/004_odt_snapshots.sql`](../supabase/migrations/004_odt_snapshots.sql)
crea:

- `centum_sync.odt_ejecuciones`: estado de cada corrida del workflow;
- `centum_sync.odt_importaciones`: una fila por contenido distinto de cada
  reporte;
- `centum_sync.odt_ejecucion_importaciones`: vínculo entre una ejecución y sus
  dos snapshots;
- `centum_sync.odt_documentos`: totales por documento dentro de cada snapshot;
- `centum_sync.odt_detalle`: detalle por `NumeroDocumento + Clave`;
- `centum_sync.ingestar_snapshot_odt(...)`: función transaccional e idempotente;
- `centum_sync.vw_odt_control_por_ejecucion`: cruce reproducible entre tránsito
  y efectivas;
- `centum_sync.vw_odt_stock_transiciones`: comparación de cada línea contra su
  snapshot anterior.

La huella se calcula sobre el contenido normalizado y ordenado. Si los archivos
no cambiaron, una nueva ejecución se vincula a las importaciones existentes y
no duplica documentos ni líneas.

## Workflow definitivo

La secuencia final agrega, después del cruce validado:

```text
Cruzar y resumir ODT
  → Execute a SQL query
  → Code in JavaScript
```

El primer nodo prepara dos llamadas a `ingestar_snapshot_odt(...)`, una por
reporte. El nodo Postgres utiliza la credencial ya configurada en n8n. El último
nodo exige que ambos reportes hayan sido procesados antes de devolver el control
como completado.

Después de retirar los nodos temporales de instalación y auditoría, la versión
guardada en n8n quedó con 18 nodos funcionales, 2 notas y 18 conexiones. La nota
interna también fue actualizada para aclarar que existe persistencia histórica.
El workflow sigue siendo exclusivamente manual e inactivo. La exportación exacta
se conserva en
[`../n8n/workflows/ODT_Despachos_Drive_Lectura_y_Validacion_MANUAL.json`](../n8n/workflows/ODT_Despachos_Drive_Lectura_y_Validacion_MANUAL.json).

## Datos de la prueba

Los dos CSV superaron nuevamente sus validaciones previas:

| Reporte | Líneas | Documentos | Resultado relevante |
| --- | ---: | ---: | --- |
| Stock en tránsito | 351 | 46 | 351 despachadas, 28 recibidas, 323 pendientes |
| ODT efectivas 35 días | 15.608 | 1.184 | 14.234 líneas con recepción confirmada |

### Primera carga válida

- ejecución n8n/Supabase: `2033`;
- estado: `completada`;
- reportes procesados: `2`;
- importaciones nuevas: `2`;
- importaciones reutilizadas: `0`;
- stock en tránsito: importación `2`;
- ODT efectivas: importación `3`.

### Repetición sin cambios

- ejecución n8n/Supabase: `2034`;
- estado: `completada`;
- reportes procesados: `2`;
- importaciones nuevas: `0`;
- importaciones reutilizadas: `2`;
- ambos reportes reutilizaron las importaciones `2` y `3` con
  `importacion_nueva = false`.

La segunda corrida demuestra la idempotencia requerida: no se crearon snapshots,
documentos ni líneas duplicadas.

## Control operativo

El control liviano queda en
[`../supabase/audits/009_validacion_odt_snapshots.sql`](../supabase/audits/009_validacion_odt_snapshots.sql).
Verifica:

- última ejecución completada con dos reportes;
- ausencia de claves duplicadas;
- igualdad `pendiente = max(despachado - recibido, 0)`;
- ausencia de líneas huérfanas;
- volumen acumulado e historial de idempotencia.

Con este resultado, la persistencia histórica de órdenes de traspaso queda
completada. El próximo frente funcional es continuar la validación del modelo
de forecasting y reposición usando ventas, stock y traspasos persistidos.
