import argparse
import asyncio
import logging
import sqlite3
import sys
import time
import types
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel


def install_scanner_stubs():
    common_mod = types.ModuleType("hummingbot.core.data_type.common")
    common_mod.MarketDict = dict
    sys.modules["hummingbot.core.data_type.common"] = common_mod

    controllers_mod = types.ModuleType("hummingbot.strategy_v2.controllers")

    class ControllerConfigBase(BaseModel):
        id: str = "probability-gap-intraday-sampling"

    class ControllerBase:
        def __init__(self, config, market_data_provider, actions_queue, update_interval=1.0):
            self.config = config
            self.market_data_provider = market_data_provider
            self.actions_queue = actions_queue
            self.update_interval = update_interval
            self.processed_data = {}

        def logger(self):
            return logging.getLogger(self.__class__.__name__)

        def stop(self):
            return None

    controllers_mod.ControllerBase = ControllerBase
    controllers_mod.ControllerConfigBase = ControllerConfigBase
    sys.modules["hummingbot.strategy_v2.controllers"] = controllers_mod

    executor_actions_mod = types.ModuleType("hummingbot.strategy_v2.models.executor_actions")

    class ExecutorAction:
        pass

    executor_actions_mod.ExecutorAction = ExecutorAction
    sys.modules["hummingbot.strategy_v2.models.executor_actions"] = executor_actions_mod


@dataclass
class StubMarketDataProvider:
    current_ts: float
    ready: bool = True

    def time(self):
        return self.current_ts

    def set_time(self, ts: float):
        self.current_ts = ts

    def initialize_candles_feed(self, candles_config):
        return None


def sqlite_row_count(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    connection = sqlite3.connect(db_path)
    try:
        return int(connection.execute("SELECT COUNT(*) FROM probability_gap_snapshots").fetchone()[0])
    finally:
        connection.close()


def latest_rows(db_path: Path, limit: int = 5):
    if not db_path.exists():
        return []
    connection = sqlite3.connect(db_path)
    try:
        return connection.execute(
            """
            SELECT observed_at, market_slug, market_classification, snapshot_reason, best_side, best_net_edge
            FROM probability_gap_snapshots
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        connection.close()


async def run_sampling(args):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    install_scanner_stubs()
    sys.path.insert(0, "/tmp/hb_pydeps")
    sys.path.insert(0, ".")

    from controllers.generic.probability_gap_scanner import ProbabilityGapScanner, ProbabilityGapScannerConfig

    db_path = Path(args.db_path).expanduser()
    if not db_path.is_absolute():
        db_path = (Path.cwd() / db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if args.reset_db and db_path.exists():
        db_path.unlink()

    start_dt = datetime.now(tz=UTC)
    mdp = StubMarketDataProvider(current_ts=start_dt.timestamp())
    scanner = ProbabilityGapScanner(
        config=ProbabilityGapScannerConfig(
            id="probability-gap-intraday-sampling",
            snapshot_db_path=str(db_path),
            market_days_ahead=args.market_days_ahead,
            refresh_interval=args.refresh_interval,
            tradable_refresh_interval=args.tradable_refresh_interval,
            near_exit_refresh_interval=args.near_exit_refresh_interval,
            near_exit_window_minutes=args.near_exit_window_minutes,
        ),
        market_data_provider=mdp,
        actions_queue=None,
    )

    print(f"DB_PATH {db_path}")
    print(f"START {start_dt.isoformat()}")

    try:
        for iteration in range(args.iterations):
            if iteration > 0:
                time.sleep(args.sleep_seconds)
            now = datetime.now(tz=UTC)
            mdp.set_time(now.timestamp())
            await scanner.update_processed_data()
            opportunities = len(scanner.processed_data.get("opportunities", []))
            observations = len(scanner.processed_data.get("observations", []))
            rejections = len(scanner.processed_data.get("rejected_markets", []))
            error = scanner.processed_data.get("error", "")
            print(
                f"ITERATION {iteration + 1} NOW {now.isoformat()} "
                f"ROWS {sqlite_row_count(db_path)} OPP {opportunities} OBS {observations} REJ {rejections}"
                f"{f' ERROR {error}' if error else ''}"
            )
            for row in latest_rows(db_path, limit=3):
                print("  ROW", row)
    finally:
        await scanner.stop()


def parse_args():
    parser = argparse.ArgumentParser(description="Run a live probability-gap intraday sampling smoke run.")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--sleep-seconds", type=int, default=12)
    parser.add_argument("--db-path", default=".yxg/data/probability_gap_samples_iv_v1.sqlite")
    parser.add_argument("--market-days-ahead", type=int, default=1)
    parser.add_argument("--refresh-interval", type=int, default=60)
    parser.add_argument("--tradable-refresh-interval", type=int, default=10)
    parser.add_argument("--near-exit-refresh-interval", type=int, default=3)
    parser.add_argument("--near-exit-window-minutes", type=int, default=30)
    parser.add_argument("--reset-db", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run_sampling(parse_args()))
