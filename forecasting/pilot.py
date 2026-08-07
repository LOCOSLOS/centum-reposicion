"""Evaluacion local del dataset semanal piloto exportado por n8n.

Lee por entrada estandar un arreglo JSON con las filas del nodo Postgres y
devuelve metricas agregadas. No conecta ni escribe en servicios externos.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import date, timedelta
from typing import Iterable, Mapping

from .baseline import (
    BacktestMetrics,
    BaselineConfig,
    DailySale,
    SeriesKey,
    aggregate_weekly,
    backtest_weekly,
    forecast_weekly,
    week_start,
)
from .io import _date, _number


DEFAULT_EXCLUDED_BRANCH_IDS = frozenset({6455})


def _load_rows(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, list):
        raise ValueError("La entrada debe ser un arreglo JSON")
    rows: list[dict[str, object]] = []
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("Cada fila debe ser un objeto JSON")
        rows.append(row)
    if not rows:
        raise ValueError("El dataset esta vacio")
    return rows


def _daily_sale(row: dict[str, object]) -> DailySale:
    return DailySale(
        fecha=_date(str(row["fecha_comprobante"])),
        id_sucursal=int(row["id_sucursal"]),
        id_articulo=int(row["id_articulo"]),
        unidades_vendidas=_number(str(row.get("unidades_vendidas", "0"))),
        unidades_devueltas=_number(str(row.get("unidades_devueltas", "0"))),
        sociedad=str(row.get("sociedad", "") or ""),
        sucursal_nombre=str(row.get("sucursal_nombre", "") or ""),
        sku=str(row.get("sku", "") or ""),
        articulo_nombre=str(row.get("articulo_nombre", "") or ""),
    )


def _aggregate_metrics(metrics: Iterable[BacktestMetrics]) -> dict[str, object]:
    values = list(metrics)
    observations = sum(value.observaciones for value in values)
    actual = sum(value.demanda_real_total for value in values)
    projected = sum(value.demanda_proyectada_total for value in values)
    absolute_error = sum(value.mae * value.observaciones for value in values)
    signed_error = sum(value.sesgo_medio * value.observaciones for value in values)
    return {
        "series": len(values),
        "observaciones": observations,
        "mae": round(absolute_error / observations, 4) if observations else None,
        "wape": round(absolute_error / actual, 4) if actual else None,
        "sesgo_medio": round(signed_error / observations, 4) if observations else None,
        "demanda_real_total": round(actual, 4),
        "demanda_proyectada_total": round(projected, 4),
    }


def _metrics_from_predictions(
    actuals: list[float], predictions: list[float]
) -> BacktestMetrics:
    if not actuals or len(actuals) != len(predictions):
        raise ValueError("Se requieren observaciones reales y proyectadas equivalentes")
    absolute_errors = [
        abs(predicted - actual)
        for predicted, actual in zip(predictions, actuals)
    ]
    signed_errors = [
        predicted - actual
        for predicted, actual in zip(predictions, actuals)
    ]
    actual_total = sum(actuals)
    return BacktestMetrics(
        observaciones=len(actuals),
        mae=sum(absolute_errors) / len(absolute_errors),
        wape=(sum(absolute_errors) / actual_total) if actual_total else None,
        sesgo_medio=sum(signed_errors) / len(signed_errors),
        demanda_real_total=actual_total,
        demanda_proyectada_total=sum(predictions),
    )


def _backtest_recent_mean(
    weekly: dict[date, float],
    *,
    holdout_weeks: int,
    training_window_weeks: int,
    recent_weeks: int = 8,
) -> BacktestMetrics:
    first = min(weekly)
    last = max(weekly)
    completed: dict[date, float] = {}
    current = first
    while current <= last:
        completed[current] = weekly.get(current, 0.0)
        current += timedelta(weeks=1)
    targets = sorted(completed)[-holdout_weeks:]
    actuals: list[float] = []
    predictions: list[float] = []
    for target in targets:
        start = target - timedelta(weeks=training_window_weeks)
        training = {
            week: value
            for week, value in completed.items()
            if start <= week < target
        }
        recent = [training[week] for week in sorted(training)[-recent_weeks:]]
        predictions.append(sum(recent) / len(recent) if recent else 0.0)
        actuals.append(completed[target])
    return _metrics_from_predictions(actuals, predictions)


def _backtest_zero(
    weekly: dict[date, float],
    *,
    holdout_weeks: int,
    horizon_weeks: int = 1,
) -> BacktestMetrics:
    """Evalua el control ingenuo que siempre pronostica demanda cero."""

    if horizon_weeks <= 0 or horizon_weeks > holdout_weeks:
        raise ValueError("El horizonte debe estar entre 1 y holdout_weeks")
    first = min(weekly)
    last = max(weekly)
    completed: dict[date, float] = {}
    current = first
    while current <= last:
        completed[current] = weekly.get(current, 0.0)
        current += timedelta(weeks=1)
    first_origin = last - timedelta(weeks=holdout_weeks - 1)
    last_origin = last - timedelta(weeks=horizon_weeks - 1)
    actuals: list[float] = []
    origin = first_origin
    while origin <= last_origin:
        actuals.append(
            sum(
                completed.get(origin + timedelta(weeks=offset), 0.0)
                for offset in range(horizon_weeks)
            )
        )
        origin += timedelta(weeks=1)
    return _metrics_from_predictions(actuals, [0.0] * len(actuals))


def _backtest_horizon(
    key: SeriesKey,
    weekly: dict[date, float],
    *,
    holdout_weeks: int,
    training_window_weeks: int,
    horizon_weeks: int,
    config: BaselineConfig,
    use_recent_mean_control: bool = False,
) -> BacktestMetrics:
    if horizon_weeks <= 0 or horizon_weeks > holdout_weeks:
        raise ValueError("El horizonte debe estar entre 1 y holdout_weeks")
    first = min(weekly)
    last = max(weekly)
    completed: dict[date, float] = {}
    current = first
    while current <= last:
        completed[current] = weekly.get(current, 0.0)
        current += timedelta(weeks=1)
    first_origin = last - timedelta(weeks=holdout_weeks - 1)
    last_origin = last - timedelta(weeks=horizon_weeks - 1)
    actuals: list[float] = []
    predictions: list[float] = []
    origin = first_origin
    while origin <= last_origin:
        start = origin - timedelta(weeks=training_window_weeks)
        training = {
            week: value
            for week, value in completed.items()
            if start <= week < origin
        }
        if use_recent_mean_control:
            recent = [training[week] for week in sorted(training)[-8:]]
            weekly_projection = sum(recent) / len(recent) if recent else 0.0
        else:
            weekly_projection = forecast_weekly(
                key,
                training,
                origin,
                config=config,
            ).demanda_proyectada
        horizon_actual = sum(
            completed.get(origin + timedelta(weeks=offset), 0.0)
            for offset in range(horizon_weeks)
        )
        actuals.append(horizon_actual)
        predictions.append(weekly_projection * horizon_weeks)
        origin += timedelta(weeks=1)
    return _metrics_from_predictions(actuals, predictions)


def _aggregate_by_branch(
    metrics: Mapping[SeriesKey, BacktestMetrics],
    metadata: Mapping[SeriesKey, dict[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[int, list[BacktestMetrics]] = defaultdict(list)
    names: dict[int, str] = {}
    for key, value in metrics.items():
        grouped[key.id_sucursal].append(value)
        names[key.id_sucursal] = str(
            metadata.get(key, {}).get("sucursal_nombre", "") or ""
        )
    return [
        {
            "id_sucursal": branch_id,
            "sucursal_nombre": names.get(branch_id, ""),
            **_aggregate_metrics(grouped[branch_id]),
        }
        for branch_id in sorted(grouped)
    ]


def evaluate(
    rows: list[dict[str, object]],
    *,
    windows: tuple[int, ...] = (52, 78, 104),
    holdout_weeks: int = 8,
    horizon_weeks: int = 4,
    config: BaselineConfig | None = None,
    excluded_branch_ids: Iterable[int] = DEFAULT_EXCLUDED_BRANCH_IDS,
) -> dict[str, object]:
    cfg = config or BaselineConfig()
    excluded = frozenset(int(value) for value in excluded_branch_ids)
    retail_rows = [
        row for row in rows if int(row["id_sucursal"]) not in excluded
    ]
    if not retail_rows:
        raise ValueError("El dataset minorista esta vacio despues de las exclusiones")
    excluded_rows = len(rows) - len(retail_rows)
    excluded_series = {
        (int(row["id_sucursal"]), int(row["id_articulo"]))
        for row in rows
        if int(row["id_sucursal"]) in excluded
    }
    sales = [_daily_sale(row) for row in retail_rows]
    weekly = aggregate_weekly(sales, config=cfg)
    patterns: dict[SeriesKey, str] = {}
    metadata: dict[SeriesKey, dict[str, object]] = {}
    for row in retail_rows:
        key = SeriesKey(int(row["id_sucursal"]), int(row["id_articulo"]))
        patterns[key] = str(row.get("patron_muestra", "sin_clasificar"))
        metadata[key] = {
            "id_sucursal": key.id_sucursal,
            "sucursal_nombre": str(row.get("sucursal_nombre", "") or ""),
            "id_articulo": key.id_articulo,
            "sku": str(row.get("sku", "") or ""),
            "articulo_nombre": str(row.get("articulo_nombre", "") or ""),
            "patron_muestra": patterns[key],
        }

    global_first = min(sale.fecha for sale in sales)
    global_last = max(sale.fecha for sale in sales)
    common_last_week = week_start(global_last)
    first_holdout_week = common_last_week - timedelta(weeks=holdout_weeks - 1)

    # Ausencia de fila semanal equivale a cero venta. Se agrega el extremo final
    # comun para que el backtest incluya tambien series sin ventas recientes.
    padded = {key: dict(series) for key, series in weekly.items()}
    for series in padded.values():
        series.setdefault(common_last_week, 0.0)

    evaluations: list[dict[str, object]] = []
    for window in windows:
        required_first_week = first_holdout_week - timedelta(weeks=window)
        eligible = {
            key: series
            for key, series in padded.items()
            if min(series) <= required_first_week
        }
        per_series: dict[SeriesKey, BacktestMetrics] = {}
        recent_mean_series: dict[SeriesKey, BacktestMetrics] = {}
        zero_series: dict[SeriesKey, BacktestMetrics] = {}
        horizon_series: dict[SeriesKey, BacktestMetrics] = {}
        horizon_control_series: dict[SeriesKey, BacktestMetrics] = {}
        horizon_zero_series: dict[SeriesKey, BacktestMetrics] = {}
        for key, series in eligible.items():
            per_series[key] = backtest_weekly(
                key,
                series,
                holdout_weeks=holdout_weeks,
                training_window_weeks=window,
                config=cfg,
            )
            recent_mean_series[key] = _backtest_recent_mean(
                series,
                holdout_weeks=holdout_weeks,
                training_window_weeks=window,
            )
            zero_series[key] = _backtest_zero(
                series,
                holdout_weeks=holdout_weeks,
            )
            horizon_series[key] = _backtest_horizon(
                key,
                series,
                holdout_weeks=holdout_weeks,
                training_window_weeks=window,
                horizon_weeks=horizon_weeks,
                config=cfg,
            )
            horizon_control_series[key] = _backtest_horizon(
                key,
                series,
                holdout_weeks=holdout_weeks,
                training_window_weeks=window,
                horizon_weeks=horizon_weeks,
                config=cfg,
                use_recent_mean_control=True,
            )
            horizon_zero_series[key] = _backtest_zero(
                series,
                holdout_weeks=holdout_weeks,
                horizon_weeks=horizon_weeks,
            )
        by_pattern: dict[str, list[BacktestMetrics]] = defaultdict(list)
        recent_by_pattern: dict[str, list[BacktestMetrics]] = defaultdict(list)
        zero_by_pattern: dict[str, list[BacktestMetrics]] = defaultdict(list)
        horizon_by_pattern: dict[str, list[BacktestMetrics]] = defaultdict(list)
        horizon_control_by_pattern: dict[str, list[BacktestMetrics]] = defaultdict(list)
        horizon_zero_by_pattern: dict[str, list[BacktestMetrics]] = defaultdict(list)
        for key, metrics in per_series.items():
            by_pattern[patterns.get(key, "sin_clasificar")].append(metrics)
            recent_by_pattern[patterns.get(key, "sin_clasificar")].append(
                recent_mean_series[key]
            )
            zero_by_pattern[patterns.get(key, "sin_clasificar")].append(
                zero_series[key]
            )
            horizon_by_pattern[patterns.get(key, "sin_clasificar")].append(
                horizon_series[key]
            )
            horizon_control_by_pattern[
                patterns.get(key, "sin_clasificar")
            ].append(horizon_control_series[key])
            horizon_zero_by_pattern[
                patterns.get(key, "sin_clasificar")
            ].append(horizon_zero_series[key])
        model_global = _aggregate_metrics(per_series.values())
        recent_global = _aggregate_metrics(recent_mean_series.values())
        zero_global = _aggregate_metrics(zero_series.values())
        model_wape = model_global["wape"]
        recent_wape = recent_global["wape"]
        zero_wape = zero_global["wape"]
        horizon_global = _aggregate_metrics(horizon_series.values())
        horizon_control_global = _aggregate_metrics(
            horizon_control_series.values()
        )
        horizon_zero_global = _aggregate_metrics(horizon_zero_series.values())
        horizon_wape = horizon_global["wape"]
        horizon_control_wape = horizon_control_global["wape"]
        horizon_zero_wape = horizon_zero_global["wape"]
        evaluations.append(
            {
                "ventana_entrenamiento_semanas": window,
                "holdout_semanas": holdout_weeks,
                "estado": "evaluada" if per_series else "historia_insuficiente",
                "series_elegibles": len(per_series),
                "series_excluidas": len(padded) - len(per_series),
                "metricas_globales": model_global,
                "metricas_por_patron": {
                    pattern: _aggregate_metrics(values)
                    for pattern, values in sorted(by_pattern.items())
                },
                "metricas_por_sucursal": _aggregate_by_branch(
                    per_series, metadata
                ),
                "control_prw”M≠¢Gß≤⁄Óù∆≠y‹_reference_is_blended_when_available(self) -> None:
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
        self.assertEqual(result.modelo, "media_intermitente_v1")
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
        # objetivo (todav√≠a incompleta) no participa del c√°lculo.
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
        self.assertEqual(result["dataset"]["sucursales_excluidas"], [6455])
        self.assertEqual(result["dataset"]["series_excluidas_sucursal"], 1)
        self.assertEqual(result["dataset"]["series"], 2)
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
                        "articulo_nombre": "Art√≠culo",
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
