# Implementación productiva de stock

## Estado actual

La captura diaria de stock funciona como un proceso independiente del reporte Excel.

| Función | Workflow | ID | Horario | Estado |
|---|---|---|---|---|
| Persistencia en Supabase | `Centum → Supabase: Sync Stock Diario` | `QKKdZL5xHFVNkiFh` | 03:00 ART | Activo |
| Excel y correo | `Reporte Inventario Centum - v8 con datatable` | `p5IRTMnkXfXe75TQ` | 05:00 ART | Activo |

Ambos procesos consultan Centum de forma independiente. Esta duplicación diaria es intencional: evita que un problema de memoria, generación del Excel o envío de correo afecte la captura utilizada por el sistema de reposición.

La zona horaria configurada en n8n es `America/Argentina/Buenos_Aires`.

## Decisión de arquitectura

Se probó un workflow integrado, `35lPkl3rmDXcG0iD`, que compartía una misma respuesta de Centum entre Excel y Supabase. La escritura de stock finalizaba correctamente, pero la ejecución completa podía permanecer en `running` durante horas debido al volumen retenido por el procesamiento combinado.

La ejecución `1836` demostró el comportamiento:

- Supabase completó las 12 sucursales a las 04:12:54 ART;
- se guardaron 923.892 registros;
- se registraron 586 cambios reales;
- n8n continuó mostrando la ejecución como activa hasta su cancelación manual cuatro horas después.

El workflow integrado fue descartado y eliminado. No debe reconstruirse ni utilizarse como referencia productiva.

## Flujo productivo de Supabase

```text
Trigger diario 03:00 ART / Trigger manual
  → Code - Lista sucursales
  → Loop Over Sucursales
      → Token pag1 sucursal
      → Normaliza Token pag1 sucursal
      → HTTP pag1 por sucursal
      → Prepara Stock Supabase
      → Postgres - Persiste Stock Piloto
      → Loop Over Sucursales
```

El loop procesa una sucursal por vez. Postgres controla el retorno al loop; no existe una segunda rama de retorno.

## Alcance funcional

Se procesan 12 sucursales físicas:

`6455`, `6457`, `6084`, `6761`, `6458`, `8774`, `9254`, `9258`, `9281`, `9292`, `9302` y `9308`.

- `6455 - 01 Casa Central` es el depósito central.
- `21 - Mayorista` queda excluida.
- El stock físico es compartido y no se separa por sociedad o división.
- Se conservan existencias positivas, iguales a cero y negativas.
- La clave de stock es sucursal, sección de sucursal y artículo.

## Persistencia

La migración [`003_stock_snapshot.sql`](../supabase/migrations/003_stock_snapshot.sql) crea:

- `centum_sync.stock_ejecuciones`: estado general y totales de cada ejecución;
- `centum_sync.stock_lotes`: resultado individual por sucursal;
- `centum_sync.stock_actual`: último estado conocido;
- `centum_sync.stock_historial`: estados iniciales y cambios reales;
- `centum_sync.ingestar_stock_snapshot(...)`: función transaccional de ingesta.

`stock_actual` utiliza esta clave:

```text
id_sucursal + id_seccion_sucursal + id_articulo
```

Una reejecución actualiza el estado existente y no duplica filas. El historial registra `inicial` para combinaciones nuevas y `cambio` cuando se modifica alguno de los valores controlados.

## Validaciones productivas

### Ejecución 1831 — 23 de julio de 2026

- estado SQL: `completada`;
- 12 sucursales procesadas;
- 12 lotes sin error;
- 923.892 registros recibidos y normalizados;
- 154.033 cambios registrados;
- 76.991 registros por sucursal.

### Ejecución 1836 — 24 de julio de 2026

- estado SQL: `completada`;
- 12 sucursales procesadas;
- 12 lotes sin error;
- 923.892 registros recibidos y normalizados;
- 586 cambios registrados;
- finalización SQL a las 04:12:54 ART.

Las dos ejecuciones confirmaron que no faltó stock durante el cambio de arquitectura.

## Documentación relacionada

- [Referencia técnica del workflow](WORKFLOW_STOCK_SUPABASE.md)
- [Operación y validación diaria](OPERACION_STOCK_SUPABASE.md)
- [Resolución de problemas](TROUBLESHOOTING_STOCK_SUPABASE.md)
