# Archivo histórico — Dash Estados de Resultados

Este directorio documenta los artefactos técnicos revisados del repositorio `LOCOSLOS/Dash-Estados-De-Resultados` el 24 de julio de 2026. Los archivos históricos permanecen disponibles solo en el entorno local de migración y están excluidos de Git para evitar publicar material obsoleto; pueden recuperarse desde el repositorio de origen cuando sea necesario.

## No utilizar en producción

- `create_ventas_items_ANTERIOR_NO_EJECUTAR.sql` contiene el esquema inicial de ventas con una restricción única por `id_venta + id_articulo`. Esa clave sobrescribe líneas legítimas cuando un artículo aparece más de una vez en el mismo comprobante.
- `n8n-workflow-sync-ventas_ANTERIOR_NO_IMPORTAR.json` es la versión anterior de la ingesta de ventas. No posee el modelo de auditoría, ordinal de línea ni finalización controlada de la versión 2.
- `README_ORIGINAL.md` conserva el README mínimo del repositorio de origen.

Las fuentes canónicas vigentes son:

- [`../../n8n/workflows/Centum_Sync_Ventas_Diario_v2.json`](../../n8n/workflows/Centum_Sync_Ventas_Diario_v2.json);
- [`../../supabase/migrations/001_ventas_v2_paralela.sql`](../../supabase/migrations/001_ventas_v2_paralela.sql);
- [`../../supabase/migrations/002_fuente_canonica_ventas.sql`](../../supabase/migrations/002_fuente_canonica_ventas.sql);
- [`../../docs/IMPLEMENTACION_V2_VENTAS.md`](../../docs/IMPLEMENTACION_V2_VENTAS.md).

Este archivo existe para trazabilidad y comparación histórica. No debe usarse como plantilla de despliegue.
