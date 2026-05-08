import argparse
import json
from decimal import Decimal

from controllers.generic.probability_gap_execution_replay import (
    ExecutionReplayConfig,
    build_future_diagnostics,
    execution_diagnostics_as_dicts,
    run_execution_research,
)
from controllers.generic.probability_gap_sampling import ProbabilityGapSnapshotStore


def parse_args():
    parser = argparse.ArgumentParser(description="Run execution-aware probability-gap replay over SQLite snapshots.")
    parser.add_argument("--db-path", default=".yxg/data/probability_gap_samples_iv_v1.sqlite")
    parser.add_argument("--market-slug", default=None)
    parser.add_argument("--model-version", default="iv_digital_v1")
    parser.add_argument("--min-edge", default="0.02")
    parser.add_argument("--quote-buffer", default="0.03")
    parser.add_argument("--take-profit", default="0.03")
    parser.add_argument("--stop-loss", default="0.02")
    parser.add_argument("--time-stop-minutes", default="20")
    parser.add_argument("--cooldown-seconds", type=int, default=300)
    parser.add_argument("--min-time-to-expiry-minutes", default="15")
    parser.add_argument("--max-spread", default="0.08")
    parser.add_argument("--max-quote-wait-minutes", default="5")
    parser.add_argument(
        "--fill-assumption",
        choices=["optimistic", "conservative", "strict"],
        default="conservative",
    )
    parser.add_argument("--include-diagnostics", action="store_true")
    parser.add_argument("--include-trades", action="store_true")
    parser.add_argument("--include-parameter-grid", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    store = ProbabilityGapSnapshotStore(args.db_path)
    snapshots = store.list_snapshots(args.market_slug)
    config = ExecutionReplayConfig(
        model_version=args.model_version,
        min_edge=Decimal(args.min_edge),
        quote_buffer=Decimal(args.quote_buffer),
        take_profit=Decimal(args.take_profit),
        stop_loss=Decimal(args.stop_loss),
        time_stop_minutes=Decimal(args.time_stop_minutes),
        cooldown_seconds=args.cooldown_seconds,
        min_time_to_expiry_minutes=Decimal(args.min_time_to_expiry_minutes),
        max_spread=Decimal(args.max_spread),
        max_quote_wait_minutes=Decimal(args.max_quote_wait_minutes),
        fill_assumption=args.fill_assumption,
    )
    report = run_execution_research(snapshots, config, include_parameter_grid=args.include_parameter_grid)
    if not args.include_trades:
        report.pop("trades", None)
    if args.include_diagnostics:
        model_snapshots = [
            snapshot for snapshot in snapshots
            if snapshot.get("model_version", "") == args.model_version
        ]
        report["diagnostics"] = execution_diagnostics_as_dicts(build_future_diagnostics(model_snapshots))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
