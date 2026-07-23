# Backfill controlado de ventas v2

## Estado previo obligatorio

- El workflow diario anterior permanece activo.
- El workflow v2 permanece inactivo.
- La fuente canónica transitoria está instalada y validada.
- No se superponen ejecuciones manuales con el cron diario de las 02:00 ART.

## Primera ventana piloto

La primera ventana propuesta es del 14 al 20 de julio de 2026, inclusive. Son siete días recientes, incluyen el 17 de julio ya conciliado y permiten medir volumen, duración e idempotencia antes de retroceder en el histórico.

La ejecución debe usar las 13 sucursales y sus dos divisiones, por lo que mantiene `lotesEsperados: 26`. Cada una de las 26 consultas utiliza el mismo rango completo de siete días.

## Secuencia

1. Duplicar el workflow v2 dentro del proyecto Personal.
2. Nombrar la copia `Centum → Supabase: Backfill Ventas v2 (MANUAL)`.
3. Reemplazar el disparador programado por uno manual.
4. Configurar `fechaDesde: '2026-07-14'` y `fechaHasta: '2026-07-20'` únicamente en la copia.
5. Mantener `lotesEsperados: 26` y `return consultas;`.
6. Verificar que la copia permanezca inactiva.
7. Ejecutarla manualmente una sola vez fuera del horario del cron diario.
8. Confirmar que la ejecución registre 26 lotes procesados y ningún error.
9. Ejecutar `supabase/audits/004_validacion_ventana_backfill.sql`.
10. Explicar cada diferencia V2 − V1 antes de ampliar la ventana.
11. Repetir la misma ventana para confirmar idempotencia.

## Criterios para avanzar

- ejecución en estado `completada`;
- 26 lotes esperados y 26 procesados;
- ninguna línea V1 solapada en la fuente canónica;
- diferencias explicadas por líneas legítimas que V1 sobrescribía;
- totales canónicos estables después de repetir la ventana;
- duración y volumen registrados.

No se activa el workflow v2 diario ni se desactiva el anterior durante este piloto.

## Resultado del piloto del 14 al 20 de julio

Validado el 23 de julio de 2026 con datos reales de Centum.

- primera ejecución manual: `1813`, completada en aproximadamente 3 minutos y 9 segundos;
- segunda ejecución manual: `1814`, completada en aproximadamente 4 minutos;
- 26 lotes esperados y 26 procesados en ambas ejecuciones;
- 2.159 comprobantes y 4.610 líneas procesadas;
- cero lotes con error y cero líneas v1 solapadas en la fuente canónica;
- 4.610 líneas almacenadas y canónicas después de repetir la ventana;
- idempotencia confirmada: la segunda ejecución no agregó duplicados.

La comparación contra v1 encontró 124 líneas adicionales en v2, distribuidas en 94 combinaciones de venta y artículo. Todas correspondieron a artículos repetidos legítimamente dentro del mismo comprobante:

- 123 unidades vendidas recuperadas;
- 3 unidades devueltas recuperadas;
- 120 unidades netas recuperadas.

## Segunda ventana

La siguiente ventana aprobada es del 7 al 13 de julio de 2026, inclusive. Se mantiene el mismo workflow manual, con 26 lotes y sin activación automática.

### Resultado

La ejecución manual `1816` fue validada el 23 de julio de 2026:

- estado `completada`;
- 26 lotes esperados y 26 procesados;
- cero lotes con error;
- 2.211 comprobantes y 4.612 líneas procesadas;
- 4.612 líneas v2 visibles en la fuente canónica;
- cero líneas v1 restantes dentro de la ventana.

V2 recuperó 159 líneas distribuidas en 122 combinaciones de venta y artículo. Todas correspondieron a artículos repetidos legítimamente dentro del mismo comprobante:

- 154 unidades vendidas recuperadas;
- 5 unidades devueltas recuperadas;
- 149 unidades netas recuperadas.

## Tercera ventana

La siguiente ventana aprobada es del 30 de junio al 6 de julio de 2026, inclusive. Se mantienen 26 lotes, disparador manual y workflow inactivo.

### Resultado

La ejecución manual `1817` fue validada el 23 de julio de 2026:

- estado `completada`;
- 26 lotes esperados y 26 procesados;
- cero lotes con error;
- 2.652 comprobantes y 5.588 líneas procesadas;
- 5.588 líneas v2 visibles en la fuente canónica;
- cero líneas v1 restantes dentro de la ventana.

V2 recuperó 194 líneas legítimas por artículos repetidos dentro del mismo comprobante. También detectó una corrección histórica de Centum: el comprobante `1275433` tenía cuatro líneas en la respuesta original guardada por v1 y tres líneas en la respuesta actual. El artículo `61625` fue retirado del mismo documento y no existe una nota de crédito posterior para ese artículo.

El balance de la ventana fue:

- 193 líneas netas adicionales;
- 191 unidades vendidas adicionales;
- 3 unidades devueltas adicionales;
- 188 unidades netas adicionales.

## Regla para documentos corregidos

La respuesta más reciente de Centum se considera la versión autoritativa para forecasting y reposición. Las respuestas anteriores se conservan para auditoría, pero no permanecen en la fuente canónica cuando un lote v2 procesado cubre la misma división, sucursal y fecha.

## Cuarta ventana

La siguiente ventana aprobada es del 23 al 29 de junio de 2026, inclusive. Se mantienen 26 lotes, disparador manual y workflow inactivo.

### Resultado

La ejecución manual `1818` fue validada el 23 de julio de 2026:

- estado `completada`;
- 26 lotes esperados y 26 procesados;
- cero lotes con error;
- 2.681 comprobantes y 5.612 líneas procesadas;
- 5.612 líneas v2 visibles en la fuente canónica;
- cero líneas v1 restantes dentro de la ventana.

V2 recuperó 183 líneas por artículos repetidos legítimamente dentro del mismo comprobante. También detectó una línea agregada posteriormente al comprobante `1274758`: la respuesta histórica contenía una línea y la respuesta actual contiene dos; el artículo `66857`, cantidad 2, sólo aparece en la versión actual.

El balance de la ventana fue:

- 184 líneas adicionales;
- 187 unidades vendidas adicionales;
- 4 unidades devueltas adicionales;
- 183 unidades netas adicionales.

## Primera ventana ampliada

Después de validar cuatro semanas consecutivas, la siguiente ejecución cubre del 25 de mayo al 22 de junio de 2026, inclusive. El objetivo es completar en una sola ventana el histórico anterior actualmente almacenado en v1. Se mantienen 26 lotes, disparador manual y workflow inactivo.

### Resultado

La ejecución manual `1820` fue validada el 23 de julio de 2026:

- estado `completada`;
- 26 lotes esperados y 26 procesados;
- cero lotes con error;
- 10.518 comprobantes y 23.678 líneas procesadas;
- 23.678 líneas v2 visibles en la fuente canónica;
- cero líneas v1 con sucursal restantes dentro de la ventana;
- duración aproximada de 12 minutos y 10 segundos.

Para el período comparable del 27 de mayo al 22 de junio, V2 recuperó 690 líneas por artículos repetidos legítimamente. También reflejó cambios posteriores realizados en Centum:

- 19 líneas agregadas a documentos existentes;
- 1 línea retirada de un documento;
- 1 cantidad modificada;
- ninguna diferencia inexplicada.

Para el 25 y 26 de mayo, V1 contenía 1.199 líneas sin sucursal. V2 reconstruyó 1.244 líneas con ubicación:

- 1.168 combinaciones coincidieron exactamente;
- 31 combinaciones contenían artículos repetidos;
- 45 líneas y 45 unidades legítimas recuperadas;
- las sucursales quedaron disponibles para el análisis por local.

## Ventana de alineación final

La siguiente ejecución cubre del 21 al 22 de julio de 2026, inclusive. Su objetivo es alinear V2 hasta el último día procesado por el workflow diario anterior antes de preparar el corte productivo.

### Resultado

La ejecución manual `1823` fue validada el 23 de julio de 2026:

- estado `completada`;
- 26 lotes esperados y 26 procesados;
- cero lotes con error;
- 717 comprobantes y 1.642 líneas procesadas;
- 1.642 líneas v2 visibles en la fuente canónica;
- cero líneas v1 restantes dentro de la ventana;
- 52 líneas y 54 unidades netas adicionales, todas explicadas por artículos repetidos legítimamente.

## Corte productivo

El corte se realizó el 23 de julio de 2026 dentro del proyecto Personal de n8n:

- workflow anterior `XUZSnbXK6ReCOwYh`: inactivo;
- workflow diario v2 `5IR7J2uxBeoW4YMK`: activo;
- workflow manual de backfill `hbcKc5ElvaAxpwYJ`: inactivo;
- horario de V2: 02:00 ART;
- fecha consultada: día anterior;
- 26 lotes esperados por ejecución.

El workflow anterior se conserva inactivo como mecanismo de reversión. El siguiente control obligatorio es validar la primera ejecución automática de V2 y confirmar sus 26 lotes antes de considerar estabilizado el corte.
