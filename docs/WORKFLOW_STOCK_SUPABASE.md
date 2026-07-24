# Referencia técnica — Workflow de stock Centum a Supabase

## Identificación

- ID n8n: `QKKdZL5xHFVNkiFh`
- Nombre: `Centum → Supabase: Sync Stock Diario`
- Estado documentado: activo
- Horario: todos los días a las 03:00 ART
- Zona horaria: `America/Argentina/Buenos_Aires`
- Cantidad de nodos: 9

Este workflow persiste stock. No genera Excel, no envía correo, no consulta listas de precios y no cruza el maestro de artículos.

## Configuración de ejecución

La instancia activa utiliza:

- `executionOrder: v1`;
- `saveDataErrorExecution: all`;
- `saveDataSuccessExecution: none`;
- `saveManualExecutions: false`;
- `saveExecutionProgress: false`;
- almacenamiento binario separado.

No guardar datos de ejecuciones exitosas es intencional. Cada corrida procesa aproximadamente 923.892 registros y conservarlos en n8n produciría un consumo innecesario de memoria y almacenamiento. La auditoría funcional reside en Supabase.

## Recorrido nodo por nodo

### 1. Triggers

`Diario 03:00 ART` inicia la ejecución automática. `When clicking 'Execute workflow'` permite pruebas manuales controladas.

Ambos conectan exclusivamente con `Code - Lista sucursales`.

### 2. `Code - Lista sucursales`

Tipo: Code v2.

Genera un item por sucursal, en este orden:

```javascript
const ids = [
  "6455", "6457", "6084", "6761",
  "6458", "8774", "9254", "9258",
  "9281", "9292", "9302", "9308"
];

return ids.map(id => ({
  json: { sucursalId: id }
}));
```

Cambiar esta lista modifica el alcance funcional y también exige revisar el valor de sucursales esperadas enviado a SQL.

### 3. `Loop Over Sucursales`

Tipo: Loop Over Items v3.

Procesa una sucursal por vuelta. Su salida de iteración conecta con `Token pag1 sucursal`. El retorno proviene únicamente de `Postgres - Persiste Stock Piloto`.

La salida de finalización no tiene nodos posteriores. Cuando terminan las 12 vueltas, la ejecución concluye.

### 4. `Token pag1 sucursal`

Tipo: nodo Centum, recurso `generarTokenSeguridad`.

Genera el token requerido por la API pública. Tiene reintentos habilitados y usa la credencial Centum almacenada en n8n. Las credenciales no se exportan ni se documentan en el repositorio.

### 5. `Normaliza Token pag1 sucursal`

Tipo: Set v3.4.

Asigna el resultado del nodo Centum a `CentumSuiteAccessToken`, que luego se envía como encabezado HTTP.

### 6. `HTTP pag1 por sucursal`

Tipo: HTTP Request v4.4, con reintentos habilitados.

Endpoint:

```text
GET https://plataforma5.centum.com.ar:23990/BL6/ArticulosSucursalesFisicas
```

Parámetro:

```text
idsSucursalesFisicas = sucursalId de la vuelta actual
```

Encabezados funcionales:

- `Accept: application/json`;
- identificador del consumidor de la API pública;
- token de acceso generado en la vuelta actual.

La respuesta contiene aproximadamente 76.991 registros por sucursal.

### 7. `Prepara Stock Supabase`

Tipo: Code v2, Run Once for All Items.

Responsabilidades:

1. Detectar respuestas de error de Centum.
2. Admitir las formas `Items`, `ArticulosSucursalesFisicas.Items` y `ArticulosSucursales.Items`.
3. Obtener la sucursal desde `IdSucursalFisica` de la respuesta real.
4. Validar que exista al menos una fila con sucursal.
5. Normalizar los valores numéricos.
6. Identificar filas por sucursal, sección y artículo.
7. Conservar stock cero y negativo.
8. Construir la llamada a `centum_sync.ingestar_stock_snapshot(...)`.
9. Adjuntar el ID de ejecución de n8n y la fecha de observación.

La sucursal no debe obtenerse con `.item` desde el loop. Esa asociación falló en iteraciones posteriores durante las primeras pruebas. `IdSucursalFisica` es la fuente validada.

La función recibe:

```text
id_ejecucion
id_sucursal
observado_en
sucursales_esperadas = 12
respuesta JSON completa de Centum
```

### 8. `Postgres - Persiste Stock Piloto`

Tipo: Postgres v2.6, operación Execute Query.

Ejecuta la consulta construida por el nodo anterior mediante la credencial Supabase/Postgres almacenada en n8n.

La función SQL realiza en una transacción:

- normalización del JSON;
- detección de estados iniciales y cambios;
- inserción del historial necesario;
- upsert de `stock_actual`;
- upsert del lote por sucursal;
- actualización de los totales de la ejecución;
- marcado como `completada` al alcanzar las 12 sucursales.

Después de confirmar la transacción, el nodo regresa al loop.

## Modelo de datos

### `stock_ejecuciones`

Una fila por ejecución de n8n. Permite distinguir una ejecución completa de una corrida parcial aunque la interfaz de n8n haya sido cancelada o no conserve su progreso.

### `stock_lotes`

Una fila por ejecución y sucursal. Su clave primaria es:

```text
id_ejecucion + id_sucursal
```

### `stock_actual`

Contiene el último valor conocido por sucursal, sección y artículo. `6455` queda marcado como depósito central.

### `stock_historial`

No almacena una copia diaria completa. Registra únicamente apariciones iniciales y cambios efectivos.

## Invariantes

Una ejecución saludable debe cumplir:

- 12 sucursales esperadas y procesadas;
- 12 lotes en estado `procesado`;
- cero lotes con error;
- mismo número de registros recibidos y normalizados;
- presencia de los 12 IDs configurados;
- `estado = completada` en `stock_ejecuciones`;
- una única sucursal marcada como depósito: `6455`.

No se considera error que existan filas con stock cero o negativo.
