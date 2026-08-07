from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from forecasting.baseline import (
    BaselineConfig,
    DailySale,
    SeriesKey,
    aggregate_weekly,
    backtest_weekly,
    forecast_all,
    forecast_weekly,
)
from forecasting.io import _date, load_daily_sales_csv, write_forecasts_csv
from forecasting.pilot import _backtest_horizon, _backtest_zero, evaluate


MONDAY = date(2026, 7, 6)
KEY = SeriesKey(id_sucursal=16, id_articulo=11594240003)


class ForecastingBaselineTests(unittest.TestCase):
    def test_default_config_uses_validated_retail_parameters(self) -> None:
        config = BaselineConfig()
        self.assertEqual(config.demand_basis, "net")
        self.assertEqual(config.recent_weeks, 10)
        self.assertEqual(config.recent_decay, 0.96)
        self.assertEqual(config.seasonal_weight, 0.05)
        self.assertEqual(config.intermittent_model, "hybrid")
        self.assertEqual(config.intermittent_demand_alpha, 0.10)
        self.assertEqual(config.intermittent_probability_beta, 0.10)
        self.assertEqual(config.intermittent_hybrid_weight, 0.25)
        self.assertEqual(config.excluded_skus, frozenset({"ENVIO", "AP9002"}))

    def test_aggregation_uses_net_demand_and_excludes_operational_skus(self) -> None:
        sales = [
            DailySale(
                MONDAY,
                16,
                10,
                4,
                unidades_devueltas=2,
                sociedad="A",
                sku="SKU-10",
            ),
            DailySale(MONDAY + timedelta(days=1), 16, 10, 3, sociedad="B", sku="SKU-10"),
            DailySale(MONDAY, 16, 99, 8, sociedad="A", sku="Envio"),
            DailySale(MONDAY, 16, 100, 13009, sociedad="A", sku="AP9002"),
        ]
        weekly = aggregate_weekly(sales)
        self.assertEqual(weekly[SeriesKey(16, 10)][MONDAY], 5)
        self.assertNotIn(SeriesKey(16, 99), weekly)
        self.assertNotIn(SeriesKey(16, 100), weekly)

    def test_net_basis_never_creates_negative_demand(self) -> None:
        sale = DailySale(MONDAY, 16, 10, 2, unidades_devueltas=5)
        weekly = aggregate_weekly(
            [sale], config=BaselineConfig(demand_basis="net")
        )
        self.assertEqual(weekly[SeriesKey(16, 10)][MONDAY], 0)

    def test_recent_weeks_receive_more_weight(self) -> None:
        target = MONDAY + timedelta(weeks=4)
        weekly = {
            MONDAY: 1,
            MONDAY + timedelta(weeks=1): 1,
            MONDAY + timedelta(weeks=2): 1,
            MONDAY + timedelta(weeks=3): 9,
        }
        result = forecast_weekly(
            KEY,
            weekly,
            target,
            config=BaselineConfig(recent_weeks=4, recent_decay=0.5),
        )
        self.assertGreater(result.demanda_proyectada, 4)
        self.assertLess(result.demanda_proyectada, 9)

    def test_seasonal_reference_is_blended_when_available(self) -> None:
        target = MONDAY + timedelta(weeks=53)
        weekly = {
            MONDAY + timedelta(weeks=i): 2 for i in range(53)
        }
        weekly[target - timedelta(weeks=52)] = 10
        result = forecast_weekly(
            KEY,
            weekly,
            target,
            config=BaselineConfig(seasonal_weight=0.5),
        )
        self.assertEqual(result.demanda_estacional, 10)
        self.assertGreater(result.demanda_proyectada, result.promedio_reciente)
        self.assertEqual(result.confianza, "alta")

    def test_stockout_week_is_not_treated_as_zero_demand(self) -> None:
        target = MONDAY + timedelta(weeks=5)
        weekly = {
            MONDAY + timedelta(weeks=0): 5,
            MONDAY + timedelta(weeks=1): 5,
            MONDAY + timedelta(weeks=2): 5,
            MONDAY + timedelta(weeks=3): 5,
            MONDAY + timedelta(weeks=4): 0,
        }
        regular = forecast_weekly(KEY, weekly, target).demanda_proyectada
        censored = forecast_weekly(
            KEY,
            weekly,
            target,
            censored_weeks={MONDAY + timedelta(weeks=4)},
        ).demanda_proyectada
        self.assertGreater(censored, regular)
        self.assertAlmostEqual(censored, 5)

    def test_intermittent_demand_is_classified_and_non_negative(self) -> None:
        target = MONDAY + timedelta(weeks=8)
        weekly = {
            MONDAY + timedelta(weeks=i): (3 if i in {1, 6} else 0)
            for i in range(8)
        }
        result = forecast_weekly(KEY, weekly, target)
        self.assertEqual(result.patron_demanda, "intermitente")
        self.assertEqual(result.modelo, "hibrido_intermitente_v1")
        self.assertGreaterEqual(result.demanda_proyectada, 0)

    def test_intermittent_forecast_decays_after_weeks_without_sales(self) -> None:
        first_target = MONDAY + timedelta(weeks=5)
        initial = {
            MONDAY: 5,
            MONDAY + timedelta(weeks=1): 0,
            MONDAY + timedelta(weeks=2): 0,
            MONDAY + timedelta(weeks=3): 0,
            MONDAY + timedelta(weeks=4): 0,
        }
        config = BaselineConfig(intermittent_model="tsb")
        first = forecast_weekly(KEY, initial, first_target, config=config)
        later = forecast_weekly(
            KEY,
            {
                **initial,
                **{
                    first_target + timedelta(weeks=i): 0
                    for i in range(4)
                },
            },
            first_target + timedelta(weeks=4),
            config=config,
        )
        self.assertLess(later.demanda_proyectada, first.demanda_proyectada)

    def test_hybrid_intermittent_blends_recent_mean_and_tsb(self) -> None:
        target = MONDAY + timedelta(weeks=8)
        weekly = {
            MONDAY + timedelta(weeks=i): (6 if i in {1, 6} else 0)
            for i in range(8)
        }
        recent = forecast_weekly(
            KEY,
            weekly,
            target,
            config=BaselineConfig(intermittent_model="recent_mean"),
        )
        tsb = forecast_weekly(
            KEY,
            weekly,
            target,
            config=BaselineConfig(
                intermittent_model="tsb",
                intermittent_demand_alpha=0.10,
                intermittent_probability_beta=0.10,
            ),
        )
        hybrid = forecast_weekly(
            KEY,
            weekly,
            target,
            config=BaselineConfig(
                intermittent_model="hybrid",
                intermittent_demand_alpha=0.10,
                intermittent_probability_beta=0.10,
                intermittent_hybrid_weight=0.50,
            ),
        )
        self.assertEqual(hybrid.modelo, "hibrido_intermitente_v1")
        self.assertAlmostEqual(
            hybrid.demanda_proyectada,
            (recent.demanda_proyectada + tsb.demanda_proyectada) / 2,
        )

    def test_hybrid_weight_must_be_between_zero_and_one(self) -> None:
        with self.assertRaises(ValueError):
            BaselineConfig(intermittent_hybrid_weight=1.01)

    def test_current_incomplete_week_is_not_used(self) -> None:
        target = MONDAY + timedelta(weeks=3)
        weekly = {
            MONDAY: 2,
            MONDAY + timedelta(weeks=1): 4,
            target: 100,
        }
        result = forecast_weekly(KEY, weekly, target)
        self.assertLess(result.demanda_proyectada, 10)
        # La semana anterior sin filas se completa con cero, pero la semana
        # objetivo (todavía incompleta) no participa del cálculo.
        self.assertEqual(result.semanas_historia, 3)

    def test_backtest_returns_auditable_metrics(self) -> None:
        weekly = {
            MONDAY + timedelta(weeks=i): 4 for i in range(20)
        }
        metrics = backtest_weekly(KEY, weekly, holdout_weeks=6)
        self.assertEqual(metrics.observaciones, 6)
        self.assertAlmostEqual(metrics.mae, 0)
        self.assertAlmostEqual(metrics.wape or 0, 0)
        self.assertAlmostEqual(metrics.sesgo_medio, 0)

    def test_backtest_includes_weeks_without_sales(self) -> None:
        weekly = {
            MONDAY: 2,
            MONDAY + timedelta(weeks=4): 2,
        }
        metrics = backtest_weekly(KEY, weekly, holdout_weeks=3)
        self.assertEqual(metrics.observaciones, 3)
        self.assertEqual(metrics.demanda_real_total, 2)

    def test_backtest_accepts_a_fixed_training_window(self) -> None:
        weekly = {
            MONDAY + timedelta(weeks=i): 4 for i in range(30)
        }
        metrics = backtest_weekly(
            KEY,
            weekly,
            holdout_weeks=4,
            training_window_weeks=12,
        )
        self.assertEqual(metrics.observaciones, 4)
        self.assertAlmostEqual(metrics.mae, 0)

    def test_n8n_iso_timestamp_is_accepted(self) -> None:
        self.assertEqual(_date("2026-07-06T00:00:00.000Z"), MONDAY)

    def test_four_week_horizon_uses_rolling_windows(self) -> None:
        weekly = {
            MONDAY + timedelta(weeks=i): 5 for i in range(70)
        }
        metrics = _backtest_horizon(
            KEY,
            weekly,
            holdout_weeks=8,
            training_window_weeks=52,
            horizon_weeks=4,
            config=BaselineConfig(seasonal_weight=0),
        )
        self.assertEqual(metrics.observaciones, 5)
        self.assertEqual(metrics.demanda_real_total, 100)
        self.assertAlmostEqual(metrics.mae, 0)

    def test_zero_control_uses_the_same_rolling_horizon(self) -> None:
        weekly = {
            MONDAY + timedelta(weeks=i): 5 for i in range(10)
        }
        metrics = _backtest_zero(
            weekly,
            holdout_weeks=4,
            horizon_weeks=2,
        )
        self.assertEqual(metrics.observaciones, 3)
        self.assertEqual(metrics.demanda_real_total, 30)
        self.assertEqual(metrics.demanda_proyectada_total, 0)
        self.assertAlmostEqual(metrics.wape or 0, 1)
        self.assertAlmostEqual(metrics.sesgo_medio, -10)

    def test_pilot_reports_zero_control_and_metrics_by_branch(self) -> None:
        rows = []
        for branch_id, branch_name in (
            (6455, "Deposito central"),
            (9261, "Mayorista"),
            (6458, "Salguero"),
            (8774, "Boedo"),
        ):
            for week in range(10):
                rows.append(
                    {
                        "fecha_comprobante": (
                            MONDAY + timedelta(weeks=week)
                        ).isoformat(),
                        "id_sucursal": branch_id,
                        "sucursal_nombre": branch_name,
                        "id_articulo": 10,
                        "sku": "SKU-10",
                        "grupo_articulo": (
                            "Medias Base" if branch_id == 6458 else "Remeras Base"
                        ),
                        "color": "Negro" if branch_id == 6458 else "Blanco",
                        "talle": "U" if branch_id == 6458 else "M",
                        "rubro": (
                            "Mayorista"
                            if branch_id in (6455, 9261)
                            else "Medias"
                            if branch_id == 6458
                            else "Remeras"
                        ),
                        "subrubro": (
                            "Canal"
                            if branch_id in (6455, 9261)
                            else "Dama"
                            if branch_id == 6458
                            else "Hombre"
                        ),
                        "unidades_vendidas": 2,
                        "patron_muestra": "regular",
                    }
                )
        result = evaluate(
            rows,
            windows=(4,),
            holdout_weeks=2,
            horizon_weeks=2,
        )
        evaluation = result["evaluaciones"][0]
        self.assertEqual(
            result["dataset"]["sucursales_excluidas"], [6455, 9261]
        )
        self.assertEqual(result["dataset"]["series_excluidas_sucursal"], 2)
        self.assertEqual(result["dataset"]["series"], 2)
        self.assertEqual(result["dataset"]["rubros"], 2)
        self.assertEqual(result["dataset"]["subrubros"], 2)
        self.assertEqual(result["dataset"]["grupos_articulo"], 2)
        self.assertEqual(result["dataset"]["colores"], 2)
        self.assertEqual(result["dataset"]["talles"], 2)
        self.assertEqual(
            {item["grupo_articulo"] for item in result["pronosticos_mayores"]},
            {"Medias Base", "Remeras Base"},
        )
        self.assertEqual(
            {item["color"] for item in result["pronosticos_mayores"]},
            {"Negro", "Blanco"},
        )
        self.assertEqual(
            {item["talle"] for item in result["pronosticos_mayores"]},
            {"U", "M"},
        )
        self.assertEqual(
            evaluation["control_pronostico_cero"]["metricas_globales"]["wape"],
            1,
        )
        self.assertEqual(
            [
                branch["sucursal_nombre"]
                for branch in evaluation["metricas_por_sucursal"]
            ],
            ["Salguero", "Boedo"],
        )
        self.assertEqual(
            sorted(evaluation["metricas_por_rubro"]),
            ["Medias", "Remeras"],
        )
        self.assertEqual(
            sorted(evaluation["metricas_por_subrubro"]),
            ["Dama", "Hombre"],
        )
        self.assertIn(
            "control_pronostico_cero", evaluation["evaluacion_horizonte"]
        )

    def test_csv_round_trip_uses_real_view_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "ventas.csv"
            target = Path(temp_dir) / "forecast.csv"
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "fecha_comprobante",
                        "sociedad",
                        "id_sucursal",
                        "sucursal_nombre",
                        "id_articulo",
                        "sku",
                        "articulo_nombre",
                        "unidades_vendidas",
                        "unidades_devueltas",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "fecha_comprobante": "2026-07-06",
                        "sociedad": "Endron",
                        "id_sucursal": "16",
                        "sucursal_nombre": "Salguero",
                        "id_articulo": "10",
                        "sku": "SKU-10",
                        "articulo_nombre": "Artículo",
                        "unidades_vendidas": "2",
                        "unidades_devueltas": "1",
                    }
                )
            sales = load_daily_sales_csv(source)
            forecasts = forecast_all(sales, date(2026, 7, 13))
            write_forecasts_csv(target, forecasts)
            self.assertEqual(len(sales), 1)
            self.assertEqual(len(forecasts), 1)
            self.assertIn("demanda_proyectada", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
