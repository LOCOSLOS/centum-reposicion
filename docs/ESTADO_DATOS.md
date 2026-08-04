# Estado de datos

Última actualización: 4 de agosto de 2026.

La validación del piloto de forecasting, la lectura de órdenes de traspaso,
la continuidad del stock diario y los próximos pasos están consolidados en
[`AVANCE_2026-08-04.md`](AVANCE_2026-08-04.md).

Este documento registra únicamente hechos confirmados, decisiones de trabajo y validaciones pendientes. No debe contener credenciales, respuestas completas de producción ni información comercial sensible.

## Fuentes y flujos existentes

- Centum es el sistema de gestión de origen.
- El inventario de manuales de la API pública de Centum está documentado en [`docs/references/centum-api/`](references/centum-api/); los PDF se conservan localmente y no se publican por ser material de un tercero.
- n8n ejecuta flujos que extraen información de Centum.
- Los flujos actuales de artículos y ventas guardan sus resultados en Supabase.
- Existe un flujo de existencias que actualmente genera un reporte, pero todavía no persiste el resultado en una tabla.
- El stock en tránsito no está disponible mediante la API de Centum. Se obtiene desde un archivo CSV que ya consume la herramienta operativa existente.
- La arquitectura original contemplaba Neon Postgres. Queda pendiente decidir si el MVP se consolida en Supabase o si se mantiene Neon como destino final, evitando duplicar información entre ambas plataformas.

## Maestro de artículos

Información disponible:

- `id_articulo`;
- rubro;
- subrubro;
- `sku`;
- descripción del artículo;
- grupo de artículo.

Validaciones confirmadas:

- `id_articulo` es estable y único;
- `sku` es único;
- todas las ventas encuentran su artículo correspondiente en el maestro.

La descripción permite obtener talle y color. Para evitar interpretar el texto en cada consulta, se prevé normalizar ambos atributos y conservar la descripción original. El método de extracción y sus excepciones todavía deben validarse con datos reales.

## Ventas

Estructura recibida el 22 de julio de 2026:

- `public.ventas_raw`: cabecera del comprobante, importes, tipo y número de comprobante, datos de sucursal y respuesta original en `raw_data` (`jsonb`);
- `public.ventas_items`: líneas del comprobante con artículo, código, descripción, cantidad, precios, descuento, IVA, costo de reposición y sucursal;
- `centum_sync.maestro_articulos`: maestro de artículos con `id_articulo` (`bigint`, obligatorio), `rubro`, `subrubro`, `updated_at`, `sku`, `descripcion` y `grupo_articulo`.

El identificador del maestro es `bigint`, mientras que `public.ventas_items.id_articulo` es `integer`. PostgreSQL puede realizar la unión mediante una conversión segura a `bigint`, pero el modelo canónico deberá utilizar un mismo tipo para evitar inconsistencias futuras. Aunque `sku` fue confirmado funcionalmente como único, la columna admite valores nulos; la auditoría debe comprobar nulos y duplicados antes de agregar una restricción.

La muestra recibida confirma que `grupo_articulo` representa el modelo base y que muchas descripciones incluyen marcadores `C:<color>` y `T:<talle>`. Ambos atributos son opcionales y no tenerlos no implica un error. La vista no destructiva los separa cuando existen, admite cualquier orden y clasifica los artículos como `con_color_y_talle`, `solo_color`, `solo_talle`, `sin_variantes_declaradas` o `sin_descripcion`.

Información disponible:

- identificador interno de Supabase;
- `id_venta`;
- `id_articulo`;
- período;
- sociedad;
- fecha del comprobante;
- `sku`;
- descripción;
- cantidad vendida;
- precio final;
- precio neto;
- costo de reposición;
- `id_sucursal`;
- nombre de la sucursal.

Validaciones confirmadas:

- `id_venta` identifica el comprobante completo;
- un comprobante contiene varias líneas y, por lo tanto, varias filas pueden compartir el mismo `id_venta`;
- el histórico actualmente almacenado comienza el 25 de mayo de 2026;
- Centum permite cargar períodos anteriores mediante ejecuciones adicionales.

### Resultado de la auditoría inicial

Auditoría ejecutada el 22 de julio de 2026:

- 20.513 comprobantes y 43.364 líneas de venta;
- cobertura desde el 25 de mayo hasta el 21 de julio de 2026;
- cero comprobantes duplicados;
- cero repeticiones de `id_venta + id_articulo` dentro de la sociedad y sucursal;
- cero líneas con cantidad igual a cero;
- 2.550 líneas con cantidad negativa, todas correspondientes a notas de crédito de venta;
- `NCV-B`: 1.991 comprobantes, 2.543 líneas y 2.560 unidades negativas;
- `NCV-A`: 5 comprobantes, 7 líneas y 7 unidades negativas;
- 76.949 artículos en el maestro, sin SKU nulos ni duplicados;
- cero líneas de venta sin correspondencia en el maestro;
- 38.106 artículos con color y talle declarados;
- 32.903 artículos con sólo talle declarado;
- 5.868 artículos sin variantes declaradas;
- 72 artículos con sólo color declarado;
- cero textos con indicadores de codificación incorrecta en la base.

La deformación observada como `NiÃ±o` y `PaÃ±o` se produjo al copiar o mostrar la muestra, no está presente en Supabase. La ausencia de marcadores de color o talle es válida para productos que no manejan esas variantes y no debe contabilizarse como un problema de calidad. Las cuatro categorías de variantes suman exactamente los 76.949 artículos del maestro.

Las cantidades negativas se conservarán como devoluciones/notas de crédito. Las vistas deben exponer por separado unidades positivas, unidades devueltas en valor absoluto y unidades netas. No se deben eliminar ni invertir estos movimientos en la fuente.

La primera carga contiene 1.199 líneas del 25 y 26 de mayo de 2026 sin `id_sucursal`, equivalentes a 1.137 unidades vendidas y 70 devueltas. La sucursal tampoco puede recuperarse desde `ventas_raw`. Estas líneas se conservarán para auditoría y totales generales, pero se excluirán de cualquier cálculo por local. El análisis confiable por sucursal comienza el 27 de mayo de 2026 y contiene 42.165 filas almacenadas, consolidadas en 40.629 filas diarias por artículo y sucursal.

La validación de la ingesta v2 demostró que la tabla anterior no conserva todas las líneas originales. Para el 17 de julio de 2026, Centum devolvió 792 líneas y `public.ventas_items` conservó 778. Las 14 líneas faltantes corresponden a artículos que aparecen dos veces dentro del mismo comprobante: 13 unidades vendidas y una unidad devuelta. La clave anterior `id_venta + id_articulo` sobrescribía una aparición; la v2 preserva ambas mediante `linea_ordinal`. Por lo tanto, los conteos históricos de `public.ventas_items` deben considerarse potencialmente subestimados hasta completar el backfill desde Centum.

Validaciones pendientes:

- medir la pérdida histórica causada por repeticiones de `id_venta + id_articulo` mediante el backfill v2;
- confirmar si Centum expone un identificador estable de línea; mientras tanto se utiliza el ordinal original y se conserva `raw_item`;
- confirmar si existen anulaciones con un tratamiento diferente a las notas de crédito;
- detectar duplicados generados por reejecuciones;
- verificar períodos incompletos por sociedad y sucursal;
- definir el alcance del backfill histórico. Como referencia inicial se consideran 12 meses como mínimo y 24 meses como período preferible para indumentaria.

La v2 ya dispone de una clave idempotente provisional por división, sucursal, venta y ordinal. El backfill debe realizarse de manera controlada, por ventanas acotadas y con conciliación, antes de considerar a la v2 como fuente canónica.

## Existencias

> Actualización del 24 de julio de 2026: la persistencia ya está implementada. El diseño preliminar que aparece al final de esta sección se conserva únicamente como antecedente y quedó reemplazado por la arquitectura siguiente.

La captura de existencias funciona de manera independiente del reporte Excel:

```text
03:00 ART — Centum → Supabase
05:00 ART — Centum → Excel → correo
```

El workflow productivo de Supabase es `QKKdZL5xHFVNkiFh`. Procesa 12 sucursales, una por vez, y conserva stock positivo, cero y negativo. Casa Central (`6455`) queda identificada como depósito.

La ejecución validada `1836` almacenó 923.892 registros, 12 lotes sin error y 586 cambios reales. Supabase finalizó a las 04:12:54 ART del 24 de julio de 2026.

El modelo implementado contiene:

- `centum_sync.stock_actual`, con una fila por sucursal, sección y artículo;
- `centum_sync.stock_historial`, limitado a estados iniciales y cambios efectivos;
- `centum_sync.stock_ejecuciones`, con el estado general de cada corrida;
- `centum_sync.stock_lotes`, con el resultado de cada sucursal;
- fecha de observación e ID de ejecución;
- conservación explícita de stock cero y negativo.

La arquitectura integrada Excel + Supabase fue descartada porque, aunque SQL terminaba correctamente, n8n podía permanecer ejecutando durante horas por el volumen combinado. Los dos flujos independientes son la arquitectura productiva definitiva.

Referencias vigentes:

- [`IMPLEMENTACION_STOCK.md`](IMPLEMENTACION_STOCK.md);
- [`WORKFLOW_STOCK_SUPABASE.md`](WORKFLOW_STOCK_SUPABASE.md);
- [`OPERACION_STOCK_SUPABASE.md`](OPERACION_STOCK_SUPABASE.md);
- [`TROUBLESHOOTING_STOCK_SUPABASE.md`](TROUBLESHOOTING_STOCK_SUPABASE.md).

### Diseño preliminar histórico — reemplazado

El flujo actual ya obtiene las existencias necesarias para producir un reporte. El próximo cambio previsto es agregar una rama de persistencia sin alterar la salida actual:

```text
Centum → normalización de existencias
                    ├─→ reporte actual
                    └─→ persistencia en Supabase
```

Diseño preliminar sujeto a validar el volumen y las columnas reales:

- una tabla de stock actual con una fila por sociedad, sucursal y artículo;
- un historial que registre cambios de stock, en lugar de copiar filas idénticas en cada ejecución;
- fecha de observación e identificador de ejecución en todos los registros;
- conservación explícita de estados con stock cero para poder identificar quiebres.

Antes de implementarlo se debe revisar el workflow exportado de n8n, las columnas del reporte, la cantidad de filas y la frecuencia de ejecución.

## Stock en tránsito

El stock en tránsito se obtiene cruzando dos reportes CSV diarios de Google Drive: órdenes despachadas y órdenes efectivamente recibidas. Cada ejecución reemplaza el documento completo manteniendo el mismo nombre, por lo que el ID de Drive cambia y no debe persistirse como referencia estable.

La clave de cruce validada sobre muestras reales es:

```text
NumeroDocumento + Clave
```

La cantidad pendiente se calcula por documento y artículo:

```text
max(CantidadValidacionDespacho - CantidadValidacionRecepcion, 0)
```

Debe utilizarse la columna de detalle `CantidadValidacionDespacho`, sin sufijo. `CantidadValidacionDespacho1` representa un total repetido del documento y no debe sumarse por artículo.

La importación deberá conservar:

- identificación del documento o transferencia, si existe;
- artículo o SKU;
- origen y destino;
- cantidad despachada, recibida y pendiente;
- estado y fechas disponibles;
- nombre o huella del archivo;
- fecha e identificador de la importación.

La muestra de despachos contenía seis filas informativas antes del encabezado real; la muestra de recepciones comenzaba directamente con la tabla. El proceso debe localizar los encabezados por nombre y no asumir una fila fija. La búsqueda en Drive debe realizarse diariamente por carpeta y nombre exacto, exigir un único resultado y validar la vigencia del archivo, porque el ID cambia en cada reemplazo.

## Auditoría de ejecuciones

Las cargas de artículos, ventas, existencias y tránsito deberán registrar como mínimo:

- identificador de ejecución;
- fuente;
- fecha de inicio y finalización;
- estado;
- registros leídos, guardados y rechazados;
- período solicitado;
- archivo de origen cuando corresponda;
- mensaje de error.

## Próximos pasos

1. Restaurar y verificar la configuración diaria del workflow v2, manteniéndolo inactivo.
2. Identificar consumidores de `public.ventas_raw` y `public.ventas_items` y adaptar las vistas a la fuente v2.
3. Ejecutar un backfill controlado por ventanas y reconciliar varios días antes del corte.
4. Desactivar el workflow anterior y activar la v2 sin superponer sus horarios.
5. Monitorear las primeras ejecuciones automáticas del workflow independiente de stock y validar sus 12 lotes en Supabase.
6. Diseñar la importación idempotente de los dos CSV de tránsito usando la clave y cantidades ya validadas.
7. Implementar la persistencia de tránsito cuando se apruebe la etapa correspondiente.

La revisión técnica del flujo diario se encuentra en [`REVISION_WORKFLOW_VENTAS.md`](REVISION_WORKFLOW_VENTAS.md).

La versión paralela y sus pasos de instalación están documentados en [`IMPLEMENTACION_V2_VENTAS.md`](IMPLEMENTACION_V2_VENTAS.md). Fue instalada y validada manualmente, pero permanece inactiva. Los resultados se encuentran en [`VALIDACION_INGESTA_V2_2026-07-22.md`](VALIDACION_INGESTA_V2_2026-07-22.md).

Scripts preparados:

- `supabase/audits/001_auditoria_ventas.sql`: controles de cobertura, nulos, duplicados, relación cabecera-detalle, signos y conciliación de importes;
- `supabase/audits/002_validacion_ventas_v2.sql`: comparación de v1/v2, detección de líneas repetidas legítimas y control de ejecuciones incompletas;
- `supabase/views/000_maestro_articulos_normalizado.sql`: normalización no destructiva de color y talle con estado de parseo;
- `supabase/views/001_ventas_diarias.sql`: vistas provisionales de ventas diarias y ventanas móviles de 7, 28 y 56 días.
- `supabase/views/002_calidad_ventas.sql`: resumen separado de ventas históricas sin sucursal recuperable.
- `supabase/migrations/001_ventas_v2_paralela.sql`: tablas paralelas, auditoría por ejecución e ingesta por lote para la versión 2.

