import argparse
import json
from pathlib import Path

from controllers.generic.probability_gap_model_validation import (
    DEFAULT_SETTLEMENT_CACHE_PATH,
    fetch_binance_rule_settlements,
    fetch_gamma_markets_by_slug,
    run_model_validation,
)
from controllers.generic.probability_gap_sampling import ProbabilityGapSnapshotStore


def parse_args():
    parser = argparse.ArgumentParser(description="Validate probability-gap model edge against settlement outcomes.")
    parser.add_argument("--db-path", default=".yxg/data/probability_gap_samples_iv_v1.sqlite")
    parser.add_argument("--market-slug", default=None)
    parser.add_argument("--official-markets-json", default=None)
    parser.add_argument("--fetch-official", action="store_true")
    parser.add_argument("--fetch-binance-rule", action="store_true")
    parser.add_argument("--settlement-cache-json", default=DEFAULT_SETTLEMENT_CACHE_PATH)
    parser.add_argument("--no-settlement-cache", action="store_true")
    parser.add_argument("--http-retry-count", type=int, default=3)
    parser.add_argument("--http-backoff-seconds", type=float, default=0.5)
    parser.add_argument("--proxy-window-seconds", type=int, default=60)
    return parser.parse_args()


def main():
    args = parse_args()
    store = ProbabilityGapSnapshotStore(args.db_path)
    snapshots = store.list_snapshots(args.market_slug)
    official_markets = {}
    if args.official_markets_json:
        with Path(args.official_markets_json).expanduser().open() as stream:
            official_markets = json.load(stream)
    if args.fetch_official:
        official_markets.update(
            fetch_gamma_markets_by_slug(
                (snapshot["market_slug"] for snapshot in snapshots),
                retry_count=args.http_retry_count,
                backoff_seconds=args.http_backoff_seconds,
            )
        )
    binance_settlements = (
        fetch_binance_rule_settlements(
            snapshots,
            cache_path=None if args.no_settlement_cache else args.settlement_cache_json,
            retry_count=args.http_retry_count,
            backoff_seconds=args.http_backoff_seconds,
        )
        if args.fetch_binance_rule
        else {}
    )
    report = run_model_validation(
        snapshots,
        official_markets_by_slug=official_markets,
        binance_settlements_by_slug=binance_settlements,
        proxy_window_seconds=args.proxy_window_seconds,
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
