"""Ejecucion reproducible del forecast y la reposicion en modo simulacion.

Acepta filas exportadas desde n8n, calcula el forecast completo y genera una
salida apta para revision humana. No conecta con servicios externos.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import timedelta
from math import isfinite
from pathlib import Path
from typing import Iterable, Mapping

from .baseline import SeriesKey, forecast_all, week_start
from .pilot import _daily_sale, _forecast_usage
from .replenishment import (
    ELIGIBLE_FORECAST_USE,
    ReplenishmentConfig,
    ReplenishmentForecast,
    ReplenishmentSuggestion,
    StockRecord,
    TransitRecord,
    normalize_odt_transit,
    simulate_replenishment,
)


DEFAULT_FORECAST_NODE = "Postgres - Ventas semanales piloto"
DEFAULT_INVENTORY_NODE = "Postgres - Ventas semanales piloto"


@dataclass(frozen=True)
class InputIssue:
    source: str
    reason: str
    id_sucursal: int | None = None
    id_articulo: int | None = None
    reference: str = ""


@dataclass(frozen=True)
class SimulationRun:
    suggestions: list[ReplenishmentSuggestion]
    summary: dict[str, object]
    issues: list[InputIssue]


def _n8n_items_to_rows(items: object) -> list[dict[str, object]]:
    if not isinstance(items, list):
        raise ValueError("La salida de n8n debe ser un arreglo de items")
    rows: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Cada item de n8n debe ser un objeto")
        row = item.get("json", item)
        if not isinstance(row, dict):
            raise ValueError("Cada item debe contener un objeto json")
        rows.append(row)
    return rows


def extract_json_rows(payload: object, *, node_name: str) -> list[dict[str, object]]:
    """Extrae filas de una lista o de una respuesta completa de ejecucion n8n."""

    if isinstance(payload, list):
        rows = _n8n_items_to_rows(payload)
    elif isinstance(payload, dict):
        try:
            runs = payload["data"]["resultData"]["runData"][node_name]
        except (KeyError, TypeError) as exc:
            raise ValueError(
                f"No se encontro el nodo {node_name!r} en la ejecucion"
            ) from exc
        if not isinstance(runs, list):
            raise ValueError("runData del nodo debe ser un arreglo")
        rows = []
        for run in runs:
            try:
                outputs = run["data"]["main"][0]
            except (KeyError, IndexError, TypeError) as exc:
                raise ValueError("La ejecucion no contiene una salida main valida") from exc
            rows.extend(_n8n_items_to_rows(outputs))
    else:
        raise ValueError("La entrada JSON debe ser un arreglo o una ejecucion n8n")
    if not rows:
        raise ValueError("La entrada no contiene filas")
    return rows


def load_json_rows(path: str | Path, *, node_name: str) -> list[dict[str, object]]:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        return extract_json_rows(json.load(handle), node_name=node_name)


def _positive_int(value: object, field_name: str) -> int:
    number = int(value)
    if number <= 0:
        raise ValueError(f"{field_name} debe ser positivo")
    return number


def _finite_number(value: object, field_name: str) -> float:
    number = float(value or 0)
    if not isfinite(number):
        raise ValueError(f"{field_name} debe ser finito")
    return number


def normalize_inventory_rows(
    rows: Iterable[Mapping[str, object]],
) -> tuple[
    list[StockRecord],
    list[TransitRecord],
    dict[SeriesKey, str],
    list[InputIssue],
]:
    """Normaliza stock, sucursales y ODT sin corregir datos invalidos."""

    materialized = list(rows)
    branch_map: dict[str, int] = {}
    for row in materialized:
        if row.get("tipo") != "sucursal":
            continue
        try:
            branch_id = _positive_int(row.get("id_sucursal"), "id_sucursal")
        except (TypeError, ValueError):
            continue
        name = str(row.get("sucursal_nombre") or "").strip()
        if name:
            branch_map[name] = branch_id

    accepted_stock: list[StockRecord] = []
    blocked: dict[SeriesKey, str] = {}
    issues: list[InputIssue] = []
    for row in materialized:
        if row.get("tipo") != "stock":
            continue
        try:
            key = SeriesKey(
                _positive_int(row.get("id_sucursal"), "id_sucursal"),
                _positive_int(row.get("id_articulo"), "id_articulo"),
            )
        except (TypeError, ValueError):
            issues.append(InputIssue("stock", "clave_stock_invalida"))
            continue
        try:
            existences = _finite_number(row.get("existencias"), "existencias")
            committed = _finite_number(
                row.get("stock_comprometido"), "stock_comprometido"
            )
        except (TypeError, ValueError):
            blocked[key] = "stock_local_invalido"
            issues.append(
                InputIssue(
                    "stock", "cantidad_stock_invalida", key.id_sucursal, key.id_articulo
                )
            )
            continue
        if committed < 0:
            blocked[key] = "stock_comprometido_negativo"
            issues.append(
                InputIssue(
                    "stock",
                    "stock_comprometido_negativo",
                    key.id_sucursal,
                    key.id_articulo,
                    reference=str(committed),
                )
            )
            continue
        try:
            accepted_stock.append(
                StockRecord(
                    key=key,
                    existences=existences,
                    committed_stock=committed,
                )
            )
        except ValueError:
            blocked[key] = "stock_local_invalido"
            issues.append(
                InputIssue(
                    "stock", "cantidad_stock_invalida", key.id_sucursal, key.id_articulo
                )
            )

    if blocked:
        accepted_stock = [row for row in accepted_stock if row.key not in blocked]

    odt_rows = [row for row in materialized if row.get("tipo") == "odt"]
    transit, rejected_transit = normalize_odt_transit(
        odt_rows,
        branch_ids_by_name=branch_map,
    )
    for rejected in rejected_transit:
        issues.append(
            InputIssue(
                source="odt",
                reason=rejected.reason,
                reference="|".join(
                    (
                        rejected.document_number,
                        rejected.article_key,
                        rejected.destination_branch_name,
                    )
                ),
            )
        )
    return accepted_stock, transit, blocked, issues


def run_simulation(
    forecast_rows: list[dict[str, object]],
    inventory_rows: list[dict[str, object]],
    *,
    config: ReplenishmentConfig | None = None,
    display_minimum_units: float = 0.0,
    dispatch_multiple: int = 1,
) -> SimulationRun:
    """Ejecuta forecast y reposicion completos usando solamente memoria local."""

    if display_minimum_units < 0:
        raise ValueError("display_minimum_units debe ser no negativo")
    if dispatch_multiple <= 0:
        raise ValueError("dispatch_multiple debe ser positivo")
    cfg = config or ReplenishmentConfig()
    sales = [_daily_sale(row) for row in forecast_rows]
    next_week = week_start(max(sale.fecha for sale in sales)) + timedelta(weeks=1)
    forecasts = forecast_all(sales, next_week)
    metadata = {
        SeriesKey(int(row["id_sucursal"]), int(row["id_articulo"])): row
        for row in forecast_rows
    }
    replenishment_forecasts: list[ReplenishmentForecast] = []
    for result in forecasts:
        row = metadata[result.key]
        replenishment_forecasts.append(
            ReplenishmentForecast(
                key=result.key,
                forecast_week=result.semana_pronosticada,
                weekly_demand=result.demanda_proyectada,
                forecast_use=_forecast_usage(row),
                branch_name=str(row.get("sucursal_nombre") or ""),
                display_minimum_units=display_minimum_units,
                dispatch_multiple=dispatch_multiple,
            )
        )

    stock, transit, blocked, issues = normalize_inventory_rows(inventory_rows)
    suggestions = simulate_replenishment(
        replenishment_forecasts,
        stock,
        transit,
        config=cfg,
        blocked_stock_reasons=blocked,
    )
    statuses = Counter(item.status for item in suggestions)
    reasons = Counter(item.reason for item in suggestions)
    issue_reasons = Counter(item.reason for item in issues)
    eligible = sum(
        forecast.forecast_use == ELIGIBLE_FORECAST_USE
        for forecast in replenishment_forecasts
    )
    positive = [item for item in suggestions if item.suggested_units > 0]
    summary: dict[str, object] = {
        "estado": "SIMULACION_OK",
        "solo_simulacion": True,
        "requiere_revision_humana": True,
        "semana_pronosticada": next_week.isoformat(),
        "parametros": {
            "semanas_cobertura": cfg.coverage_weeks,
            "semanas_stock_seguridad": cfg.safety_stock_weeks,
            "minimo_exhibicion_unidades": display_minimum_units,
            "multiplo_despacho": dispatch_multiple,
        },
        "entradas": {
            "filas_forecast": len(forecast_rows),
            "filas_inventario": len(inventory_rows),
            "filas_stock_validas": len(stock),
            "filas_odt_validas": len(transit),
            "incidencias": len(issues),
            "incidencias_por_motivo": dict(sorted(issue_reasons.items())),
        },
        "resultados": {
            "series_pronosticadas": len(replenishment_forecasts),
            "series_elegibles": eligible,
            "por_estado": dict(sorted(statuses.items())),
            "por_motivo": dict(sorted(reasons.items())),
            "series_con_sugerencia": len(positive),
            "unidades_sugeridas": sum(item.suggested_units for item in positive),
            "articulos_sugeridos": len({item.key.id_articulo for item in positive}),
            "sucursales_con_sugerencia": len(
                {item.key.id_sucursal for item in positive}
            ),
        },
    }
    return SimulationRun(suggestions=suggestions, summary=summary, issues=issues)


SUGGESTION_FIELDS = [
    "id_sucursal",
    "id_articulo",
    "forecast_week",
    "branch_name",
    "status",
    "reason",
    "weekly_demand",
    "coverage_weeks",
    "safety_stock_weeks",
    "demand_during_coverage",
    "safety_stock_units",
    "display_minimum_units",
    "target_stock",
    "local_existences",
    "local_committed_stock",
    "local_available_stock",
    "inbound_transit",
    "raw_need",
    "dispatch_multiple",
    "theoretical_units",
    "suggested_units",
    "depot_available_before",
    "depot_available_after",
    "simulation_only",
    "requires_human_review",
]


def write_simulation_csv(
    path: str | Path, suggestions: Iterable[ReplenishmentSuggestion]
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUGGESTION_FIELDS)
        writer.writeheader()
        for suggestion in suggestions:
            row = asdict(suggestion)
            key = row.pop("key")
            writer.writerow(
                {
                    "id_sucursal": key["id_sucursal"],
                    "id_articulo": key["id_articulo"],
                    **row,
                }
            )


def write_simulation_summary(path: str | Path, run: SimulationRun) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **run.summary,
        "incidencias": [asdict(issue) for issue in run.issues],
    }
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
