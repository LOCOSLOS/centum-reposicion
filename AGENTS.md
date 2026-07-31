# AGENTS.md — Proyecto: Forecast & Reposición (reemplazo In-Season/Analyticalways)

## Objetivo
Reemplazar el módulo In-Season de Analyticalways (proyección de demanda + sugerencia de reposición) por una solución propia orquestada con n8n, para dejar de pagar la licencia.

## Alcance confirmado
- **Incluye**: proyección de demanda semanal y sugerencia de reposición por producto-talle-sucursal.
- **No incluye**: Pre-Season (planificación de colecciones), Sales Team Management, ni funcionalidades de VM/display rules de In-Season.

## Decisiones ya tomadas
- No es viable resolver el forecasting con nodos de n8n solamente (Function nodes con fórmulas). Se necesita una capa de cálculo separada (Python: promedio móvil ponderado + ajuste estacional, o similar), orquestada pero no ejecutada por n8n.
- Arquitectura en capas:
  1. **Extracción**: n8n trae de Centum ventas + stock por producto-talle-sucursal → Neon Postgres.
  2. **Cálculo**: script Python (ejecutado vía n8n o como servicio separado) que calcula demanda proyectada y sugerencia de reposición (proyección − stock actual − pendiente de entrada, con umbral de lead time).
  3. **Output**: tabla en Postgres → tablero (mismo patrón HTML que el dashboard de KPIs, o Looker Studio).

## Confirmado por Pablo
1. Hay posibilidad de carga histórica desde Centum con filtro de fecha desde/hasta.
2. Se registra quiebre de stock (necesario para no subestimar demanda real en productos con rotura).

## Abierto / sin confirmar (bloqueante antes de programar la extracción)
- **Granularidad real del endpoint `EstadisticaVentaRanking`** de la API de Centum: no está confirmado si el "artículo" devuelto discrimina talle, o si es necesario cruzar con otro endpoint para obtener la variante.
- Si se puede filtrar simultáneamente por sucursal física + rango de fechas en la misma llamada.
- Profundidad de histórico disponible sin paginación excesiva.
- **Próximo paso concreto**: hacer una llamada de prueba a `EstadisticaVentaRanking` (o revisar `Artículos/Ventas` en `API_Pública.pdf`) con una ventana corta (1 semana) para inspeccionar la respuesta cruda antes de programar la extracción completa.

## Referencias del proyecto
- `API_Pública.pdf` y `API_Pública_-_Anexo_Ejemplos.pdf` en project knowledge — usar grep por nombre de campo específico, no lectura completa.
- Patrón de node de Centum ya usado en `Dashboard KPI de Ventas` (auth SHA1 por división: Endronsa 1, EndronPrueba 2, NichSRL 3, Capaysa 6) — reutilizable para esta extracción.
- Neon Postgres (proyecto "n8n test", São Paulo) ya conectado a Looker Studio — reutilizable como destino de esta tabla.

## Reglas de trabajo (aplican a este repo)
- **Idioma**: responder SIEMPRE en español.
- **Confirmación previa**: SIEMPRE consultar y esperar el OK explícito del usuario antes de avanzar con cualquier cambio que deba realizar. No ejecutar cambios sin aprobación previa.
- No tocar ni rehacer código fuera del alcance específico pedido en cada sesión.
- No generar documentación/deliverables hasta validar cada etapa con datos reales de Centum.
- Priorizar prueba en producción con datos reales sobre staging extendido.

## Acceso operativo a n8n
- Antes de concluir que n8n no está accesible, revisar `env.download`: allí están configuradas `N8N_BASE_URL` y `N8N_API_KEY`.
- Para consultar o actualizar workflows, usar primero la API de n8n con esas variables; no pedir login mientras esa API responda autenticada.
- No mostrar, copiar ni registrar el valor de `N8N_API_KEY` en respuestas, comandos visibles, documentación o commits.
- Modificar únicamente el workflow y los campos autorizados, verificar el resultado con una lectura posterior y no ejecutar el workflow salvo pedido explícito.
