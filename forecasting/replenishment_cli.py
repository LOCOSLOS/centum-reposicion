"""Genera una simulacion de reposicion desde exportaciones JSON de n8n."""

from __future__ import annotations

import argparse
import json

from .replenishment import ReplenishmentConfig
from .simulation import (
    DEFAULT_FORECAST_NODE,
    DEFAULT_INVENTORY_NODE,
    load_json_rows,
    run_simulation,
    write_simulation_csv,
    write_simulation_summary,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecast-input", required=True)
    parser.add_argument("--inventory-input", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--forecast-node", default=DEFAULT_FORECAST_NODE)
    parser.add_argument("--inventory-node", default=DEFAULT_INVENTORY_NODE)
    parser.add_argument("--coverage-weeks", type=float, default=4.0)
    parser.add_argument("--safety-stock-weeks", type=float, default=0.0)
    parser.add_argument("--display-minimum-units", type=float, default=0.0)
    parser.add_argument("--dispatch-multiple", type=int, default=1)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    forecast_rows = load_json_rows(args.forecast_input, node_name=args.forecast_node)
    inventory_rows = load_json_rows(
        args.inventory_input, node_name=args.inventory_node
    )
    run = run_simulation(
        forecast_rows,
        inventory_rows,
        config=ReplenishmentConfig(
            coverage_weeks=args.coverage_weeks,
            safety_stock_weeks=args.safety_stock_weeks,
        ),
        display_minimum_units=args.display_minimum_units,
        dispatch_multiple=args.dispatch_multiple,
    )
    write_simulation_csv(args.output_csv, run.suggestions)
    write_simulation_summary(args.summary_output, run)
    print(json.dumps(run.summary, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
