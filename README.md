# Centum Reposición

Sistema propio de análisis y asistencia para la reposición de inventario de una operación de indumentaria. El objetivo es convertir datos de Centum y fuentes complementarias en recomendaciones de reposición claras, auditables y accionables.

## Contexto operativo

- Aproximadamente 75.000 SKU.
- Rubro: indumentaria.
- Variantes por producto, incluyendo color y talle.
- 10 locales físicos.
- 1 canal de ecommerce.
- 1 depósito central.
- Sistema de gestión actual: Centum.
- Fuentes de datos disponibles: API REST de Centum y archivos Excel/CSV.
- Frecuencia actual estimada de reposición: dos veces por semana, pendiente de validación.

## Objetivo inicial

Construir un MVP que ayude a decidir qué mercadería enviar desde el depósito central a cada local. El sistema debe reducir quiebres de stock y sobrestock sin ocultar la lógica utilizada para generar cada recomendación.

Los traslados entre locales forman parte de la operación, pero no son el foco de la primera etapa.

## Alcance del MVP

1. Importar y normalizar productos, variantes, locales, ventas, stock y mercadería en tránsito.
2. Consolidar información por SKU y ubicación.
3. Calcular demanda histórica, tendencia, cobertura y stock de seguridad.
4. Detectar riesgo de quiebre, sobrestock y productos sin movimiento.
5. Generar propuestas de reposición desde el depósito hacia los locales.
6. Explicar cada sugerencia mediante sus datos de entrada, reglas y nivel de confianza.
7. Permitir revisión humana antes de aprobar o exportar una propuesta.
8. Exportar resultados a Excel o CSV.
9. Presentar indicadores operativos en un tablero.

## Cálculo conceptual inicial

La primera versión partirá de una regla simple, configurable y auditable:

```text
necesidad =
  demanda prevista durante el período de cobertura
  + stock de seguridad
  - stock disponible en el local
  - mercadería en tránsito
```

La cantidad final también deberá respetar:

- stock disponible en el depósito;
- curvas de talle y color;
- mínimos de exhibición;
- múltiplos o unidades de despacho;
- prioridades comerciales;
- restricciones logísticas;
- distribución justa cuando el stock sea escaso.

Los modelos estadísticos o de aprendizaje automático se incorporarán después de disponer de una línea base medible.

## Evolución futura del forecasting

Una vez validada la calidad de los datos y medida la línea base, se evaluarán modelos de aprendizaje automático para mejorar la proyección de demanda. La incorporación será gradual y cada alternativa deberá compararse contra la regla inicial con datos históricos reales.

### Modelos candidatos

1. **XGBoost — candidato principal**
   - Suele ofrecer alta precisión con datos tabulares de ventas e inventario.
   - Permite incorporar estacionalidad, promociones, precios, disponibilidad y atributos de producto como variables.
   - Es una alternativa ampliamente utilizada en forecasting de retail y competencias de ciencia de datos.

2. **LightGBM — candidato para mayor volumen**
   - Tiene un enfoque similar a XGBoost y está optimizado para entrenamiento rápido y uso eficiente de memoria.
   - Resulta especialmente relevante para el volumen esperado de combinaciones SKU-ubicación.
   - Deberá compararse con XGBoost en precisión, tiempo de entrenamiento y costo operativo.

3. **Random Forest — línea base de machine learning**
   - Es robusto, relativamente simple de implementar y útil como primera referencia.
   - Facilita validar si modelos más complejos realmente aportan una mejora material.
   - Puede servir para pruebas iniciales y análisis de importancia de variables.

4. **Microsoft Azure Machine Learning / AutoML — opción administrada**
   - Se evaluará como alternativa para automatizar entrenamiento, despliegue y monitoreo de modelos.
   - Su adopción dependerá del costo total frente a una implementación propia en Python, del volumen procesado y de la facilidad de integración con la arquitectura del proyecto.
   - No será una dependencia obligatoria: el sistema deberá poder funcionar con modelos ejecutados en infraestructura propia.

### Criterios de evaluación

Los modelos se probarán mediante validación temporal, evitando mezclar información futura en el entrenamiento. La selección no dependerá sólo de la precisión, sino también de:

- error de pronóstico por SKU, local, categoría y horizonte;
- impacto simulado en quiebres de stock y sobrestock;
- tiempo y costo de entrenamiento e inferencia;
- capacidad de explicar y auditar las recomendaciones;
- mantenimiento, monitoreo y frecuencia de reentrenamiento;
- comportamiento ante productos nuevos, ventas intermitentes y períodos sin stock.

La arquitectura separará la interfaz de pronóstico de cada implementación. Así, el motor de reposición podrá consumir una salida estándar y cambiar entre la línea base, XGBoost, LightGBM, Random Forest o un proveedor administrado sin modificar las reglas de inventario ni el flujo de aprobación.

## Flujo operativo propuesto

```text
Centum API / Excel / CSV
          ↓
Validación y normalización
          ↓
Histórico de ventas y estado de inventario
          ↓
Pronóstico y reglas de cobertura
          ↓
Propuesta depósito → locales
          ↓
Revisión humana
          ↓
Exportación y seguimiento
```

## Principios del producto

- Recomendaciones explicables y auditables.
- Datos históricos preservados.
- Integración incremental con Centum.
- Importaciones idempotentes, sin duplicar movimientos.
- Separación entre datos originales, cálculos y decisiones aprobadas.
- Configuración por local, categoría y producto cuando sea necesario.
- Seguridad: credenciales y datos sensibles nunca se almacenan en Git.
- Medición del resultado antes de aumentar la complejidad del modelo.

## Información pendiente

Antes de implementar la integración y el motor de reposición se debe confirmar:

- definición exacta de SKU, producto, color y talle en Centum;
- endpoints disponibles y ejemplos de respuesta;
- archivos Excel/CSV actualmente utilizados;
- granularidad y antigüedad del histórico de ventas;
- forma de representar stock reservado, disponible y en tránsito;
- devoluciones, anulaciones y ventas del ecommerce;
- tiempos de preparación y entrega a cada local;
- calendario real de reposición;
- mínimos de exhibición y reglas comerciales;
- tratamiento de temporadas, promociones y productos nuevos;
- mecanismo actual para aprobar y ejecutar una reposición;
- indicadores utilizados hoy para evaluar el resultado.

## Etapas previstas

### Etapa 1 — Descubrimiento de datos

Inventariar fuentes, obtener muestras anonimizadas y definir un modelo canónico.

### Etapa 2 — Línea base

Reproducir el cálculo actual con reglas explícitas y generar propuestas en modo simulación.

### Etapa 3 — MVP operativo

Incorporar revisión, exportación, tablero y seguimiento de propuestas.

### Etapa 4 — Optimización

Comparar pronósticos, ajustar seguridad y cobertura, modelar estacionalidad y evaluar traslados entre locales.

## Estado

Proyecto en etapa de construcción de la base de datos e integración. La ingesta diaria v2 de ventas quedó activa el 23 de julio de 2026. El stock se captura en un workflow independiente todos los días a las 03:00 ART y el reporte Excel conserva su flujo operativo separado a las 05:00 ART. Esta separación evita que el procesamiento del reporte afecte la persistencia utilizada por el sistema de reposición. Al cierre del 31 de julio de 2026 el histórico continuo de ventas está validado desde el 24 de enero de 2025 hasta la actualidad mediante la ejecución `1949`. La próxima ventana pendiente, todavía sin configurar, es del 10 al 23 de enero de 2025. El backfill continuará hasta completar julio de 2024 y se detendrá allí, con una cobertura objetivo aproximada de 24 meses.

- Fuentes, resultados de auditoría y pendientes: [`docs/ESTADO_DATOS.md`](docs/ESTADO_DATOS.md).
- Revisión del workflow vigente: [`docs/REVISION_WORKFLOW_VENTAS.md`](docs/REVISION_WORKFLOW_VENTAS.md).
- Instalación y prueba controlada de la versión 2: [`docs/IMPLEMENTACION_V2_VENTAS.md`](docs/IMPLEMENTACION_V2_VENTAS.md).
- Resultado de la validación real de la v2: [`docs/VALIDACION_INGESTA_V2_2026-07-22.md`](docs/VALIDACION_INGESTA_V2_2026-07-22.md).
- Implementación y validación de inventario en Supabase: [`docs/IMPLEMENTACION_STOCK.md`](docs/IMPLEMENTACION_STOCK.md).
- Referencia técnica del workflow de stock: [`docs/WORKFLOW_STOCK_SUPABASE.md`](docs/WORKFLOW_STOCK_SUPABASE.md).
- Operación y controles diarios de stock: [`docs/OPERACION_STOCK_SUPABASE.md`](docs/OPERACION_STOCK_SUPABASE.md).
- Resolución de problemas de stock: [`docs/TROUBLESHOOTING_STOCK_SUPABASE.md`](docs/TROUBLESHOOTING_STOCK_SUPABASE.md).
- Migración del proyecto Estado de Resultados: [`docs/MIGRACION_DASH_ESTADOS_RESULTADOS.md`](docs/MIGRACION_DASH_ESTADOS_RESULTADOS.md).
- Inventario local de manuales de la API pública de Centum: [`docs/references/centum-api/`](docs/references/centum-api/).
- Plan de backfill de ventas hasta julio de 2024: [`docs/PLAN_BACKFILL_VENTAS_5_ANIOS.md`](docs/PLAN_BACKFILL_VENTAS_5_ANIOS.md).

