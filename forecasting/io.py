"""Entrada y salida local para validar el motor sin tocar producción."""

from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from .baseline import DailySale, ForecastResult


REQUIRED_COLUMNS = {
    "fecha_comprobante",
    "id_sucursal",
    "id_articulo",
    "unidades_vendidas",
}


def _number(value: str | None) -> float:
    raw = (value or "").strip().replace(" ", "")
    if not raw:
        return 0.0
    if "," in raw and "." in raw:
        raw = (
            raw.replace(".", "").replace(",", ".")
            if raw.rfind(",") > raw.rfind(".")
            else raw.replace(",", "")
        )
    elif "," in raw:
        raw = raw.replace(",", ".")
    return float(raw)


def _date(value: str) -> date:
    raw = value.strip()
    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    ):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Fecha no reconocida: {value!r}")


def load_daily_sales_csv(path: str | Path) -> list[DailySale]:
    """Carga una exportación CSV de la vista diaria canónica."""

    source = Path(path)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or ())
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError(f"Faltan columnas requeridas: {', '.join(missing)}")
        rows = []
        for row in reader:
            rows.append(
                DailySale(
                    fecha=_date(row["fecha_comprobante"]),
                    id_sucursal=int(row["id_sucursal"]),
                    id_articulo=int(row["id_articulo"]),
                    unidades_vendidas=_number(row["unidades_vendidas"]),
                    unidades_devueltas=_number(row.get("unidades_devueltas")),
                    sociedad=(row.get("sociedad") or "").strip(),
                    sucursal_nombre=(row.get("sucursal_nombre") or "").strip(),
                    sku=(row.get("sku") or "").strip(),
                    articulo_nombre=(row.get("articulo_nombre") or "").strip(),
                )
            )
    return rows


def write_forecasts_csv(
    path: str | Path, forecasts: Iterable[ForecastResult]
) -> None:
    """Escribe resultados locales; nunca conecta con Supabase."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "id_sucursal",
        "id_articulo",
        "semana_pronosticada",
        "demanda_proyectada",
        "promedio_reciente",
        "demanda_estacional",
        "semanas_historia",
        "semanas_utilizadas",
        "patron_demanda",
        "confianza",
        "modelo",
    ]
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in forecasts:
            data = asdict(result)
            key = data.pop("key")
            writer.writerow(
                {
                    "id_sucursal": key["id_sucursal"],
                    "id_articulo": key["id_articulo"],
                    **data,
                }
            )
