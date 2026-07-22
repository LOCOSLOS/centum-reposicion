# Implementación paralela de ventas v2

Última actualización: 22 de julio de 2026.

Esta versión permite validar una ingesta más robusta sin modificar ni detener el workflow diario actual. La preparación del repositorio no ejecuta cambios en Supabase ni en n8n.

## Qué resuelve

- guarda `id_division` e `id_sucursal` en todas las cabeceras y líneas;
- registra cada ejecución y cada consulta a Centum;
- conserva la respuesta completa de cada lote para auditoría;
- usa una clave de cabecera compuesta por división, sucursal e `id_venta`;
- identifica cada línea por su posición original dentro del comprobante, sin suponer que `id_venta + id_articulo` siempre será único;
- procesa una respuesta completa con una sola llamada a PostgreSQL;
- permite repetir la misma ejecución sin duplicar los datos.

La posición de la línea es reproducible mientras Centum devuelva los artículos del comprobante en el mismo orden. También se conserva un posible identificador nativo (`IdVentaArticulo`, `IdVentaItem` o `Id`) y el JSON completo de cada línea para migrar a una clave mejor si la API la expone.

## Archivos

- `supabase/migrations/001_ventas_v2_paralela.sql`: tablas paralelas y función de ingesta;
- `n8n/workflows/Centum_Sync_Ventas_Diario_v2.json`: workflow importable, inactivo y sin credenciales.

## Instalación controlada

### 1. Crear las tablas paralelas

1. Abrir el proyecto correcto en Supabase.
2. Ir a **SQL Editor** y crear una consulta nueva.
3. Copiar todo el contenido de `supabase/migrations/001_ventas_v2_paralela.sql`.
4. Ejecutarlo una sola vez.
5. Verificar que aparezcan estas tablas en el esquema `centum_sync`:
   - `carga_ejecuciones_v2`;
   - `ventas_lotes_v2`;
   - `ventas_raw_v2`;
   - `ventas_items_v2`.

La migración no elimina ni altera `public.ventas_raw`, `public.ventas_items` ni el maestro de artículos.

### 2. Importar el workflow

1. En n8n, seleccionar **Import from File**.
2. Elegir `n8n/workflows/Centum_Sync_Ventas_Diario_v2.json`.
3. Asignar manualmente la credencial existente de Centum al nodo `TOKEN`.
4. Asignar la credencial existente de Supabase/Postgres a los tres nodos PostgreSQL.
5. Mantener el workflow **inactivo**.

El archivo no incluye identificadores de credenciales ni secretos.

### 3. Primera prueba recomendada

Ejecutar manualmente una sola combinación de sucursal/división y un solo día. Para hacerlo, fijar temporalmente el límite del nodo `Genera Consultas` a un elemento o dejar una sola sucursal en su lista. No activar aún el cron.

Comprobar el resultado con:

```sql
select *
from centum_sync.carga_ejecuciones_v2
order by iniciada_en desc
limit 5;

select
  id_ejecucion,
  id_division,
  id_sucursal,
  estado,
  comprobantes,
  lineas
from centum_sync.ventas_lotes_v2
order by recibido_en desc
limit 30;
```

Comparar v1 y v2 para la combinación probada. El ejemplo usa `Endron Prueba`, sucursal `01` y división `2`:

```sql
with v1 as (
  select
    count(distinct (sociedad, id_sucursal, id_venta)) as comprobantes,
    count(*) as lineas,
    coalesce(sum(cantidad), 0) as unidades_netas
  from public.ventas_items
  where fecha_comprobante = date '2026-07-21'
    and sociedad = 'Endron Prueba'
    and id_sucursal = 6455
),
v2 as (
  select
    count(distinct (id_division, id_sucursal, id_venta)) as comprobantes,
    count(*) as lineas,
    coalesce(sum(cantidad), 0) as unidades_netas
  from centum_sync.ventas_items_v2
  where fecha_comprobante = date '2026-07-21'
    and id_division = 2
    and id_sucursal = 6455
)
select 'v1' as version, * from v1
union all
select 'v2' as version, * from v2;
```

Cambiar la fecha, sociedad, división y sucursal del ejemplo por la combinación efectivamente probada. Las cantidades negativas deben permanecer como devoluciones y el SKU `Envio` sigue presente en ventas; su exclusión se hará únicamente en las futuras vistas de reposición.

## Criterio para avanzar

No activar ni usar esta versión para el backfill hasta comprobar al menos:

- misma cantidad de comprobantes, líneas y unidades que la carga actual para varios días;
- separación correcta de `Endron Prueba` por sucursal;
- reejecución idempotente del mismo día;
- comportamiento de comprobantes con dos líneas del mismo artículo;
- volumen y tiempo de ejecución aceptables.

El workflow actual debe permanecer activo hasta completar estas validaciones.

