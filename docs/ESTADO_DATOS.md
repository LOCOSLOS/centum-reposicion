# Estado de datos

Última actualización: 22 de julio de 2026.

Este documento registra únicamente hechos confirmados, decisiones de trabajo y validaciones pendientes. No debe contener credenciales, respuestas completas de producción ni información comercial sensible.

## Fuentes y flujos existentes

- Centum es el sistema de gestión de origen.
- n8n ejecuta flujos que extraen información de Centum.
- Los flujos actuales de artículos y ventas guardan sus resultados en Supabase.
- Existe un flujo de existencias que actualmente genera un reporte, pero todavía no persiste el resultado en una tabla.
- El stock en tránsito no está disponible mediante la API de Centum. Se obtiene desde un archivo CSV que ya consume la herramienta operativa existente.
- La arquitectura original contemplaba Neon Postgres. Queda pendiente decidir si el MVP se consolida en Supabase o si se mantiene Neon como destino final, evitando duplicar información entre ambas plataformas.

## Maestro de artículos

Información disponible:

- `idarticulo`;
- rubro;
- subrubro;
- `sku`;
- descripción del artículo;
- grupo de artículo.

Validaciones confirmadas:

- `idarticulo` es estable y único;
- `sku` es único;
- todas las ventas encuentran su artículo correspondiente en el maestro.

La descripción permite obtener talle y color. Para evitar interpretar el texto en cada consulta, se prevé normalizar ambos atributos y conservar la descripción original. El método de extracción y sus excepciones todavía deben validarse con datos reales.

## Ventas

Información disponible:

- identificador interno de Supabase;
- `idventa`;
- `idarticulo`;
- período;
- sociedad;
- fecha del comprobante;
- `sku`;
- descripción;
- cantidad vendida;
- precio final;
- precio neto;
- costo de reposición;
- `idsucursal`;
- nombre de la sucursal.

Validaciones confirmadas:

- `idventa` identifica el comprobante completo;
- un comprobante contiene varias líneas y, por lo tanto, varias filas pueden compartir el mismo `idventa`;
- el histórico actualmente almacenado comienza el 26 de mayo de 2026;
- Centum permite cargar períodos anteriores mediante ejecuciones adicionales.

Validaciones pendientes:

- determinar si puede repetirse `idventa + idarticulo` legítimamente;
- localizar un identificador estable de línea o definir una clave reproducible;
- comprobar cómo se representan devoluciones y anulaciones;
- detectar duplicados generados por reejecuciones;
- verificar períodos incompletos por sociedad y sucursal;
- definir el alcance del backfill histórico. Como referencia inicial se consideran 12 meses como mínimo y 24 meses como período preferible para indumentaria.

No se debe ejecutar el backfill completo hasta definir una clave idempotente para cada línea de venta.

## Existencias

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

El CSV existente será la fuente del stock en tránsito. Su importación deberá conservar:

- identificación del documento o transferencia, si existe;
- artículo o SKU;
- origen y destino;
- cantidad enviada y cantidad pendiente;
- estado y fechas disponibles;
- nombre o huella del archivo;
- fecha e identificador de la importación.

Queda pendiente revisar las columnas del archivo y definir una clave estable. También se debe establecer qué significa que una transferencia deje de aparecer en una nueva versión del CSV antes de marcarla como recibida o cancelada.

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

1. Revisar nombres, columnas, tipos y muestras anonimizadas de las tablas actuales de artículos y ventas.
2. Auditar unicidad de las líneas, duplicados, devoluciones, anulaciones y cobertura temporal de ventas.
3. Revisar el workflow de existencias y definir su persistencia en Supabase.
4. Revisar el CSV de tránsito y definir su clave e importación idempotente.
5. Decidir si Supabase será la base central del MVP o si existirá una sincronización justificada con Neon.
6. Ejecutar una carga histórica controlada después de resolver la idempotencia.
7. Construir una vista consolidada por fecha, sociedad, sucursal y artículo.
