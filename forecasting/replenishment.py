"""Motor explicable de reposicion en modo simulacion.

No conecta con Centum, n8n ni Postgres y no genera ordenes de traspaso. La
unidad de calculo es articulo-sucursal. El stock recibido puede contener varias
secciones y se consolida antes de calcular la sugerencia.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from math import ceil, floor, isfinite
from typing import Iterable, Mapping
import unicodedata

from .baseline import (
    DEFAULT_BRANCH_CLOSURE_DATES,
    SeriesKey,
    branch_is_open_for_forecast,
)


ELIGIBLE_FORECAST_USE = "elegible_simulacion_reposicion"
DEFAULT_EXCLUDED_RETAIL_BRANCH_IDS = frozenset({6455, 9261})


def _non_negative(value: float, field_name: str) -> float:
    number = float(value)
    if not isfinite(number) or number < 0:
        raise ValueError(f"{field_name} debe ser un numero no negativo")
    return number


@dataclass(frozen=True)
class ReplenishmentConfig:
    """Politica provisional y versionable para la simulacion."""

    coverage_weeks: float = 4.0
    safety_stock_weeks: float = 0.0
    central_depot_branch_id: int = 6455
    excluded_retail_branch_ids: frozenset[int] = (
        DEFAULT_EXCLUDED_RETAIL_BRANCH_IDS
    )
    branch_closure_dates: Mapping[int, date] | None = None

    def __post_init__(self) -> None:
        _non_negative(self.coverage_weeks, "coverage_weeks")
        _non_negative(self.safety_stock_weeks, "safety_stock_weeks")
        if self.coverage_weeks == 0:
            raise ValueError("coverage_weeks debe ser mayor que cero")
        if self.central_depot_branch_id <= 0:
            raise ValueError("central_depot_branch_id debe ser positivo")

    @property
    def closures(self) -> Mapping[int, date]:
        return (
            DEFAULT_BRANCH_CLOSURE_DATES
            if self.branch_closure_dates is None
            else self.branch_closure_dates
        )


@dataclass(frozen=True)
class ReplenishmentForecast:
    key: SeriesKey
    forecast_week: date
    weekly_demand: float
    forecast_use: str
    branch_name: str = ""
    display_minimum_units: float = 0.0
    dispatch_multiple: int = 1

    def __post_init__(self) -> None:
        _non_negative(self.weekly_demand, "weekly_demand")
        _non_negative(self.display_minimum_units, "display_minimum_units")
        if self.dispatch_multiple <= 0:
            raise ValueError("dispatch_multiple debe ser positivo")


@dataclass(frozen=True)
class StockRecord:
    """Fila de ``stock_actual``; puede representar una sola seccion."""

    key: SeriesKey
    existences: float
    committed_stock: float = 0.0
    section_id: int | None = None

    def __post_init__(self) -> None:
        if not isfinite(float(self.existences)):
            raise ValueError("existences debe ser un numero finito")
        _non_negative(self.committed_stock, "committed_stock")


@dataclass(frozen=True)
class AggregatedStock:
    key: SeriesKey
    existences: float
    committed_stock: float
    sections: int

    @property
    def available(self) -> float:
        return max(self.existences - self.committed_stock, 0.0)


@dataclass(frozen=True)
class TransitRecord:
    key: SeriesKey
    pending_units: float
    document_number: str = ""
    source_branch_name: str = ""

    def __post_init__(self) -> None:
        _non_negative(self.pending_units, "pending_units")


@dataclass(frozen=True)
class RejectedTransit:
    document_number: str
    article_key: str
    destination_branch_name: str
    reason: str


@dataclass(frozen=True)
class ReplenishmentSuggestion:
    key: SeriesKey
    forecast_week: date
    branch_name: str
    status: str
    reason: str
    weekly_demand: float
    coverage_weeks: float
    safety_stock_weeks: float
    demand_during_coverage: float
    safety_stock_units: float
    display_minimum_units: float
    target_stock: float
    local_existences: float
    local_committed_stock: float
    local_available_stock: float
    inbound_transit: float
    raw_need: float
    dispatch_multiple: int
    theoretical_units: float
    suggested_units: float
    depot_available_before: float
    depot_available_after: float
    simulation_only: bool = True
    requires_human_review: bool = True


def aggregate_stock(
    records: Iterable[StockRecord],
) -> dict[SeriesKey, AggregatedStock]:
    """Suma las secciones fisicas por articulo y sucursal."""

    totals: dict[SeriesKey, list[float]] = {}
    for record in records:
        current = totals.setdefault(record.key, [0.0, 0.0, 0.0])
        current[0] += float(record.existences)
        current[1] += float(record.committed_stock)
        current[2] += 1
    return {
        key: AggregatedStock(
            key=key,
            existences=values[0],
            committed_stock=values[1],
            sections=int(values[2]),
        )
        for key, values in totals.items()
    }


def aggregate_transit(records: Iterable[TransitRecord]) -> dict[SeriesKey, float]:
    totals: dict[SeriesKey, float] = {}
    for record in records:
        totals[record.key] = totals.get(record.key, 0.0) + record.pending_units
    return totals


def _normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or "").strip().casefold())
    return " ".join(
        "".join(char for char in text if unicodedata.category(char) != "Mn")
        .replace("-", " ")
        .split()
    )


def normalize_odt_transit(
    rows: Iterable[Mapping[str, object]],
    *,
    branch_ids_by_name: Mapping[str, int],
) -> tuple[list[TransitRecord], list[RejectedTransit]]:
    """Convierte el ultimo snapshot de ODT al contrato del motor.

    ``Clave`` se interpreta como ``id_articulo`` solamente cuando contiene un
    entero positivo. El destino se resuelve por un mapa explicito de nombres;
    no se adivinan sucursales desconocidas.
    """

    branch_map = {
        _normalize_name(name): int(branch_id)
        for name, branch_id in branch_ids_by_name.items()
    }
    accepted: list[TransitRecord] = []
    rejected: list[RejectedTransit] = []
    for row in rows:
        document = str(row.get("numero_documento") or "").strip()
        article_key = str(row.get("clave") or "").strip()
        destination = str(row.get("sucursal_hacia_nombre") or "").strip()
        try:
            article_id = int(article_key)
            if article_id <= 0:
                raise ValueError
        except ValueError:
            rejected.append(
                RejectedTransit(
                    document, article_key, destination, "clave_articulo_invalida"
                )
            )
            continue
        branch_id = branch_map.get(_normalize_name(destination))
        if branch_id is None:
            rejected.append(
                RejectedTransit(
                    document, article_key, destination, "sucursal_destino_desconocida"
                )
            )
            continue
        raw_pending = row.get("cantidad_pendiente_control")
        if raw_pending is None:
            raw_pending = row.get("cantidad_pendiente")
        try:
            pending = _non_negative(float(raw_pending or 0), "cantidad_pendiente")
        except (TypeError, ValueError):
            rejected.append(
                RejectedTransit(
                    document, article_key, destination, "cantidad_pendiente_invalida"
                )
            )
            continue
        if pending == 0:
            continue
        accepted.append(
            TransitRecord(
                key=SeriesKey(branch_id, article_id),
                pending_units=pending,
                document_number=document,
                source_branch_name=str(
                    row.get("sucursal_desde_nombre") or ""
                ).strip(),
            )
        )
    return accepted, rejected


def _empty_suggestion(
    forecast: ReplenishmentForecast,
    config: ReplenishmentConfig,
    *,
    status: str,
    reason: str,
    stock: AggregatedStock | None = None,
    inbound: float = 0.0,
) -> ReplenishmentSuggestion:
    demand_coverage = forecast.weekly_demand * config.coverage_weeks
    safety = forecast.weekly_demand * config.safety_stock_weeks
    target = max(
        demand_coverage + safety,
        forecast.display_minimum_units,
    )
    local_existences = stock.existences if stock else 0.0
    local_committed = stock.committed_stock if stock else 0.0
    local_available = stock.available if stock else 0.0
    raw_need = max(target - local_available - inbound, 0.0)
    theoretical = (
        ceil(raw_need / forecast.dispatch_multiple) * forecast.dispatch_multiple
        if raw_need > 0
        else 0.0
    )
    return ReplenishmentSuggestion(
        key=forecast.key,
        forecast_week=forecast.forecast_week,
        branch_name=forecast.branch_name,
        status=status,
        reason=reason,
        weekly_demand=forecast.weekly_demand,
        coverage_weeks=config.coverage_weeks,
        safety_stock_weeks=config.safety_stock_weeks,
        demand_during_coverage=demand_coverage,
        safety_stock_units=safety,
        display_minimum_units=forecast.display_minimum_units,
        target_stock=target,
        local_existences=local_existences,
        local_committed_stock=local_committed,
        local_available_stock=local_available,
        inbound_transit=inbound,
        raw_need=raw_need,
        dispatch_multiple=forecast.dispatch_multiple,
        theoretical_units=theoretical,
        suggested_units=0.0,
        depot_available_before=0.0,
        depot_available_after=0.0,
    )


def simulate_replenishment(
    forecasts: Iterable[ReplenishmentForecast],
    stock_records: Iterable[StockRecord],
    transit_records: Iterable[TransitRecord] = (),
    *,
    config: ReplenishmentConfig | None = None,
) -> list[ReplenishmentSuggestion]:
    """Calcula sugerencias sin escribir datos ni generar movimientos."""

    cfg = config or ReplenishmentConfig()
    stock = aggregate_stock(stock_records)
    transit = aggregate_transit(transit_records)
    drafts: list[ReplenishmentSuggestion] = []

    for forecast in forecasts:
        local_stock = stock.get(forecast.key)
        inbound = transit.get(forecast.key, 0.0)
        branch_id = forecast.key.id_sucursal
        if branch_id in cfg.excluded_retail_branch_ids:
            drafts.append(
                _empty_suggestion(
                    forecast,
                    cfg,
                    status="excluida",
                    reason="sucursal_fuera_circuito_minorista",
                    stock=local_stock,
                    inbound=inbound,
                )
            )
            continue
        if not branch_is_open_for_forecast(
            branch_id, forecast.forecast_week, cfg.closures
        ):
            drafts.append(
                _empty_suggestion(
                    forecast,
                    cfg,
                    status="excluida",
                    reason="sucursal_cerrada",
                    stock=local_stock,
                    inbound=inbound,
                )
            )
            continue
        if forecast.forecast_use != ELIGIBLE_FORECAST_USE:
            drafts.append(
                _empty_suggestion(
                    forecast,
                    cfg,
                    status="revision_manual",
                    reason=forecast.forecast_use,
                    stock=local_stock,
                    inbound=inbound,
                )
            )
            continue
        if local_stock is None:
            drafts.append(
                _empty_suggestion(
                    forecast,
                    cfg,
                    status="revision_manual",
                    reason="stock_local_no_encontrado",
                    inbound=inbound,
                )
            )
            continue
        drafts.append(
            _empty_suggestion(
                forecast,
                cfg,
                status="pendiente_asignacion",
                reason="necesidad_calculada",
                stock=local_stock,
                inbound=inbound,
            )
        )

    result = list(drafts)
    by_article: dict[int, list[int]] = {}
    for index, draft in enumerate(result):
        if draft.status == "pendiente_asignacion":
            by_article.setdefault(draft.key.id_articulo, []).append(index)

    for article_id, indexes in by_article.items():
        depot_key = SeriesKey(cfg.central_depot_branch_id, article_id)
        depot_stock = stock.get(depot_key)
        if depot_stock is None:
            for index in indexes:
                result[index] = replace(
                    result[index],
                    status="revision_manual",
                    reason="stock_deposito_no_encontrado",
                )
            continue
        remaining = depot_stock.available
        ordered = sorted(
            indexes,
            key=lambda index: (
                -(result[index].raw_need / result[index].target_stock)
                if result[index].target_stock > 0
                else 0.0,
                -result[index].raw_need,
                result[index].key.id_sucursal,
            ),
        )
        for index in ordered:
            draft = result[index]
            before = remaining
            if draft.theoretical_units == 0:
                allocated = 0.0
                status = "sin_sugerencia"
                reason = "cobertura_satisfecha"
            else:
                allocatable = min(draft.theoretical_units, remaining)
                allocated = (
                    floor(allocatable / draft.dispatch_multiple)
                    * draft.dispatch_multiple
                )
                remaining -= allocated
                if allocated == draft.theoretical_units:
                    status = "sugerida"
                    reason = "necesidad_cubierta_por_deposito"
                elif allocated > 0:
                    status = "sugerida_parcial"
                    reason = "limitada_por_stock_deposito"
                else:
                    status = "sin_sugerencia"
                    reason = "stock_deposito_insuficiente"
            result[index] = replace(
                draft,
                status=status,
                reason=reason,
                suggested_units=allocated,
                depot_available_before=before,
                depot_available_after=remaining,
            )

    return sorted(result, key=lambda item: (item.key.id_sucursal, item.key.id_articulo))
