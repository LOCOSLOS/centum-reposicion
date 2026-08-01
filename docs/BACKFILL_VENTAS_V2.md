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
- cero l�t�-�G����ƭy�                                      "sendBody":  true,
                                         "specifyBody":  "json",
                                         "jsonBody":  "={{ JSON.stringify({ FechaDocumentoDesde: $json.fechaDesde, FechaDocumentoHasta: $json.fechaHasta, IdSucursal: $json.idSucursal, IdDivisionEmpresaGrupoEconomico: $json.idDivision }) }}",
                                         "options":  {
                                                         "lowercaseHeaders":  false,
                                                         "response":  {
                                                                          "response":  {
                                                                                           "fullResponse":  true,
                                                                                           "responseFormat":  "json"
                                                                                       }
                                                                      }
                                                     }
                                     },
                      "id":  "01820add-8a8c-47eb-a245-c7f644b7737e",
                      "name":  "Obtiene Ventas",
                      "type":  "n8n-nodes-base.httpRequest",
                      "typeVersion":  4.4,
                      "position":  [
                                       448,
                                       224
                                   ],
                      "retryOnFail":  true,
                      "maxTries":  3,
                      "waitBetweenTries":  10000
                  },
                  {
                      "parameters":  {
                                         "jsCode":  "const divisionMap = {\n  1: \u0027Endron Empresa\u0027,\n  2: \u0027Endron Prueba\u0027,\n  3: \u0027Nich Empresa\u0027,\n  6: \u0027Capay\u0027\n};\n\nfunction sqlTexto(valor) {\n  if (valor === null || valor === undefined) return \u0027NULL\u0027;\n  return \"\u0027\" + String(valor).replace(/\u0027/g, \"\u0027\u0027\") + \"\u0027\";\n}\n\nfunction sqlJson(valor) {\n  return \"\u0027\" + JSON.stringify(valor).replace(/\u0027/g, \"\u0027\u0027\") + \"\u0027::jsonb\";\n}\n\nconst contexto = $(\u0027Normaliza Contexto\u0027).item.json;\nconst respuesta = $input.item.json.body ?? {};\nconst sociedad =\n  divisionMap[contexto.idDivision] ||\n  `Division ${contexto.idDivision}`;\n\nconst query = `\nselect *\nfrom centum_sync.ingestar_lote_ventas_v2(\n  ${sqlTexto(contexto.idEjecucion)},\n  ${Number(contexto.idDivision)},\n  ${sqlTexto(sociedad)},\n  ${Number(contexto.idSucursal)},\n  ${sqlTexto(contexto.sucursalNombre)},\n  ${sqlTexto(contexto.fechaDesde)}::date,\n  ${sqlTexto(contexto.fechaHasta)}::date,\n  ${sqlJson(respuesta)}\n);\n`;\n\nreturn [\n  {\n    json: {\n      query\n    }\n  }\n];"
                                     },
                      "id":  "1338f574-e90e-4fe5-8c35-2db5d1440a84",
                      "name":  "Prepara Ingesta",
                      "type":  "n8n-nodes-base.code",
                      "typeVersion":  2,
                      "position":  [
                                       672,
                                       224
                                   ]
                  },
                  {
                      "parameters":  {
                                         "operation":  "executeQuery",
                                         "query":  "{{ $json.query }}",
                                         "options":  {

                                                     }
                                     },
                      "id":  "61773a6b-4a55-43a7-acc7-073507fc7384",
                      "name":  "Ingiere Lote v2",
                      "type":  "n8n-nodes-base.postgres",
                      "typeVersion":  2.5,
                      "position":  [
                                       880,
                                       224
                                   ],
                      "credentials":  {
                                          "postgres":  {
                                                           "id":  "EHXOTkKVgCHfYUZu",
                                                           "name":  "Postgres account 2"
                                                       }
                                      }
                  },
                  {
                      "parameters":  {
                                         "operation":  "executeQuery",
                                         "query":  "UPDATE centum_sync.carga_ejecuciones_v2\nSET estado = CASE\n      WHEN lotes_procesados = lotes_esperados THEN \u0027completada\u0027\n      ELSE \u0027con_error\u0027\n    END,\n    finalizada_en = now(),\n    mensaje_error = CASE\n      WHEN lotes_procesados = lotes_esperados THEN NULL\n      ELSE concat(\u0027Se esperaban \u0027, lotes_esperados, \u0027 lotes y se procesaron \u0027, lotes_procesados)\n    END\nWHERE id_ejecucion = \u0027{{ $(\u0027Inicializa Ejecucion\u0027).first().json.idEjecucion }}\u0027\nRETURNING *;",
                                         "options":  {

                                                     }
                                     },
                      "id":  "3b614130-bcb7-411d-bf54-c39bf11f3a80",
                      "name":  "Finaliza Ejecucion",
                      "type":  "n8n-nodes-base.postgres",
                      "typeVersion":  2.5,
                      "position":  [
                                       0,
                                       0
                                   ],
                      "credentials":  {
                                          "postgres":  {
                                                           "id":  "EHXOTkKVgCHfYUZu",
                                                           "name":  "Postgres account 2"
                                                       }
                                      }
                  }
              ],
    "pinData":  {

                },
    "connections":  {
                        "Inicio Manual":  {
                                              "main":  [
                                                           [
                                                               {
                                                                   "node":  "Inicializa Ejecucion",
                                                                   "type":  "main",
                                                                   "index":  0
                                                               }
                                                           ]
                                                       ]
                                          },
                        "Inicializa Ejecucion":  {
                                                     "main":  [
                                                                  [
                                                                      {
                                                                          "node":  "Registra Ejecucion",
                                                                          "type":  "main",
                                                                          "index":  0
                                                                      }
                                                                  ]
                                                              ]
                                                 },
                        "Registra Ejecucion":  {
                                                   "main":  [
                                                                [
                                                                    {
                                                                        "node":  "Genera Consultas",
                                                                        "type":  "main",
                                                                        "index":  0
                                                                    }
                                                                ]
                                                            ]
                                               },
                        "Genera Consultas":  {
                                                 "main":  [
                                                              [
                                                                  {
                                                                      "node":  "Loop Over Items",
                                                                      "type":  "main",
                                                                      "index":  0
                                                                  }
                                                              ]
                                                          ]
                                             },
                        "Loop Over Items":  {
                                                "main":  [
                                                             [
                                                                 {
                                                                     "node":  "Finaliza Ejecucion",
                                                                     "type":  "main",
                                                                     "index":  0
                                                                 }
                                                             ],
                                                             [
                                                                 {
                                                                     "node":  "TOKEN",
                                                                     "type":  "main",
                                                                     "index":  0
                                                                 }
                                                             ]
                                                         ]
                                            },
                        "TOKEN":  {
                                      "main":  [
                                                   [
                                                       {
                                                           "node":  "Normaliza Contexto",
                                                           "type":  "main",
                                                           "index":  0
                                                       }
                                                   ]
                                               ]
                                  },
                        "Normaliza Contexto":  {
                                                   "main":  [
                                                                [
                                                                    {
                                                                        "node":  "Obtiene Ventas",
                                                                        "type":  "main",
                                                                        "index":  0
                                                                    }
                                                                ]
                                                            ]
                                               },
                        "Obtiene Ventas":  {
                                               "main":  [
                                                            [
                                                                {
                                                                    "node":  "Prepara Ingesta",
                                                                    "type":  "main",
                                                                    "index":  0
                                                                }
                                                            ]
                                                        ]
                                           },
                        "Prepara Ingesta":  {
                                                "main":  [
                                                             [
                                                                 {
                                                                     "node":  "Ingiere Lote v2",
                                                                     "type":  "main",
                                                                     "index":  0
                                                                 }
                                                             ]
                                                         ]
                                            },
                        "Ingiere Lote v2":  {
                                                "main":  [
                                                             [
                                                                 {
                                                                     "node":  "Loop Over Items",
                                                                     "type":  "main",
                                                                     "index":  0
                                                                 }
                                                             ]
                                                         ]
                                            }
                    },
    "active":  false,
    "settings":  {
                     "executionOrder":  "v1",
                     "timezone":  "America/Argentina/Buenos_Aires",
                     "saveManualExecutions":  false,
                     "saveDataSuccessExecution":  "none",
                     "saveDataErrorExecution":  "all",
                     "saveExecutionProgress":  false
                 },
    "versionId":  "63178825-677c-4420-bec2-801992dde087",
    "meta":  {
                 "sourceWorkflowId":  "hbcKc5ElvaAxpwYJ",
                 "exportedAt":  "2026-07-29",
                 "credentialsNote":  "Solo referencias de credenciales de n8n; no contiene valores secretos"
             }
}
