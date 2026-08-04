"""Comando local para probar el motor con una exportación CSV."""

from __future__ import annotations

import argparse
from datetime import date

from .baseline import BaselineConfig, forecast_all
from .io import load_daily_sales_csv, write_forecasts_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pronóstico semanal base de Centum")
    parser.add_argument("--input", required=True, help="CSV de ventas diarias")
    parser.add_argument("--output", required=True, help="CSV local de pronósticos")
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=date.today(),
        help="Fecha de cálculo YYYY-MM-DD; usa su semana ISO",
    )
    parser.add_argument("--recent-weeks", type=int, default=13)
    parser.add_argument("--seasonal-weight", type=float, default=0.10)
    parser.add_argument(
        "--demand-basis", choices=("gross", "net"), default="gross"
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = BaselineConfig(
        recent_weeks=args.recent_weeks,
        seasonal_weight=args.seasonal_weight,
        demand_basis=args.demand_basis,
    )
    sales = load_daily_sales_csv(args.input)
    forecasts = forecast_all(sales, args.as_of, config=config)
    write_forecasts_csv(args.output, forecasts)
    print(f"Pronósticos generados: {len(forecasts)}")


if __name__ == "__main__":
    main()
