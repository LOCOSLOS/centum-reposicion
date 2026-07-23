# Integración de inventario Centum con Supabase

## Objetivo

Extender el workflow existente de inventario para que una única consulta de stock a Centum tenga dos destinos:

1. conservar la generación y el envío obligatorio del Excel de inventario;
2. persistir el stock por sucursal en Supabase para el futuro motor de reposición.

La arquitectura final evita consultar dos veces a Centum. Cada respuesta por sucursal se reutiliza para el Excel y para Supabase.

## Decisiones funcionales

- `6455 - 01 Casa Central` es el depósito central desde el que se repone.
- Se procesan 12 sucursales físicas: `6455`, `6457`, `6084`, `6761`, `6458`, `8774`, `9254`, `9258`, `9281`, `9292`, `9302` y `9308`.
- `21 - Mayorista` queda excluida por el momento.
- El stock físico es compartido y no distingue sociedad ni división.
- La clave de stock es sucursal, sección de sucursal y artículo.
- Los estados con cantidades en cero o negativas se conservan tal como los informa Centum.

## Workflows de n8n

### Versión 9 integrada

- ID: `35lPkl3rmDXcG0iD`
- Nombre: `Centum → Excel + Supabase: Inventario Diario v9`
- Proyecto: Personal
- Horario: 04:00 ART
- Estado al 23 de julio de 2026: activo en período de validación

Se creó como copia completa de la versión 8. Conserva el procesamiento, la generación del Excel y el envío por correo, y agrega la persistencia en Supabase.

### Versión 8 original

- ID: `p5IRTMnkXfXe75TQ`
- Nombre: `Reporte Inventario Centum - v8 con datatable`
- Horario: 05:00 ART
- Estado al 23 de julio de 2026: activo temporalmente como respaldo

El original no fue modificado. Permanece activo hasta confirmar que la versión 9 genera y entrega correctamente el Excel.

### Piloto separado de Supabase

- ID: `QKKdZL5xHFVNkiFh`
- Nombre: `Centum → Supabase: Sync Stock Diario`
- Estado: inactivo

Se utilizó para validar la persistencia sin poner en riesgo el Excel. Quedó desactivado para evitar consultas duplicadas a Centum.

## Arquitectura de la versión 9

La respuesta cruda del HTTP se bifurca dentro del loop:

```text
Loop de sucursales
  → Token Centum
  → HTTP pag1 por sucursal
      ├─→ Norm Stock
      │    → procesamiento existente
      │    → consolidación
      │    → generación del Excel
      │    → envío por correo
      │
      └─→ Prepara Stock Supabase
           → Postgres - Persiste Stock Supabase
```

Los nodos de Supabase se ejecutan una vez por vuelta porque nacen desde el HTTP que está dentro del loop. La rama Postgres no regresa al loop: `Norm Stock` ya controla ese retorno y una segunda conexión podría provocar señales o iteraciones duplicadas.

## Nodo `Prepara Stock Supabase`

- Tipo: Code v2
- Modo: `Run Once for All Items`

```javascript
const data = $input.first().json;

if (
  data.error ||
  data.code ||
  (data.statusCode && data.statusCode >= 400)
) {
  throw new Error(
    'Centum devolvio un error al consultar stock'
  );
}

const registros =
  data.Items ||
  data.ArticulosSucursalesFisicas?.Items ||
  data.ArticulosSucursales?.Items ||
  [];

const filaConSucursal = registros.find(
  row => Number(row.IdSucursalFisica ?? 0) > 0
);

if (!filaConSucursal) {
  throw new Error(
    'Centum devolvio stock vacio o sin IdSucursalFisica'
  );
}

const idSucursal = Number(
  filaConSucursal.IdSucursalFisica
);

const mejores = new Map();

for (const row of registros) {
  const idArticulo = Number(
    row.IdArticulo ?? 0
  );

  if (!idArticulo) {
    continue;
  }

  const idSeccion = Number(
    row.IdSeccionSucursal ?? 0
  );

  const idSucursalFila = Number(
    row.IdSucursalFisica ?? idSucursal
  );

  if (idSucursalFila !== idSucursal) {
    continue;
  }

  const key =
    idSucursalFila +
    '_' +
    idSeccion +
    '_' +
    idArticulo;

  const normalizada = {
    IdArticulo: idArticulo,
    IdSucursalFisica: idSucursalFila,
    IdSeccionSucursal: idSeccion,
    Existencias: Number(
      row.Existencias ?? 0
    ),
    CantidadOrdenesCompra: Number(
      row.CantidadOrdenesCompra ?? 0
    ),
    CantidadPedidosVenta: Number(
      row.CantidadPedidosVenta ?? 0
    ),
    StockComprometido: Number(
      row.StockComprometido ?? 0
    ),
    StockIdeal: Number(
      row.StockIdeal ?? 0
    ),
    StockMinimo: Number(
      row.StockMinimo ?? 0
    ),
    StockCritico: Number(
      row.StockCritico ?? 0
    ),
    StockExcesivo: Number(
      row.StockExcesivo ?? 0
    ),
    CodigoArticuloPropioSucursal:
      row.CodigoArticuloPropioSucursal ?? ''
  };

  const anterior = mejores.get(key);

  if (
    !anterior ||
    normalizada.Existencias > anterior.Existencias
  ) {
    mejores.set(key, normalizada);
  }
}

const payload = Array.from(
  mejores.values()
);

function sqlTexto(valor) {
  return (
    "'" +
    String(valor).replace(/'/g, "''") +
    "'"
  );
}

function sqlJson(valor) {
  return (
    "'" +
    JSON.stringify(valor).replace(/'/g, "''") +
    "'::jsonb"
  );
}

const observadoEn = new Date().toISOString();

const query =
  'select * from centum_sync.ingestar_stock_snapshot('
  + sqlTexto(String($execution.id)) + ', '
  + idSucursal + ', '
  + sqlTexto(observadoEn) + '::timestamptz, '
  + '12, '
  + sqlJson(registros)
  + ');';

return [
  {
    json: {
      query,
      idEjecucion: String($execution.id),
      idSucursal,
      registrosRecibidos: registros.length,
      registrosNormalizados: payload.length,
      observadoEn
    }
  }
];
```

El código obtiene la sucursal desde `IdSucursalFisica` de la respuesta real. La referencia inicial `$('Loop Over Sucursales').item.json.sucursalId` se descartó porque n8n perdía la asociación del ítem después de regresar al loop.

## Nodo `Postgres - Persiste Stock Supabase`

- Tipo: Postgres 2.6
- Operación: Execute Query
- Consulta:

```javascript
{{ $json.query }}
```

Ejecuta `centum_sync.ingestar_stock_snapshot` con el ID de ejecución de n8n, la sucursal, la fecha de observación, las 12 sucursales esperadas y el JSON completo de Centum.

## Diseño en Supabase

La migración `supabase/migrations/003_stock_snapshot.sql` crea:

- `centum_sync.stock_ejecuciones`: auditoría general de ejecuciones;
- `centum_sync.stock_lotes`: control individual por sucursal;
- `centum_sync.stock_actual`: último estado conocido;
- `centum_sync.stock_historial`: estado inicial y cambios reales;
- `centum_sync.ingestar_stock_snapshot`: normalización, historial y upsert transaccional.

La clave de `stock_actual` es:

```text
id_sucursal + id_seccion_sucursal + id_articulo
```

El historial registra `inicial` cuando aparece una combinación nueva y `cambio` cuando cambia alguno de los valores. No copia diariamente todas las filas sin cambios.

## Incidentes corregidos

### Ambigüedad PL/pgSQL

La función falló inicialmente con:

```text
column reference "registros_recibidos" is ambiguous
```

Se corrigió calificando las columnas de `stock_lotes` con un alias explícito.

### Asociación incorrecta del loop

`Prepara Stock Supabase` devolvió `Unknown error` al usar `.item` para recuperar la sucursal. Se reemplazó esa dependencia por `IdSucursalFisica` de la respuesta.

### Timeout del piloto

El piloto superó los 300 segundos cuando `Norm Stock` continuó procesando la rama del Excel. Durante la prueba se hizo que Postgres controlara el retorno al loop. Esa conexión fue sólo de validación y no se trasladó a la versión integrada.

### Ejecución visual sin cerrar

La ejecución completa quedó en `running` después de terminar los 12 lotes porque n8n intentaba cerrar una ejecución manual con casi un millón de registros. Supabase confirmó la finalización y la ejecución visual se canceló sin afectar los datos.

## Validaciones con datos reales

### Casa Central

Primera carga:

- 76.980 registros recibidos y almacenados;
- 76.980 entradas de historial inicial.

Segunda carga:

- 76.982 registros recibidos;
- 2 artículos nuevos;
- 0 modificaciones existentes;
- 0 duplicados.

### Doce sucursales

Ejecución `1831`:

- estado `completada`;
- 12 sucursales esperadas y procesadas;
- 12 lotes procesados;
- 0 lotes con error;
- 923.892 registros recibidos y normalizados;
- 76.991 artículos por sucursal.

Casa Central fue la única sucursal marcada como depósito. Se conservaron 33 filas con existencias negativas porque son valores reales informados por Centum.

## Estado temporal y corte pendiente

Durante la primera validación automática se mantienen activos:

- 04:00 ART: versión 9 integrada, Excel y Supabase;
- 05:00 ART: versión 8 original, Excel de respaldo.

Los destinatarios pueden recibir dos correos durante esta prueba. El piloto separado de Supabase permanece inactivo.

Después de la primera ejecución automática de la versión 9 se debe confirmar:

1. ejecución finalizada;
2. 12 sucursales y 12 lotes sin error en Supabase;
3. Excel generado;
4. correo recibido por los destinatarios;
5. ausencia de duplicados;
6. historial limitado a cambios reales.

Cuando estas condiciones se cumplan, se desactivará la versión 8 y quedará activa únicamente la versión 9 integrada.
