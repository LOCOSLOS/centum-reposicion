from __future__ import annotations

import unittest
from datetime import date

from forecasting.baseline import SeriesKey
from forecasting.replenishment import (
    ELIGIBLE_FORECAST_USE,
    ReplenishmentConfig,
    ReplenishmentForecast,
    StockRecord,
    TransitRecord,
    aggregate_stock,
    normalize_odt_transit,
    simulate_replenishment,
)


FORECAST_WEEK = date(2026, 8, 3)


def forecast(
    branch_id: int,
    article_id: int,
    demand: float,
    *,
    usage: str = ELIGIBLE_FORECAST_USE,
    multiple: int = 1,
) -> ReplenishmentForecast:
    return ReplenishmentForecast(
        key=SeriesKey(branch_id, article_id),
        forecast_week=FORECAST_WEEK,
        weekly_demand=demand,
        forecast_use=usage,
        dispatch_multiple=multiple,
    )


class ReplenishmentTests(unittest.TestCase):
    def test_stock_sections_are_aggregated_before_availability(self) -> None:
        key = SeriesKey(6458, 10)
        aggregated = aggregate_stock(
            [
                StockRecord(key, 3, committed_stock=1, section_id=1),
                StockRecord(key, 4, committed_stock=2, section_id=2),
            ]
        )[key]
        self.assertEqual(aggregated.existences, 7)
        self.assertEqual(aggregated.committed_stock, 3)
        self.assertEqual(aggregated.available, 4)
        self.assertEqual(aggregated.sections, 2)

    def test_transit_and_committed_stock_are_reflected_in_need(self) -> None:
        local = SeriesKey(6458, 10)
        depot = SeriesKey(6455, 10)
        result = simulate_replenishment(
            [forecast(6458, 10, 2)],
            [
                StockRecord(local, 5, committed_stock=2),
                StockRecord(depot, 20),
            ],
            [TransitRecord(local, 2)],
        )[0]
        self.assertEqual(result.target_stock, 8)
        self.assertEqual(result.local_available_stock, 3)
        self.assertEqual(result.inbound_transit, 2)
        self.assertEqual(result.raw_need, 3)
        self.assertEqual(result.suggested_units, 3)
        self.assertTrue(result.simulation_only)
        self.assertTrue(result.requires_human_review)

    def test_depot_and_wholesale_are_excluded_from_retail_circuit(self) -> None:
        records = [
            StockRecord(SeriesKey(6455, 10), 30),
            StockRecord(SeriesKey(9261, 10), 2),
        ]
        result = simulate_replenishment(
            [forecast(6455, 10, 2), forecast(9261, 10, 2)], records
        )
        self.assertEqual({item.status for item in result}, {"excluida"})
        self.assertEqual(
            {item.reason for item in result},
            {"sucursal_fuera_circuito_minorista"},
        )

    def test_membrillar_is_excluded_after_closure(self) -> None:
        result = simulate_replenishment(
            [forecast(9258, 10, 2)],
            [
                StockRecord(SeriesKey(9258, 10), 0),
                StockRecord(SeriesKey(6455, 10), 20),
            ],
        )[0]
        self.assertEqual(result.status, "excluida")
        self.assertEqual(result.reason, "sucursal_cerrada")
        self.assertEqual(result.suggested_units, 0)

    def test_non_eligible_forecast_never_generates_suggestion(self) -> None:
        result = simulate_replenishment(
            [
                forecast(
                    6458,
                    10,
                    2,
                    usage="revision_manual_historia_limitada",
                )
            ],
            [
                StockRecord(SeriesKey(6458, 10), 0),
                StockRecord(SeriesKey(6455, 10), 20),
            ],
        )[0]
        self.assertEqual(result.status, "revision_manual")
        self.assertEqual(result.suggested_units, 0)

    def test_missing_local_stock_requires_manual_review(self) -> None:
        result = simulate_replenishment(
            [forecast(6458, 10, 2)],
            [StockRecord(SeriesKey(6455, 10), 20)],
        )[0]
        self.assertEqual(result.status, "revision_manual")
        self.assertEqual(result.reason, "stock_local_no_encontrado")

    def test_depot_shortage_is_allocated_by_relative_need(self) -> None:
        article = 10
        results = simulate_replenishment(
            [
                forecast(6458, article, 2),
                forecast(6459, article, 4),
            ],
            [
                StockRecord(SeriesKey(6458, article), 4),  # falta 50 %
                StockRecord(SeriesKey(6459, article), 0),  # falta 100 %
                StockRecord(SeriesKey(6455, article), 10),
            ],
        )
        by_branch = {item.key.id_sucursal: item for item in results}
        self.assertEqual(by_branch[6459].suggested_units, 10)
        self.assertEqual(by_branch[6458].suggested_units, 0)
        self.assertEqual(
            by_branch[6458].reason, "stock_deposito_insuficiente"
        )

    def test_dispatch_multiple_is_respected_without_overallocating_depot(self) -> None:
        result = simulate_replenishment(
            [forecast(6458, 10, 2, multiple=3)],
            [
                StockRecord(SeriesKey(6458, 10), 0),
                StockRecord(SeriesKey(6455, 10), 8),
            ],
        )[0]
        self.assertEqual(result.theoretical_units, 9)
        self.assertEqual(result.suggested_units, 6)
        self.assertEqual(result.status, "sugerida_parcial")

    def test_odt_is_resolved_by_explicit_branch_map(self) -> None:
        accepted, rejected = normalize_odt_transit(
            [
                {
                    "numero_documento": "00001-00043183",
                    "clave": "11594240003",
                    "sucursal_desde_nombre": "Gallardo",
                    "sucursal_hacia_nombre": "Sálguero",
                    "cantidad_pendiente_control": 2,
                },
                {
                    "numero_documento": "2",
                    "clave": "SKU-A",
                    "sucursal_hacia_nombre": "Salguero",
                    "cantidad_pendiente_control": 1,
                },
            ],
            branch_ids_by_name={"Salguero": 6458},
        )
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0].key, SeriesKey(6458, 11594240003))
        self.assertEqual(accepted[0].pending_units, 2)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].reason, "clave_articulo_invalida")

    def test_config_can_change_coverage_and_safety_without_code_changes(self) -> None:
        result = simulate_replenishment(
            [forecast(6458, 10, 2)],
            [
                StockRecord(SeriesKey(6458, 10), 0),
                StockRecord(SeriesKey(6455, 10), 30),
            ],
            config=ReplenishmentConfig(
                coverage_weeks=2,
                safety_stock_weeks=1,
            ),
        )[0]
        self.assertEqual(result.demand_during_coverage, 4)
        self.assertEqual(result.safety_stock_units, 2)
        self.assertEqual(result.target_stock, 6)
        self.assertEqual(result.suggested_units, 6)


if __name__ == "__main__":
    unittest.main()
