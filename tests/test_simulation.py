from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from forecasting.simulation import (
    extract_json_rows,
    run_simulation,
    write_simulation_csv,
    write_simulation_summary,
)


MONDAY = date(2026, 6, 1)


def forecast_rows() -> list[dict[str, object]]:
    rows = []
    for index in range(8):
        rows.append(
            {
                "fecha_comprobante": (MONDAY + timedelta(weeks=index)).isoformat(),
                "sociedad": "",
                "id_sucursal": 6458,
                "sucursal_nombre": "16 - Local de Salguero",
                "id_articulo": 10,
                "sku": "SKU-10",
                "articulo_nombre": "Articulo 10",
                "unidades_vendidas": 2,
                "unidades_devueltas": 0,
                "cohorte_historia": "maduro_52_mas",
                "estado_actividad": "venta_reciente",
                "es_segunda_seleccion": False,
            }
        )
    return rows


def inventory_rows(
    *,
    committed: float = 0,
    depot_committed: float = 0,
    transit: float = 0,
) -> list[dict[str, object]]:
    rows = [
        {
            "tipo": "sucursal",
            "id_sucursal": 6458,
            "sucursal_nombre": "16 - Local de Salguero",
            "id_articulo": 0,
        },
        {
            "tipo": "stock",
            "id_sucursal": 6458,
            "sucursal_nombre": "16 - Local de Salguero",
            "id_articulo": 10,
            "existencias": 3,
            "stock_comprometido": committed,
        },
        {
            "tipo": "stock",
            "id_sucursal": 6455,
            "sucursal_nombre": "01",
            "id_articulo": 10,
            "existencias": 20,
            "stock_comprometido": depot_committed,
        },
    ]
    if transit:
        rows.append(
            {
                "tipo": "odt",
                "id_articulo": 10,
                "numero_documento": "00001-00043183",
                "sucursal_desde_nombre": "Gallardo",
                "sucursal_hacia_nombre": "16 - Local de Salguero",
                "clave": "10",
                "cantidad_pendiente": transit,
            }
        )
    return rows


class SimulationTests(unittest.TestCase):
    def test_extracts_plain_rows_and_complete_n8n_execution(self) -> None:
        rows = forecast_rows()
        self.assertEqual(extract_json_rows(rows, node_name="Nodo"), rows)
        payload = {
            "data": {
                "resultData": {
                    "runData": {
                        "Nodo": [
                            {"data": {"main": [[{"json": rows[0]}]]}},
                            {"data": {"main": [[{"json": rows[1]}]]}},
                        ]
                    }
                }
            }
        }
        self.assertEqual(
            extract_json_rows(payload, node_name="Nodo"), rows[:2]
        )

    def test_full_simulation_generates_an_auditable_suggestion(self) -> None:
        run = run_simulation(forecast_rows(), inventory_rows())
        self.assertEqual(len(run.suggestions), 1)
        suggestion = run.suggestions[0]
        self.assertEqual(suggestion.status, "sugerida")
        self.assertEqual(suggestion.target_stock, 8)
        self.assertEqual(suggestion.local_available_stock, 3)
        self.assertEqual(suggestion.suggested_units, 5)
        self.assertEqual(run.summary["estado"], "SIMULACION_OK")
        self.assertTrue(run.summary["solo_simulacion"])

    def test_live_odt_format_reduces_the_suggestion(self) -> None:
        run = run_simulation(
            forecast_rows(), inventory_rows(transit=2)
        )
        suggestion = run.suggestions[0]
        self.assertEqual(suggestion.inbound_transit, 2)
        self.assertEqual(suggestion.suggested_units, 3)

    def test_negative_committed_stock_is_blocked_and_reported(self) -> None:
        run = run_simulation(
            forecast_rows(), inventory_rows(committed=-1)
        )
        suggestion = run.suggestions[0]
        self.assertEqual(suggestion.status, "revision_manual")
        self.assertEqual(suggestion.reason, "stock_comprometido_negativo")
        self.assertEqual(suggestion.suggested_units, 0)
        self.assertEqual(len(run.issues), 1)
        self.assertEqual(
            run.summary["entradas"]["incidencias_por_motivo"],
            {"stock_comprometido_negativo": 1},
        )

    def test_invalid_depot_stock_blocks_every_allocation_for_the_article(self) -> None:
        run = run_simulation(
            forecast_rows(), inventory_rows(depot_committed=-1)
        )
        suggestion = run.suggestions[0]
        self.assertEqual(suggestion.status, "revision_manual")
        self.assertEqual(suggestion.reason, "stock_deposito_invalido")
        self.assertEqual(suggestion.suggested_units, 0)

    def test_outputs_include_all_series_and_input_issues(self) -> None:
        run = run_simulation(
            forecast_rows(), inventory_rows(committed=-1)
        )
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "simulacion.csv"
            json_path = Path(directory) / "resumen.json"
            write_simulation_csv(csv_path, run.suggestions)
            write_simulation_summary(json_path, run)
            with csv_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reason"], "stock_comprometido_negativo")
        self.assertEqual(payload["estado"], "SIMULACION_OK")
        self.assertEqual(
            payload["incidencias"][0]["reason"],
            "stock_comprometido_negativo",
        )


if __name__ == "__main__":
    unittest.main()
