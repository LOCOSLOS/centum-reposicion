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
    DEFAULT_BRANCH_CLOSURE_DATES,
    DailySale,
    SeriesKey,
    aggregate_weekly,
    backtest_weekly,
    branch_is_open_for_forecast,
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
        "error_absoluto_total": round(absolute_error, 4),
        "wape": round(absolute_error / actual, 4) if actual else None,
        "sesgo_medio": round(signed_error / observations, 4) if observations else None,
        "demanda_real_total": round(actual, 4),
        "demanda_proyectada_total": round(projected, 4),
        "desvio_volumen_total": round(projected - actual, 4),
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


def _normalized_label(row: Mapping[str, object], field: str) -> str:
    return str(row.get(field, "") or "").strip() or "sin_clasificar"


def _seasonal_rubro_comparison(
    model: Mapping[str, dict[str, object]],
    control: Mapping[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for rubro, metrics in model.items():
        normalized = rubro.casefold()
        if "verano" not in normalized and "invierno" not in normalized:
            continue
        control_metrics = control.get(rubro, {})
        model_wape = metrics.get("wape")
        control_wape = control_metrics.get("wape")
        result[rubro] = {
            "temporada": "verano" if "verano" in normalized else "invierno",
            "modelo": metrics,
            "control_promedio_movil_8": control_metrics,
            "mejora_wape_vs_control": (
                round(float(control_wape) - float(model_wape), 4)
                if model_wape is not None and control_wape is not None
                else None
            ),
        }
    return result


def _metrics_comparison(
    model_metrics: dict[str, object],
    control_metrics: dict[str, object],
) -> dict[str, object]:
    model_wape = model_metrics.get("wape")
    control_wape = control_metrics.get("wape")
    return {
        "modelo": model_metrics,
        "control_promedio_movil_8": control_metrics,
        "mejora_wape_vs_control": (
            round(float(control_wape) - float(model_wape), 4)
            if model_wape is not None and control_wape is not None
            else None
        ),
    }


def _second_selection_comparison(
    model: Mapping[SeriesKey, BacktestMetrics],
    control: Mapping[SeriesKey, BacktestMetrics],
    metadata: Mapping[SeriesKey, dict[str, object]],
) -> dict[str, object]:
    keys = [
        key
        for key in model
        if bool(metadata.get(key, {}).get("es_segunda_seleccion", False))
    ]
    return _metrics_comparison(
        _aggregate_metrics(model[key] for key in keys),
        _aggregate_metrics(control[key] for key in keys),
    )


def _forecast_usage(metadata: Mapping[str, object]) -> str:
    if bool(metadata.get("es_segunda_seleccion", False)):
        return "revision_manual_segunda_seleccion"
    if metadata.get("cohorte_historia") == "nuevo_menos_26":
        return "revision_manual_historia_insuficiente"
    if metadata.get("cohorte_historia") == "historia_26_51":
        return "revision_manual_historia_limitada"
    if metadata.get("estado_actividad") == "sin_venta_13_mas":
        return "revision_manual_inactividad"
    return "elegible_simulacion_reposicion"


def evaluate(
    rows: list[dict[str, object]],
    *,
    windows: tuple[int, ...] = (8, 13, 26, 52, 78, 104),
    holdout_weeks: int = 8,
    horizon_weeks: int = 4,
    config: BaselineConfig | None = None,
    excluded_branch_ids: Iterable[int] = DEFAULT_EXCLUDED_BRANCH_IDS,
    branch_closure_dates: Mapping[int, date] | None = None,
) -> dict[str, object]:
    cfg = config or BaselineConfig()
    closures = (
        DEFAULT_BRANCH_CLOSURE_DATES
        if branch_closure_dates is None
        else branch_closure_dates
    )
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
            "sucursal_nombre": str(row.get("sucursal_nombre", "") or "").strip(),
            "id_articulo": key.id_articulo,
            "sku": str(row.get("sku", "") or ""),
            "articulo_nombre": str(row.get("articulo_nombre", "") or ""),
            "grupo_articulo": _normalized_label(row, "grupo_articulo"),
            "color": _normalized_label(row, "color"),
            "talle": _normalized_label(row, "talle"),
            "rubro": _normalized_label(row, "rubro"),
            "subrubro": _normalized_label(row, "subrubro"),
            "patron_muestra": patterns[key],
            "cohorte_historia": _normalized_label(row, "cohorte_historia"),
            "estado_actividad": _normalized_label(row, "estado_actividad"),
            "es_segunda_seleccion": bool(
                row.get("es_segunda_seleccion", False)
            ),
            "primera_semana": str(row.get("primera_semana", "") or ""),
            "ultima_semana_venta": str(
                row.get("ultima_semana_venta", "") or ""
            ),
            "semanas_calendario": int(row.get("semanas_calendario", 0) or 0),
            "semanas_sin_venta": int(row.get("semanas_sin_venta", 0) or 0),
        }

    global_first = min(sale.fecha for sale in sales)
    global_last = max(sale.fecha for sale in sales)
    common_last_week = week_start(global_last)
    # Ausencia de fila semanal equivale a cero venta. Se agrega el extremo final
    # comun para que el backtest incluya tambien series sin ventas recientes.
    # Las sucursales cerradas terminan en su ultima semana operativa: no se
    # inventan ceros posteriores que deformen su evaluacion historica.
    padded: dict[SeriesKey, dict[date, float]] = {}
    for key, series in weekly.items():
        last_series_week = common_last_week
        closed_on = closures.get(key.id_sucursal)
        if closed_on is not None:
            last_series_week = min(last_series_week, week_start(closed_on))
        completed = {
            week: value
            for week, value in series.items()
            if week <= last_series_week
        }
        if not completed:
            continue
        completed.setdefault(last_series_week, 0.0)
        padded[key] = completed

    evaluations: list[dict[str, object]] = []
    for window in windows:
        eligible = {
            key: series
            for key, series in padded.items()
            if min(series)
            <= max(series)
            - timedelta(weeks=holdout_weeks - 1)
            - timedelta(weeks=window)
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
        model_rubros = _aggregate_by_metadata(per_series, metadata, "rubro")
        control_rubros = _aggregate_by_metadata(
            recent_mean_series, metadata, "rubro"
        )
        horizon_rubros = _aggregate_by_metadata(
            horizon_series, metadata, "rubro"
        )
        horizon_control_rubros = _aggregate_by_metadata(
            horizon_control_series, metadata, "rubro"
        )
        model_cohorts = _aggregate_by_metadata(
            per_series, metadata, "cohorte_historia"
        )
        control_cohorts = _aggregate_by_metadata(
            recent_mean_series, metadata, "cohorte_historia"
        )
        model_activity = _aggregate_by_metadata(
            per_series, metadata, "estado_actividad"
        )
        control_activity = _aggregate_by_metadata(
            recent_mean_series, metadata, "estado_actividad"
        )
        horizon_cohorts = _aggregate_by_metadata(
            horizon_series, metadata, "cohorte_historia"
        )
        horizon_control_cohorts = _aggregate_by_metadata(
            horizon_control_series, metadata, "cohorte_historia"
        )
        horizon_activity = _aggregate_by_metadata(
            horizon_series, metadata, "estado_actividad"
        )
        horizon_control_activity = _aggregate_by_metadata(
            horizon_control_series, metadata, "estado_actividad"
        )
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
                "metricas_por_rubro": model_rubros,
                "comparacion_rubros_estacionales": _seasonal_rubro_comparison(
                    model_rubros, control_rubros
                ),
                "metricas_por_cohorte_historia": model_cohorts,
                "metricas_por_estado_actividad": model_activity,
                "comparacion_segunda_seleccion": _second_selection_comparison(
                    per_series, recent_mean_series, metadata
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
                    "metricas_por_rubro": control_rubros,
                    "metricas_por_cohorte_historia": control_cohorts,
                    "metricas_por_estado_actividad": control_activity,
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
                    "metricas_por_rubro": horizon_rubros,
                    "comparacion_rubros_estacionales": _seasonal_rubro_comparison(
                        horizon_rubros, horizon_control_rubros
                    ),
                    "metricas_por_cohorte_historia": horizon_cohorts,
                    "metricas_por_estado_actividad": horizon_activity,
                    "comparacion_segunda_seleccion": _second_selection_comparison(
                        horizon_series, horizon_control_series, metadata
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
                        "metricas_por_rubro": horizon_control_rubros,
                        "metricas_por_cohorte_historia": horizon_control_cohorts,
                        "metricas_por_estado_actividad": horizon_control_activity,
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
    closed_series = {
        key
        for key in padded
        if not branch_is_open_for_forecast(key.id_sucursal, next_week, closures)
    }
    forecasts = []
    for key, series in padded.items():
        if key in closed_series:
            continue
        result = forecast_weekly(key, series, next_week, config=cfg)
        forecasts.append(
            {
                **metadata[key],
                "uso_reposicion": _forecast_usage(metadata[key]),
                **{
                    name: value
                    for name, value in asdict(result).items()
                    if name != "key"
                },
            }
        )
    forecasts.sort(key=lambda value: float(value["demanda_proyectada"]), reverse=True)
    forecast_cohorts: dict[str, int] = defaultdict(int)
    forecast_confidence: dict[str, int] = defaultdict(int)
    forecast_usage: dict[str, int] = defaultdict(int)
    for forecast in forecasts:
        forecast_cohorts[str(forecast["cohorte_historia"])] += 1
        forecast_confidence[str(forecast["confianza"])] += 1
        forecast_usage[str(forecast["uso_reposicion"])] += 1

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
            "sucursales_cerradas_al_pronostico": [
                {
                    "id_sucursal": branch_id,
                    "sucursal_nombre": next(
                        (
                            str(value.get("sucursal_nombre", ""))
                            for key, value in metadata.items()
                            if key.id_sucursal == branch_id
                        ),
                        "",
                    ),
                    "fecha_cierre": closures[branch_id].isoformat(),
                }
                for branch_id in sorted(
                    {key.id_sucursal for key in closed_series}
                )
            ],
            "series_excluidas_cierre": len(closed_series),
            "cohortes_historia": {
                label: sum(
                    value.get("cohorte_historia") == label
                    for value in metadata.values()
                )
                for label in sorted(
                    {
                        str(value.get("cohorte_historia", "sin_clasificar"))
                        for value in metadata.values()
                    }
                )
            },
            "estados_actividad": {
                label: sum(
                    value.get("estado_actividad") == label
                    for value in metadata.values()
                )
                for label in sorted(
                    {
                        str(value.get("estado_actividad", "sin_clasificar"))
                        for value in metadata.values()
                    }
                )
            },
            "series_segunda_seleccion": sum(
                bool(value.get("es_segunda_seleccion", False))
                for value in metadata.values()
            ),
            "rubros": len(
                {_normalized_label(row, "rubro") for row in retail_rows}
            ),
            "subrubros": len(
                {
                    _normalized_label(row, "subrubro")
                    for row in retail_rows
                }
            ),
            "grupos_articulo": len(
                {
                    _normalized_label(row, "grupo_articulo")
                    for row in retail_rows
                }
            ),
            "colores": len(
                {_normalized_label(row, "color") for row in retail_rows}
            ),
            "talles": len(
                {_normalized_label(row, "talle") for row in retail_rows}
            ),
            "patrones": {
                pattern: sum(value == pattern for value in patterns.values())
                for pattern in sorted(set(patterns.values()))
            },
        },
        "evaluaciones": evaluations,
        "resumen_pronosticos": {
            "series": len(forecasts),
            "por_cohorte_historia": dict(sorted(forecast_cohorts.items())),
            "por_confianza": dict(sorted(forecast_confidence.items())),
            "por_uso_reposicion": dict(sorted(forecast_usage.items())),
            "segunda_seleccion": sum(
                bool(value.get("es_segunda_seleccion", False))
                for value in forecasts
            ),
        },
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
