# Auditoría acumulada del histórico de ventas

Fecha de cierre: 5 de agosto de 2026.

## Conclusión

La etapa de backfill de ventas queda formalmente cerrada. La cobertura útil es
continua desde el 1 de julio de 2024 hasta el 4 de agosto de 2026 y no quedan
días sin una ejecución completa de 26 combinaciones sucursal-división.

La auditoría confirmó:

- 765 días cubiertos de 765 esperados;
- 75 ejecuciones completas, reconciliadas y válidas para cobertura;
- cero ejecuciones completadas con diferencias entre cabecera y lotes;
- cero campos críticos nulos o inválidos;
- cero líneas fuera de la ventana de su ejecución autoritativa;
- una clave primaria que impide duplicados canónicos;
- una clave foránea que impide ítems sin cabecera.

## Incidencia corregida durante la auditoría

La primera ejecución acumulada detectó un único hueco, el 1 de agosto de 2026.
La ejecución `1967` había quedado abierta después de procesar 13 de 26 lotes.
Se repitió solamente ese día mediante el workflow manual y el control posterior
quedó en cero días faltantes.

Las ejecuciones `1804`, `1805` y `1806` no eran fallas: fueron pruebas
controladas de un lote y cerraron correctamente 1/1. Por eso se separó la
conciliación genérica de una ejecución de la exigencia 26/26 que corresponde a
las ventanas productivas de backfill.

Permanecen cinco ejecuciones históricas con estado `iniciada` y una con estado
`con_error`. No afectan la fuente actual: sus fechas están cubiertas por
ejecuciones posteriores completas y el criterio autoritativo usa lotes
procesados.

## Resultado sobre la fuente canónica v2

La consulta final revisó 744.651 líneas canónicas vigentes:

| Control | Resultado |
|---|---:|
| Líneas con venta | 697.240 |
| Líneas con devolución | 47.411 |
| Líneas con cantidad cero | 0 |
| Unidades vendidas | 737.365 |
| Unidades devueltas | 61.872 |
| Unidades netas | 675.493 |
| Líneas de servicio `ENVIO` identificadas | 7.351 |

El servicio `ENVIO` se conserva en la historia comercial, pero continúa
excluido del cálculo de reposición.

Los 350.365 comprobantes y 789.229 líneas informados por la auditoría de
ejecuciones son totales procesados por las 75 ejecuciones válidas. No deben
interpretarse como claves canónicas únicas porque pueden incluir ventanas
reprocesadas. El total vigente y deduplicado es el de 744.651 líneas indicado
por la consulta de cierre.

## Validación profunda de respuestas JSON

Además de los controles 26/26 realizados durante cada ventana original, se
comparó nuevamente la respuesta cruda contra las tablas canónicas sobre doce
meses continuos, desde julio de 2024 hasta junio de 2025.

Se revisaron 910 lotes procesados y se obtuvo cero diferencias en los tres
controles:

- cantidad registrada frente a `Ventas.Items` y `VentaArticulos`;
- última cabecera canónica frente a la última respuesta procesada;
- últimas líneas canónicas frente al último `VentaArticulos` recibido.

La comprobación mensual se detuvo después de cubrir doce meses consecutivos
porque repetía la validación ya realizada durante el backfill y no detectó
ninguna diferencia.

## Consultas reproducibles

- `supabase/audits/006_auditoria_acumulada_ventas_v2.sql`: cobertura diaria,
  26 combinaciones y conciliación de ejecuciones/lotes.
- `supabase/audits/007_auditoria_json_ventas_v2_mensual.sql`: comparación
  profunda de JSON, cabeceras y líneas por bloques configurables.
- `supabase/audits/008_cierre_calidad_ventas_v2.sql`: restricciones, campos
  críticos, rangos, ventas, devoluciones y servicio `ENVIO`.

## Decisión

No se cargarán períodos anteriores al 1 de julio de 2024 en esta etapa. La
auditoría acumulada queda aprobada y el siguiente trabajo de datos es persistir
snapshots diarios de órdenes de traspaso.
