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

Proyecto en etapa de definición funcional y descubrimiento de datos.
