# Migración desde Dash Estados de Resultados

## Decisión

El 24 de julio de 2026 se decidió pausar el desarrollo independiente del dashboard de Estado de Resultados y consolidar en `centum-reposicion` la información reutilizable de ventas y de la API de Centum.

No se fusionaron los historiales Git. La migración fue selectiva para no reemplazar implementaciones vigentes con versiones iniciales ya superadas.

Repositorio de origen:

```text
LOCOSLOS/Dash-Estados-De-Resultados
```

Repositorio canónico:

```text
LOCOSLOS/centum-reposicion
```

## Inventario del origen

| Archivo original | Clasificación | Destino/decisión |
|---|---|---|
| `API Pública.pdf` | Referencia oficial reutilizable | Copia local excluida de Git por ser documentación de un tercero |
| `API Pública - Anexo Ejemplos.pdf` | Referencia oficial reutilizable | Copia local excluida de Git por ser documentación de un tercero |
| `n8n-workflow-sync-ventas.json` | Workflow anterior | Evaluado y descartado; copia histórica local no publicada |
| `sql/create_ventas_items.sql` | Esquema anterior | Evaluado y descartado; copia histórica local no publicada |
| `README.md` | Contexto mínimo del dashboard | Sin información técnica reutilizable |

## Motivo para no reutilizar el SQL anterior

El esquema inicial definía:

```text
unique (id_venta, id_articulo)
```

La validación con datos reales demostró que un mismo artículo puede aparecer varias veces dentro del mismo comprobante. Esa restricción sobrescribía líneas legítimas y subestimaba las ventas.

La versión 2 utiliza una clave idempotente que incorpora división, sucursal, venta y ordinal de línea, además de conservar el item original para auditoría.

## Motivo para no importar el workflow anterior

El workflow original tenía 8 nodos y escribía directamente en las tablas iniciales. La versión canónica tiene 11 nodos y agrega:

- inicialización y registro de la ejecución;
- generación controlada de consultas;
- preservación del contexto por división y sucursal;
- ingesta por lotes mediante función SQL;
- ordinal de línea;
- finalización y auditoría de la ejecución;
- zona horaria explícita de Buenos Aires.

La fuente vigente es [`../n8n/workflows/Centum_Sync_Ventas_Diario_v2.json`](../n8n/workflows/Centum_Sync_Ventas_Diario_v2.json).

## Uso de ventas dentro de reposición

La ingesta diaria de ventas deja de considerarse infraestructura exclusiva del dashboard financiero. Es una fuente central del motor de reposición:

```text
Centum
  ├─ ventas diarias → Supabase → demanda histórica y forecasting
  ├─ stock diario → Supabase → disponibilidad por sucursal
  └─ reporte de inventario → Excel y correo operativo
```

Las ventas conservan notas de crédito y cantidades negativas. Los cálculos posteriores deben distinguir ventas positivas, devoluciones y unidades netas.

## Estado posterior a la migración

- La versión 2 de ventas permanece como fuente canónica.
- El inventario de manuales de Centum queda documentado; los PDF permanecen como referencias locales no publicadas.
- Los artefactos anteriores se conservan únicamente para trazabilidad.
- El repositorio de origen no fue modificado ni eliminado durante la migración.
- El archivo o eliminación del repositorio de origen requiere una decisión posterior.

## Referencias

- [Estado de datos](ESTADO_DATOS.md)
- [Implementación de ventas v2](IMPLEMENTACION_V2_VENTAS.md)
- [Revisión del workflow de ventas](REVISION_WORKFLOW_VENTAS.md)
- [Validación real de la ingesta v2](VALIDACION_INGESTA_V2_2026-07-22.md)
- [Backfill de ventas](BACKFILL_VENTAS_V2.md)
