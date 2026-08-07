"""Línea base auditable de pronóstico semanal.

El módulo usa solamente la biblioteca estándar. No accede a bases de datos ni
escribe resultados productivos. La unidad de cálculo es artículo-sucursal y el
stock físico compartido hace que las ventas de distintas sociedades se sumen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from math import isfinite
from typing import Iterable, Mapping


@dataclass(frozen=True, order=True)
class SeriesKey:
    """Identifica una serie de demanda compatible con la clave de stock."""

    id_sucursal: int
    id_articulo: int


@dataclass(frozen=True)
class DailySale:
    """Fila diaria normalizada desde vw_ventas_diarias_articulo_sucursal."""

    fecha: date
    id_sucursal: int
    id_articulo: int
    unidades_vendidas: float
    unidades_devueltas: float = 0.0
    sociedad: str = ""
    sucursal_nombre: str = ""
    sku: str = ""
    articulo_nombre: str = ""

    def __post_init__(self) -> None:
        if self.id_sucursal <= 0:
            raise ValueError("id_sucursal debe ser positivo")
        if self.id_articulo <= 0:
            raise ValueError("id_articulo debe ser positivo")
        if not isfinite(self.unidades_vendidas) or self.unidades_vendidas < 0:
            raise ValueError("unidades_vendidas debe ser un número no negativo")
        if not isfinite(self.unidades_devueltas) or self.unidades_devueltas < 0:
            raise ValueError("unidades_devueltas debe ser un número no negativo")


@dataclass(frozen=True)
class BaselineConfig:
    """Parámetros explícitos y versionables del modelo base."""

    recent_weeks: int = 10
    recent_decay: float = 0.96
    seasonal_lag_weeks: int = 52
    seasonal_weight: float = 0.05
    minimum_history_weeks: int = 4
    intermittent_zero_share: float = 0.50
    intermittent_model: str = "hybrid"
    intermittent_demand_alpha: float = 0.10
    intermittent_probability_beta: float = 0.10
    intermittent_hybrid_weight: float = 0.25
    demand_basis: str = "net"
    excluded_skus: frozenset[str] = field(
        default_factory=lambda: frozenset({"ENVIO", "AP9002"})
    )

    def __post_init__(self) -> None:
        if self.recent_weeks <= 0:
            raise ValueError("recent_weeks debe ser positivo")
        if not 0 < self.recent_decay <= 1:
            raise ValueError("recent_decay debe estar entre 0 y 1")
        if self.seasonal_lag_weeks <= 0:
            raise ValueError("seasonal_lag_weeks debe ser positivo")
        if not 0 <= self.seasonal_weight <= 1:
            raise ValueError("seasonal_weight debe estar entre 0 y 1")
        if self.minimum_history_weeks <= 0:
            raise ValueError("minimum_history_weeks debe ser positivo")
        if not 0 <= self.intermittent_zero_share <= 1:
            raise ValueError("intermittent_zero_share debe estar entre 0 y 1")
        if self.intermittent_model not in {"recent_mean", "tsb", "hybrid"}:
            raise ValueError(
                "intermittent_model debe ser 'recent_mean', 'tsb' o 'hybrid'"
            )
        if not 0 < self.intermittent_demand_alpha <= 1:
            raise ValueError("intermittent_demand_alpha debe estar entre 0 y 1")
        if not 0 < self.intermittent_probability_beta <= 1:
            raise ValueError("intermittent_probability_beta debe estar entre 0 y 1")
        if not 0 <= self.intermittent_hybrid_weight <= 1:
            raise ValueError("intermittent_hybrid_weight debe estar entre 0 y 1")
        if self.demand_basis not in {"gross", "net"}:
            raise ValueError("demand_basis debe ser 'gross' o 'net'")


@dataclass(frozen=True)
class ForecastResult:
    key: SeriesKey
    semana_pronosticada: date
    demanda_proyectada: float
    promedio_reciente: float
    demanda_estacional: float | None
    semanas_historia: int
    semanas_utilizadas: int
    patron_demanda: str
    confianza: str
    modelo: str = "wma_estacional_v1"


@dataclass(frozen=True)
class BacktestMetrics:
    observaciones: int
    mae: float
    wape: float | None
    sesgo_medio: float
    demanda_real_total: float
    demanda_proyectada_total: float


WeeklySeries = dict[date, float]


def week_start(value: date) -> date:
    """Devuelve el lunes de la semana ISO de value."""

    return value - timedelta(days=value.weekday())


def _demand_units(sale: DailySale, basis: str) -> float:
    if basis == "gross":
        return sale.unidades_vendidas
    return max(sale.unidades_vendidas - sale.unidades_devueltas, 0.0)


def aggregate_weekly(
    sales: Iterable[DailySale],
    *,
    config: BaselineConfig | None = None,
) -> dict[SeriesKey, WeeklySeries]:
    """Agrupa ventas por semana, sucursal y artículo.

    Las sociedades se suman porque el stock físico está compartido. Se excluyen
    servicios configurados, como el SKU ``Envio``.
    """

    cfg = config or BaselineConfig()
    excluded = {value.strip().upper() for value in cfg.excluded_skus}
    weekly: dict[SeriesKey, WeeklySeries] = {}
    for sale in sales:
        if sale.sku.strip().upper() in excluded:
            continue
        key = SeriesKey(sale.id_sucursal, sale.id_articulo)
        monday = week_start(sale.fecha)
        series = weekly.setdefault(key, {})
        series[monday] = series.get(monday, 0.0) + _demand_units(
            sale, cfg.demand_basis
        )
    return weekly


def _complete_history(
    weekly: Mapping[date, float], forecast_week: date
) -> WeeklySeries:
    completed = {
        week_start(week): max(float(units), 0.0)
        for week, units in weekly.items()
        if week_start(week) < forecast_week
    }
    if not completed:
        return {}
    current = min(completed)
    last = forecast_week - timedelta(weeks=1)
    result: WeeklySeries = {}
    while current <= last:
        result[current] = completed.get(current, 0.0)
        current += timedelta(weeks=1)
    return result


def _weighted_recent(
    history: Mapping[date, float],
    forecast_week: date,
    config: BaselineConfig,
    censored_weeks: set[date],
) -> tuple[float, int]:
    selected: list[tuple[int, float]] = []
    week = forecast_week - timedelta(weeks=1)
    age = 0
    while week >= min(history, default=forecast_week):
        if week not in censored_weeks:
            selected.append((age, history.get(week, 0.0)))
            if len(selected) >= config.recent_weeks:
                break
        week -= timedelta(weeks=1)
        age += 1
    if not selected:
        return 0.0, 0
    weights = [config.recent_decay**age for age, _ in selected]
    weighted = sum(value * weight for (_, value), weight in zip(selected, weights))
    return weighted / sum(weights), len(selected)


def _demand_pattern(values: list[float], config: BaselineConfig) -> str:
    if not values:
        return "sin_historia"
    zero_share = sum(value == 0 for value in values) / len(values)
    if zero_share >= config.intermittent_zero_share:
        return "intermitente"
    return "regular"


def _tsb_intermittent(
    history: Mapping[date, float],
    config: BaselineConfig,
    censored_weeks: set[date],
) -> float:
    """Pronostica demanda intermitente con el metodo TSB.

    Estima por separado el tamano de una venta y la probabilidad semanal de
    que ocurra. La probabilidad disminuye durante periodos prolongados sin
    ventas, algo importante para articulos que pierden vigencia.
    """

    demand_size: float | None = None
    probability = 0.0
    alpha = config.intermittent_demand_alpha
    beta = config.intermittent_probability_beta
    for week in sorted(history):
        if week in censored_weeks:
            continue
        demand = history[week]
        occurred = demand > 0
        probability = beta * float(occurred) + (1 - beta) * probability
        if occurred:
            demand_size = (
                demand
                if demand_size is None
                else alpha * demand + (1 - alpha) * demand_size
            )
    return probability * (demand_size or 0.0)


def _mean_recent(
    history: Mapping[date, float],
    forecast_week: date,
    config: BaselineConfig,
    censored_weeks: set[date],
) -> float:
    values: list[float] = []
    week = forecast_week - timedelta(weeks=1)
    while week >= min(history, default=forecast_week):
        if week not in censored_weeks:
            values.append(history.get(week, 0.0))
            if len(values) >= config.recent_weeks:
                break
        week -= timedelta(weeks=1)
    return sum(values) / len(values) if values else 0.0


def _confidence(history_weeks: int, seasonal_available: bool) -> str:
    if seasonal_available and history_weeks >= 52:
        return "alta"
    if history_weeks >= 12:
        return "media"
    return "baja"


def forecast_weekly(
    key: SeriesKey,
    weekly: Mapping[date, float],
    forecast_week: date,
    *,
    config: BaselineConfig | None = None,
    censored_weeks: Iterable[date] = (),
) -> ForecastResult:
    """Pronostica una semana con promedio ponderado y referencia estacional.

    ``censored_weeks`` representa semanas con quiebre de stock. Esas semanas no
    participan del promedio reciente ni de la referencia estacional para evitar
    interpretar falta de disponibilidad como falta de demanda.
    """

    cfg = config or BaselineConfig()
    target = week_start(forecast_week)
    history = _complete_history(weekly, target)
    censored = {week_start(value) for value in censored_weeks}
    recent, used = _weighted_recent(history, target, cfg, censored)
    seasonal_week = target - timedelta(weeks=cfg.seasonal_lag_weeks)
    seasonal = (
        history.get(seasonal_week)
        if seasonal_week in history and seasonal_week not in censored
        else None
    )
    values = [
        value for week, value in history.items() if week not in censored
    ]
    pattern = _demand_pattern(values, cfg)
    if len(history) < cfg.minimum_history_weeks:
        pattern = "historia_insuficiente" if history else "sin_historia"
    if pattern == "intermitente":
        if cfg.intermittent_model == "tsb":
            projected = _tsb_intermittent(history, cfg, censored)
            model = "tsb_intermitente_v1"
        elif cfg.intermittent_model == "hybrid":
            recent_intermittent = _mean_recent(history, target, cfg, censored)
            tsb_intermittent = _tsb_intermittent(history, cfg, censored)
            projected = (
                recent_intermittent * (1 - cfg.intermittent_hybrid_weight)
                + tsb_intermittent * cfg.intermittent_hybrid_weight
            )
            model = "hibrido_intermitente_v1"
        else:
            projected = _mean_recent(history, target, cfg, censored)
            model = "media_intermitente_v1"
        seasonal_output = None
    else:
        if seasonal is None:
            projected = recent
        else:
            projected = (
                recent * (1 - cfg.seasonal_weight)
                + seasonal * cfg.seasonal_weight
            )
        model = "wma_estacional_v1"
        seasonal_output = seasonal
    return ForecastResult(
        key=key,
        semana_pronosticada=target,
        demanda_proyectada=max(projected, 0.0),
        promedio_reciente=max(recent, 0.0),
        demanda_estacional=seasonal_output,
        semanas_historia=len(history),
        semanas_utilizadas=used,
        patron_demanda=pattern,
        confianza=_confidence(len(history), seasonal_output is not None),
        modelo=model,
    )


def forecast_all(
    sales: Iterable[DailySale],
    as_of: date,
    *,
    config: BaselineConfig | None = None,
    censored_by_key: Mapping[SeriesKey, Iterable[date]] | None = None,
) -> list[ForecastResult]:
    """Genera un pronóstico por serie para la semana de ``as_of``."""

    cfg = config or BaselineConfig()
    weekly = aggregate_weekly(sales, config=cfg)
    censored_by_key = censored_by_key or {}
    target = week_start(as_of)
    return [
        forecast_weekly(
            key,
            series,
            target,
            config=cfg,
            censored_weeks=censored_by_key.get(key, ()),
        )
        for key, series in sorted(weekly.items())
    ]


def backtest_weekly(
    key: SeriesKey,
    weekly: Mapping[date, float],
    *,
    holdout_weeks: int = 8,
    training_window_weeks: int | None = None,
    config: BaselineConfig | None = None,
    censored_weeks: Iterable[date] = (),
) -> BacktestMetrics:
    """Evalúa el modelo mediante pronósticos rodantes sobre semanas conocidas."""

    if holdout_weeks <= 0:
        raise ValueError("holdout_weeks debe ser positivo")
    if training_window_weeks is not None and training_window_weeks <= 0:
        raise ValueError("training_window_weeks debe ser positivo")
    cfg = config or BaselineConfig()
    normalized = {week_start(week): max(float(value), 0.0) for week, value in weekly.items()}
    if not normalized:
        raise ValueError("No hay historia para realizar backtesting")
    completed: WeeklySeries = {}
    current = min(normalized)
    last = max(normalized)
    while current <= last:
        completed[current] = normalized.get(current, 0.0)
        current += timedelta(weeks=1)
    if len(completed) <= holdout_weeks:
        raise ValueError("No hay historia suficiente para el backtesting solicitado")
    test_weeks = sorted(completed)[-holdout_weeks:]
    actuals: list[float] = []
    predictions: list[float] = []
    for target in test_weeks:
        training = {week: value for week, value in completed.items() if week < target}
        if training_window_weeks is not None:
            first_training_week = target - timedelta(weeks=training_window_weeks)
            training = {
                week: value
                for week, value in training.items()
                if week >= first_training_week
            }
        prediction = forecast_weekly(
            key,
            training,
            target,
            config=cfg,
            censored_weeks=censored_weeks,
        ).demanda_proyectada
        actuals.append(completed[target])
        predictions.append(prediction)
    errors = [abs(predicted - actual) for predicted, actual in zip(predictions, actuals)]
    signed = [predicted - actual for predicted, actual in zip(predictions, actuals)]
    actual_total = sum(actuals)
    return BacktestMetrics(
        observaciones=len(actuals),
        mae=sum(errors) / len(errors),
        wape=(sum(errors) / actual_total) if actual_total > 0 else None,
        sesgo_medio=sum(signed) / len(signed),
        demanda_real_total=actual_total,
        demanda_proyectada_total=sum(predictions),
    )
