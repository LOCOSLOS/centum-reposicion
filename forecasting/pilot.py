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


DEFAULT_EXCLUDED_BRANCH_IDS = frozenset({6455, 9261})


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


def _aggregate_by_metadata(
    metrics: Mapping[SeriesKey, BacktestMetrics],
    metadata: Mapping[SeriesKey, dict[str, object]],
    field: str,
) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[BacktestMetrics]] = defaultdict(list)
    for key, value in metrics.items():
        label = str(metadata.get(key, {}).get(field, "") or "sin_clasificar")
        grouped[label].append(value)
    return {
        label: _aggregate_metrics(values)
        for label, values in sorted(grouped.items())
    }


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
            "grupo_articulo": str(
                row.get("grupo_articulo", "") or "sin_clasificar"
            ),
            "color": str(row.get("color", "") or "sin_clasificar"),
            "talle": str(row.get("talle", "") or "sin_clasificar"),
            "rubro": str(row.get("rubro", "") or "sin_clasificar"),
            "subrubro": str(row.get("subrubro", "") or "sin_clasificar"),
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
                "metricas_por_rubro": _aggregate_by_metadata(
                    per_series, metadata, "rubro"
                ),
                "metricas_por_subrubro": _aggregate_by_metadata(
                    per_series, metadata, "subrubro"
                ),
                "control_promedio_movil_8": {
                    "metricas_globales": recent_global,
                    "metricas_por_patron": {
                        pattern: _aggregate_metrics(values)
                        for pattern, values in sorted(recent_by_pattern.items())
                    },
                    "metricas_por_sucursal": _aggregate_by_branch(
                        recent_mean_series, metadata
                    ),
                    "metricas_por_rubro": _aggregate_by_metadata(
                        recent_mean_series, metadata, "rubro"
                    ),
                    "metricas_por_subrubro": _aggregate_by_metadata(
                        recent_mean_series, metadata, "subrubro"
                    ),
                },
                "control_pronostico_cero": {
                    "metricas_globales": zero_global,
                    "metricas_por_patron": {
                        pattern: _aggregate_metrics(values)
                        for pattern, values in sorted(zero_by_pattern.items())
                    },
                    "metricas_por_sucursal": _aggregate_by_branch(
                        zero_series, metadata
                    ),
                    "metricas_por_rubro": _aggregate_by_metadata(
                        zero_series, metadata, "rubro"
                    ),
                    "metricas_por_subrubro": _aggregate_by_metadata(
                        zero_series, metadata, "subrubro"
                    ),
                },
                "mejora_wape_vs_control": (
                    round(float(recent_wape) - float(model_wape), 4)
                    if model_wape is not None and recent_wape is not None
                    else None
                ),
                "mejora_wape_vs_cero": (
                    round(float(zero_wape) - float(model_wape), 4)
                    if model_wape is not None and zero_wape is not None
                    else None
                ),
                "evaluacion_horizonte": {
                    "horizonte_semanas": horizon_weeks,
                    "ventanas_rodantes_por_serie": max(
                        holdout_weeks - horizon_weeks + 1, 0
                    ),
                    "metricas_globales": horizon_global,
                    "metricas_por_patron": {
                        pattern: _aggregate_metrics(values)
                        for pattern, values in sorted(horizon_by_pattern.items())
                    },
                    "metricas_por_sucursal": _aggregate_by_branch(
                        horizon_series, metadata
                    ),
                    "metricas_por_rubro": _aggregate_by_metadata(
                        horizon_series, metadata, "rubro"
                    ),
                    "metricas_por_subrubro": _aggregate_by_metadata(
                        horizon_series, metadata, "subrubro"
                    ),
                    "control_promedio_movil_8": {
                        "metricas_globales": horizon_control_global,
                        "metricas_por_patron": {
                            pattern: _aggregate_metrics(values)
                            for pattern, values in sorted(
                                horizon_control_by_pattern.items()
                            )
                        },
                        "metricas_por_sucursal": _aggregate_by_branch(
                            horizon_control_series, metadata
                        ),
                        "metricas_por_rubro": _aggregate_by_metadata(
                            horizon_control_series, metadata, "rubro"
                        ),
                        "metricas_por_subrubro": _aggregate_by_metadata(
                            horizon_control_series, metadata, "subrubro"
                        ),
                    },
                    "control_pronostico_cero": {
                        "metricas_globales": horizon_zero_global,
                        "metricas_por_patron": {
                            pattern: _aggregate_metrics(values)
                            for pattern, values in sorted(
                                horizon_zero_by_pattern.items()
                            )
                        },
                        "metricas_por_sucursal": _aggregate_by_branch(
                            horizon_zero_series, metadata
                        ),
                        "metricas_por_rubro": _aggregate_by_metadata(
                            horizon_zero_series, metadata, "rubro"
                        ),
                        "metricas_por_subrubro": _aggregate_by_metadata(
                            horizon_zero_series, metadata, "subrubro"
                        ),
                    },
                    "mejora_wape_vs_control": (
                        round(
                            float(horizon_control_wape) - float(horizon_wape),
                            4,
                        )
                        if horizon_wape is not None
                        and horizon_control_wape is not None
                        else None
                    ),
                    "mejora_wape_vs_cero": (
                        round(
                            float(horizon_zero_wape) - float(horizon_wape),
                            4,
                        )
                        if horizon_wape is not None
                        and horizon_zero_wape is not None
                        else None
                    ),
                },
            }
        )

    next_week = common_last_week + timedelta(weeks=1)
    forecasts = []
    for key, series in padded.items():
        result = forecast_weekly(key, series, next_week, config=cfg)
        forecasts.append(
            {
                **metadata[key],
                **{
                    name: value
                    for name, value in asdict(result).items()
                    if name != "key"
                },
            }
        )
    forecasts.sort(key=lambda value: float(value["demanda_proyectada"]), reverse=True)

    return {
        "dataset": {
            "filas": len(retail_rows),
            "series": len(padded),
            "desde": global_first.isoformat(),
            "hasta": global_last.isoformat(),
            "semana_pronosticada": next_week.isoformat(),
            "sucursales_excluidas": sorted(excluded),
            "filas_excluidas": excluded_rows,
            "series_excluidas_sucursal": len(excluded_series),
            "rubros": len(
                {str(row.get("rubro", "") or "sin_clasificar") for row in retail_rows}
            ),
            "subrubros": len(
                {
                    str(row.get("subrubro", "") or "sin_clasificar")
                    for row in retail_rows
                }
            ),
            "grupos_articulo": len(
                {
                    str(row.get("grupo_articulo", "") or "sin_clasificar")
                    for row in retail_rows
                }
            ),
            "colores": len(
                {str(row.get("color", "") or "sin_clasificar") for row in retail_rows}
            ),
            "talles": len(
                {str(row.get("talle", "") or "sin_clasificar") for row in retail_rows}
            ),
            "patrones": {
                pattern: sum(value == pattern for value in patterns.values())
                for pattern in sorted(set(patterns.values()))
            },
        },
        "evaluaciones": evaluations,
        "pronosticos_mayores": forecasts[:10],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdout-weeks", type=int, default=8)
    parser.add_argument("--horizon-weeks", type=int, default=4)
    parser.add_argument("--recent-weeks", type=int, default=10)
    parser.add_argument("--recent-decay", type=float, default=0.96)
    parser.add_argument("--seasonal-weight", type=float, default=0.05)
    parser.add_argument(
        "--demand-basis", choices=("gross", "net"), default="net"
    )
    parser.add_argument(
        "--intermittent-model",
        choices=("recent_mean", "tsb", "hybrid"),
        default="hybrid",
    )
    parser.add_argument("--intermittent-demand-alpha", type=float, default=0.10)
    parser.add_argument("--intermittent-probability-beta", type=float, default=0.10)
    parser.add_argument("--intermittent-hybrid-weight", type=float, default=0.25)
    args = parser.parse_args()
    if args.holdout_weeks <= 0:
        parser.error("--holdout-weeks debe ser positivo")
    if args.horizon_weeks <= 0 or args.horizon_weeks > args.holdout_weeks:
        parser.error("--horizon-weeks debe estar entre 1 y --holdout-weeks")
    config = BaselineConfig(
        recent_weeks=args.recent_weeks,
        recent_decay=args.recent_decay,
        seasonal_weight=args.seasonal_weight,
        intermittent_model=args.intermittent_model,
        intermittent_demand_alpha=args.intermittent_demand_alpha,
        intermittent_probability_beta=args.intermittent_probability_beta,
        intermittent_hybrid_weight=args.intermittent_hybrid_weight,
        demand_basis=args.demand_basis,
    )
    rows = _load_rows(json.load(sys.stdin))
    json.dump(
        evaluate(
            rows,
            holdout_weeks=args.holdout_weeks,
            horizon_weeks=args.horizon_weeks,
            config=config,
        ),
        sys.stdout,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
