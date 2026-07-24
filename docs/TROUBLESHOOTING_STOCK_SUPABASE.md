# Resolución de problemas — Stock Centum a Supabase

## Principio de diagnóstico

Separar tres estados distintos:

1. estado visual de la ejecución en n8n;
2. ejecución general registrada en `stock_ejecuciones`;
3. lotes confirmados en `stock_lotes`.

Una ejecución puede aparecer cancelada o continuar en `running` en n8n y, aun así, haber confirmado todos los lotes en Supabase. Nunca decidir una recarga basándose únicamente en la interfaz de n8n.

## La ejecución aparece en `running` durante demasiado tiempo

Tiempo de referencia: aproximadamente 12 minutos para 12 sucursales. Investigar si supera claramente ese valor.

1. Consultar `stock_ejecuciones` con el ID de n8n.
2. Consultar cuántos lotes existen.
3. Si hay 12/12 y estado `completada`, los datos ya están guardados.
4. Si faltan lotes, identificar la última sucursal procesada.
5. No cancelar ni reejecutar hasta conocer el estado SQL, salvo riesgo operativo inmediato.

El incidente del workflow integrado no debe confundirse con este flujo separado. Aquel problema se producía por combinar casi un millón de registros con el procesamiento del Excel.

## n8n muestra `canceled`, pero Supabase muestra `completada`

Supabase confirmó la transacción antes de la cancelación. No recargar.

Validar:

- 12 sucursales procesadas;
- 12 lotes;
- cero errores;
- totales de lotes iguales a la cabecera.

La ejecución `1831` es el antecedente validado de este escenario.

## La ejecución queda en `iniciada`

Significa que no alcanzó las 12 sucursales esperadas.

```sql
select *
from centum_sync.stock_lotes
where id_ejecucion = '<ID_EJECUCION>'
order by procesado_en;
```

Si existe una corrida posterior completa, no recuperar la anterior. Puede marcarse administrativamente como fallida, pero no debe borrarse sin una decisión explícita.

## Timeout de n8n

Antecedente: durante el piloto, `Norm Stock` procesaba datos destinados al Excel y la tarea superó 300 segundos.

La solución productiva fue eliminar todos los nodos ajenos a Supabase y usar esta única ruta:

```text
HTTP → Prepara Stock Supabase → Postgres → Loop
```

Si reaparece un timeout:

- comprobar que no se hayan agregado ramas de Excel o maestro;
- revisar latencia de Centum por sucursal;
- revisar duración de la función SQL;
- comprobar bloqueos o saturación de Postgres;
- no aumentar el timeout como primera respuesta.

## Error al obtener la sucursal desde el loop

Síntoma histórico: `Unknown error` en `Prepara Stock Supabase` después de la primera vuelta.

Causa: uso de una referencia `.item` cuya asociación se pierde al regresar al loop.

Solución vigente: obtener `idSucursal` desde `IdSucursalFisica` de la respuesta de Centum. No revertir esta decisión.

## Respuesta vacía o sin `IdSucursalFisica`

`Prepara Stock Supabase` detiene la ejecución con:

```text
Centum devolvio stock vacio o sin IdSucursalFisica
```

Revisar:

- ID enviado en `idsSucursalesFisicas`;
- validez del token;
- estructura real de la respuesta;
- disponibilidad del endpoint;
- cambios en los nombres `Items`, `ArticulosSucursalesFisicas` o `ArticulosSucursales`.

No interpretar una respuesta vacía como stock cero.

## Error HTTP o de autenticación Centum

Los nodos de token y HTTP tienen reintentos habilitados. Si fallan definitivamente:

- revisar la credencial Centum en n8n;
- verificar el identificador del consumidor;
- confirmar conectividad con el endpoint;
- evitar copiar tokens o secretos a logs, documentación o Git.

## Error de Postgres

Revisar el mensaje guardado por n8n y, si existe, `mensaje_error` en las tablas de auditoría.

Antecedente corregido:

```text
column reference "registros_recibidos" is ambiguous
```

La migración actual califica las columnas de `stock_lotes` mediante alias. Si reaparece, comprobar que Supabase tenga aplicada la versión vigente de [`003_stock_snapshot.sql`](../supabase/migrations/003_stock_snapshot.sql).

## Diferencia entre registros recibidos y normalizados

En las ejecuciones validadas ambos valores coinciden. Una diferencia nueva requiere revisar:

- filas sin `IdArticulo`;
- registros pertenecientes a otra sucursal;
- duplicados por sucursal, sección y artículo;
- cambios en el contrato de Centum.

No corregir datos directamente en `stock_actual` antes de entender la respuesta cruda.

## Cambios registrados demasiado altos

Un número alto puede ser válido:

- primera aparición de una sucursal;
- incorporación de artículos nuevos;
- cambio real masivo en Centum.

En `1831`, las sucursales `9302` y `9308` registraron 76.991 cambios cada una porque fue su carga inicial. La corrida siguiente, `1836`, registró solo 586 cambios totales.

## Existencias negativas

No son un error de importación por sí mismas. Se validaron 33 filas negativas provenientes de Centum. Deben conservarse para mantener fidelidad con el origen.

## Una sucursal falta en la última ejecución

1. Confirmar el ID en `Code - Lista sucursales`.
2. Revisar si el loop alcanzó esa posición.
3. Consultar `stock_lotes`.
4. Revisar token y HTTP para esa sucursal.
5. No recargar las 12 sucursales automáticamente.
6. Definir una recuperación controlada y aprobarla antes de ejecutar cambios.

## Escalamiento

Conservar siempre:

- ID de ejecución n8n;
- hora de inicio y detención en ART;
- estado de `stock_ejecuciones`;
- detalle de `stock_lotes`;
- última sucursal procesada;
- mensaje exacto del nodo fallido;
- cualquier cambio realizado inmediatamente antes del incidente.

No incluir credenciales, tokens ni respuestas completas de producción en issues o documentación.
