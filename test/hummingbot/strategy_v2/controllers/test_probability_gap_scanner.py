import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase

from controllers.generic.probability_gap_sampling import (
    ProbabilityGapSnapshotStore,
    replay_tradable_windows,
    summarize_replays,
)
from controllers.generic.probability_gap_scanner import ProbabilityGapScanner, ProbabilityGapScannerConfig
from controllers.generic.probability_gap_scanner_utils import (
    build_binance_overlap_signal,
    build_daily_market_slug,
    calculate_probability_gap,
    evaluate_overlap_window,
    parse_polymarket_daily_market,
)


class ProbabilityGapScannerLogicTest(TestCase):
    def test_parse_polymarket_daily_market_parses_supported_market(self):
        market, rejection = parse_polymarket_daily_market(
            {
                "question": "Bitcoin Up or Down on April 16?",
                "slug": "bitcoin-up-or-down-on-april-16-2026",
                "endDate": "2026-04-16T16:00:00Z",
                "clobTokenIds": '["up-token", "down-token"]',
                "outcomes": '["Up", "Down"]',
                "description": "This market resolves to Up if the Binance 1 minute candle for BTC/USDT at 12:00 ET is higher than the previous day.",
                "resolutionSource": "https://www.binance.com/en/trade/BTC_USDT",
                "bestBid": 0.87,
                "bestAsk": 0.88,
                "outcomePrices": '["0.875", "0.125"]',
                "liquidityClob": 12000,
                "conditionId": "condition-id",
            }
        )

        self.assertIsNone(rejection)
        self.assertEqual("up-token", market.up_token_id)
        self.assertEqual("down-token", market.down_token_id)
        self.assertEqual(datetime(2026, 4, 16, 16, 0, tzinfo=UTC), market.end_time)
        self.assertEqual(datetime(2026, 4, 15, 16, 0, tzinfo=UTC), market.reference_time)

    def test_build_daily_market_slug_formats_expected_slug(self):
        self.assertEqual(
            "bitcoin-up-or-down-on-april-17-2026",
            build_daily_market_slug(datetime(2026, 4, 17, tzinfo=UTC).date()),
        )

    def test_evaluate_overlap_window_rejects_market_before_window(self):
        market, _ = parse_polymarket_daily_market(
            {
                "question": "Bitcoin Up or Down on April 17?",
                "slug": "bitcoin-up-or-down-on-april-17-2026",
                "endDate": "2026-04-17T16:00:00Z",
                "clobTokenIds": '["up-token", "down-token"]',
                "outcomes": '["Up", "Down"]',
                "description": "This market resolves using Binance BTC/USDT prices.",
                "resolutionSource": "https://www.binance.com/en/trade/BTC_USDT",
                "bestBid": 0.49,
                "bestAsk": 0.50,
                "outcomePrices": '["0.495", "0.505"]',
                "conditionId": "condition-id",
            }
        )

        rejection = evaluate_overlap_window(
            market=market,
            now=datetime(2026, 4, 16, 0, 0, tzinfo=UTC),
            min_minutes_before_settlement=Decimal("15"),
            max_minutes_before_settlement=Decimal("720"),
        )

        self.assertEqual("outside_overlap_window", rejection)

    def test_build_binance_overlap_signal_blends_option_and_spot(self):
        market, _ = parse_polymarket_daily_market(
            {
                "question": "Bitcoin Up or Down on April 16?",
                "slug": "bitcoin-up-or-down-on-april-16-2026",
                "endDate": "2026-04-16T16:00:00Z",
                "clobTokenIds": '["up-token", "down-token"]',
                "outcomes": '["Up", "Down"]',
                "description": "This market resolves using Binance BTC/USDT prices.",
                "resolutionSource": "https://www.binance.com/en/trade/BTC_USDT",
                "bestBid": 0.87,
                "bestAsk": 0.88,
                "outcomePrices": '["0.875", "0.125"]',
                "conditionId": "condition-id",
            }
        )

        signal, rejection = build_binance_overlap_signal(
            now=datetime(2026, 4, 16, 10, 0, tzinfo=UTC),
            market=market,
            reference_price=Decimal("73792.01"),
            current_spot_price=Decimal("74200"),
            latest_option_delta=Decimal("0.62"),
            latest_option_expiry=datetime(2026, 4, 17, 8, 0, tzinfo=UTC),
        )

        self.assertIsNone(rejection)
        self.assertEqual("spot_option_blend", signal.signal_kind)
        self.assertGreater(signal.signal_value, Decimal("0.55"))
        self.assertGreater(signal.overlap_penalty, ZERO := Decimal("0"))
        self.assertTrue(signal.tradable)
        self.assertEqual("overlap_window_live", signal.classification_reason)

    def test_select_latest_option_signal_interpolates_near_reference_price(self):
        scanner = ProbabilityGapScanner(
            config=ProbabilityGapScannerConfig(id="logic-select-option-signal"),
            market_data_provider=_StubMarketDataProvider(),
            actions_queue=None,
        )

        delta, expiry, lower_strike, lower_delta, upper_strike, upper_delta = scanner._select_latest_option_signal(
            target_date=datetime(2026, 4, 16, 16, 0, tzinfo=UTC),
            reference_price=Decimal("74754.2"),
            marks=[
                {"symbol": "BTC-260417-74500-C", "delta": "0.65646939"},
                {"symbol": "BTC-260417-75000-C", "delta": "0.17569006"},
                {"symbol": "BTC-260417-56000-C", "delta": "1.0"},
                {"symbol": "BTC-260418-74500-C", "delta": "0.58"},
            ],
            option_metadata={
                "BTC-260417-74500-C": {
                    "symbol": "BTC-260417-74500-C",
                    "expiryDate": 1776412800000,
                    "underlying": "BTCUSDT",
                    "side": "CALL",
                    "strikePrice": "74500",
                },
                "BTC-260417-75000-C": {
                    "symbol": "BTC-260417-75000-C",
                    "expiryDate": 1776412800000,
                    "underlying": "BTCUSDT",
                    "side": "CALL",
                    "strikePrice": "75000",
                },
                "BTC-260417-56000-C": {
                    "symbol": "BTC-260417-56000-C",
                    "expiryDate": 1776412800000,
                    "underlying": "BTCUSDT",
                    "side": "CALL",
                    "strikePrice": "56000",
                },
                "BTC-260418-74500-C": {
                    "symbol": "BTC-260418-74500-C",
                    "expiryDate": 1776499200000,
                    "underlying": "BTCUSDT",
                    "side": "CALL",
                    "strikePrice": "74500",
                },
            },
        )

        self.assertAlmostEqual(float(delta), 0.412041178628, places=6)
        self.assertEqual(datetime(2026, 4, 17, 8, 0, tzinfo=UTC), expiry)
        self.assertEqual(Decimal("74500"), lower_strike)
        self.assertEqual(Decimal("75000"), upper_strike)
        self.assertEqual(Decimal("0.65646939"), lower_delta)
        self.assertEqual(Decimal("0.17569006"), upper_delta)

    def test_calculate_probability_gap_uses_overlap_signal(self):
        market, _ = parse_polymarket_daily_market(
            {
                "question": "Bitcoin Up or Down on April 16?",
                "slug": "bitcoin-up-or-down-on-april-16-2026",
                "endDate": "2026-04-16T16:00:00Z",
                "clobTokenIds": '["up-token", "down-token"]',
                "outcomes": '["Up", "Down"]',
                "description": "This market resolves using Binance BTC/USDT prices.",
                "resolutionSource": "https://www.binance.com/en/trade/BTC_USDT",
                "bestBid": 0.87,
                "bestAsk": 0.88,
                "outcomePrices": '["0.875", "0.125"]',
                "liquidityClob": 34921.95,
                "conditionId": "condition-id",
            }
        )

        gap = calculate_probability_gap(
            market=market,
            binance_signal=Decimal("0.93"),
            estimated_cost_buffer=Decimal("0.005"),
        )

        self.assertEqual(Decimal("0.13"), gap.polymarket_down_best_ask)
        self.assertEqual(Decimal("0.05"), gap.gross_edge_up)
        self.assertEqual(Decimal("-0.06"), gap.gross_edge_down)
        self.assertEqual("UP", gap.best_side)


class _StubMarketDataProvider:
    ready = True

    def time(self):
        return datetime(2026, 4, 16, 10, 0, tzinfo=UTC).timestamp()

    def initialize_candles_feed(self, candles_config):
        return None


class ProbabilityGapScannerControllerTest(IsolatedAsyncioTestCase):
    async def test_controller_handles_tradable_and_prefixed_daily_markets(self):
        class StubProbabilityGapScanner(ProbabilityGapScanner):
            async def _fetch_polymarket_markets(self):
                return [
                    {
                        "question": "Bitcoin Up or Down on April 16?",
                        "slug": "bitcoin-up-or-down-on-april-16-2026",
                        "endDate": "2026-04-16T16:00:00Z",
                        "clobTokenIds": '["up-token", "down-token"]',
                        "outcomes": '["Up", "Down"]',
                        "description": "This market resolves using Binance BTC/USDT prices.",
                        "resolutionSource": "https://www.binance.com/en/trade/BTC_USDT",
                        "bestBid": 0.87,
                        "bestAsk": 0.88,
                        "outcomePrices": '["0.875", "0.125"]',
                        "liquidityClob": 34921.95,
                        "conditionId": "today-market",
                    },
                    {
                        "question": "Bitcoin Up or Down on April 17?",
                        "slug": "bitcoin-up-or-down-on-april-17-2026",
                        "endDate": "2026-04-17T16:00:00Z",
                        "clobTokenIds": '["up-token", "down-token"]',
                        "outcomes": '["Up", "Down"]',
                        "description": "This market resolves using Binance BTC/USDT prices.",
                        "resolutionSource": "https://www.binance.com/en/trade/BTC_USDT",
                        "bestBid": 0.49,
                        "bestAsk": 0.50,
                        "outcomePrices": '["0.495", "0.505"]',
                        "liquidityClob": 11153.57,
                        "conditionId": "tomorrow-market",
                    },
                ]

            async def _fetch_binance_reference_close(self, reference_time: datetime):
                if reference_time == datetime(2026, 4, 15, 16, 0, tzinfo=UTC):
                    return Decimal("74754.2")
                return None

            async def _fetch_current_spot_price(self):
                return Decimal("74646.18")

            async def _fetch_option_market_data(self):
                return (
                    [
                        {"symbol": "BTC-260417-74500-C", "delta": "0.65646939"},
                        {"symbol": "BTC-260417-75000-C", "delta": "0.17569006"},
                        {"symbol": "BTC-260417-56000-C", "delta": "1.0"},
                    ],
                    {
                        "BTC-260417-74500-C": {
                            "symbol": "BTC-260417-74500-C",
                            "expiryDate": 1776412800000,
                            "underlying": "BTCUSDT",
                            "side": "CALL",
                            "strikePrice": "74500",
                        },
                        "BTC-260417-75000-C": {
                            "symbol": "BTC-260417-75000-C",
                            "expiryDate": 1776412800000,
                            "underlying": "BTCUSDT",
                            "side": "CALL",
                            "strikePrice": "75000",
                        },
                        "BTC-260417-56000-C": {
                            "symbol": "BTC-260417-56000-C",
                            "expiryDate": 1776412800000,
                            "underlying": "BTCUSDT",
                            "side": "CALL",
                            "strikePrice": "56000",
                        },
                    },
                )

        controller = StubProbabilityGapScanner(
            config=ProbabilityGapScannerConfig(id="controller-e2e"),
            market_data_provider=_StubMarketDataProvider(),
            actions_queue=None,
        )

        await controller.update_processed_data()

        self.assertEqual(
            [
                "bitcoin-up-or-down-on-april-16-2026",
                "bitcoin-up-or-down-on-april-17-2026",
            ],
            controller.processed_data["target_slugs"],
        )
        self.assertEqual(2, controller.processed_data["total_polymarket_markets"])
        self.assertEqual(1, len(controller.processed_data["opportunities"]))
        self.assertEqual(1, len(controller.processed_data["all_ranked_opportunities"]))
        self.assertEqual(0, len(controller.processed_data["observations"]))
        self.assertEqual(1, len(controller.processed_data["rejected_markets"]))
        self.assertEqual(
            "bitcoin-up-or-down-on-april-16-2026",
            controller.processed_data["opportunities"][0]["slug"],
        )
        self.assertEqual(
            "outside_overlap_window",
            controller.processed_data["rejected_markets"][0]["rejection_reason"],
        )
        self.assertEqual(
            "spot_option_blend",
            controller.processed_data["opportunities"][0]["binance_signal_kind"],
        )
        self.assertEqual(
            Decimal("0.87"),
            controller.processed_data["opportunities"][0]["polymarket_up_best_bid"],
        )
        self.assertEqual(
            Decimal("0.12"),
            controller.processed_data["opportunities"][0]["polymarket_down_best_bid"],
        )
        self.assertLess(
            controller.processed_data["opportunities"][0]["binance_signal_value"],
            Decimal("0.7"),
        )
        self.assertEqual(
            "tradable",
            controller.processed_data["opportunities"][0]["market_classification"],
        )
        self.assertEqual(
            "overlap_window_live",
            controller.processed_data["opportunities"][0]["classification_reason"],
        )
        self.assertEqual(
            "2026-04-17T08:00:00+00:00",
            controller.processed_data["opportunities"][0]["selected_option_expiry"],
        )
        self.assertEqual(
            Decimal("74500"),
            controller.processed_data["opportunities"][0]["lower_strike"],
        )
        self.assertEqual(
            Decimal("75000"),
            controller.processed_data["opportunities"][0]["upper_strike"],
        )
        self.assertTrue(controller.processed_data["opportunities"][0]["forced_exit_time"].startswith("2026-04-16T15:45:00"))

        custom_info = controller.get_custom_info()
        self.assertEqual(1, custom_info["n_opportunities"])
        self.assertEqual(0, custom_info["n_observations"])
        self.assertEqual(1, custom_info["n_rejections"])
        self.assertTrue(custom_info["top_forced_exit_time"].startswith("2026-04-16T15:45:00"))
        self.assertGreaterEqual(custom_info["n_snapshots"], 2)
        self.assertEqual(0, custom_info["n_replays"])

        status = controller.to_format_status()
        self.assertIn("Qualified opportunities: 1", status)
        self.assertIn("Observable but not tradable: 0", status)
        self.assertIn("Rejected markets: 1", status)
        self.assertTrue(any("overlap_window_live" in line for line in status))
        self.assertTrue(any("outside_overlap_window" in line for line in status))
        self.assertTrue(any("expiry" in line for line in status))
        self.assertTrue(any("exit_at" in line for line in status))

        await controller.stop()

    async def test_dynamic_refresh_interval_tightens_for_tradable_markets(self):
        market_data_provider = _MutableTimeMarketDataProvider(
            datetime(2026, 4, 16, 10, 0, tzinfo=UTC).timestamp()
        )

        class StubProbabilityGapScanner(ProbabilityGapScanner):
            async def _fetch_polymarket_markets(self):
                return [
                    {
                        "question": "Bitcoin Up or Down on April 16?",
                        "slug": "bitcoin-up-or-down-on-april-16-2026",
                        "endDate": "2026-04-16T16:00:00Z",
                        "clobTokenIds": '["up-token", "down-token"]',
                        "outcomes": '["Up", "Down"]',
                        "description": "This market resolves using Binance BTC/USDT prices.",
                        "resolutionSource": "https://www.binance.com/en/trade/BTC_USDT",
                        "bestBid": 0.55,
                        "bestAsk": 0.56,
                        "outcomePrices": '["0.555", "0.445"]',
                        "liquidityClob": 30000,
                        "conditionId": "today-market",
                    }
                ]

            async def _fetch_binance_reference_close(self, reference_time: datetime):
                return Decimal("74754.2")

            async def _fetch_current_spot_price(self):
                return Decimal("74646.18")

            async def _fetch_option_market_data(self):
                return (
                    [
                        {"symbol": "BTC-260417-74500-C", "delta": "0.65646939"},
                        {"symbol": "BTC-260417-75000-C", "delta": "0.17569006"},
                    ],
                    {
                        "BTC-260417-74500-C": {
                            "symbol": "BTC-260417-74500-C",
                            "expiryDate": 1776412800000,
                            "underlying": "BTCUSDT",
                            "side": "CALL",
                            "strikePrice": "74500",
                        },
                        "BTC-260417-75000-C": {
                            "symbol": "BTC-260417-75000-C",
                            "expiryDate": 1776412800000,
                            "underlying": "BTCUSDT",
                            "side": "CALL",
                            "strikePrice": "75000",
                        },
                    },
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            controller = StubProbabilityGapScanner(
                config=ProbabilityGapScannerConfig(
                    id="dynamic-refresh",
                    snapshot_db_path=str(Path(temp_dir) / "samples.sqlite"),
                ),
                market_data_provider=market_data_provider,
                actions_queue=None,
            )

            self.assertEqual(60, controller._current_refresh_interval(market_data_provider.time()))
            await controller.update_processed_data()
            self.assertEqual(10, controller._current_refresh_interval(market_data_provider.time()))
            market_data_provider.current_ts += 5
            self.assertEqual(10, controller._current_refresh_interval(market_data_provider.time()))

            await controller.stop()


class ProbabilityGapSamplingTest(TestCase):
    def test_snapshot_store_and_replay_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "probability_gap.sqlite"
            store = ProbabilityGapSnapshotStore(str(db_path))
            store.record_snapshots(
                [
                    {
                        "observed_at": "2026-04-20T12:00:00+00:00",
                        "market_slug": "bitcoin-up-or-down-on-april-20-2026",
                        "signal_window_id": "bitcoin-up-or-down-on-april-20-2026:UP:2026-04-20T15:45:00+00:00",
                        "market_classification": "tradable",
                        "classification_reason": "overlap_window_live",
                        "best_side": "UP",
                        "best_net_edge": Decimal("0.05"),
                        "net_edge_up": Decimal("0.05"),
                        "net_edge_down": Decimal("-0.08"),
                        "binance_signal_value": Decimal("0.41"),
                        "binance_signal_kind": "spot_option_blend",
                        "current_spot_price": Decimal("75550"),
                        "reference_price": Decimal("75768"),
                        "up_best_bid": Decimal("0.24"),
                        "up_best_ask": Decimal("0.25"),
                        "down_best_bid": Decimal("0.75"),
                        "down_best_ask": Decimal("0.76"),
                        "selected_option_expiry": "2026-04-21T08:00:00+00:00",
                        "forced_exit_time": "2026-04-20T15:45:00+00:00",
                        "snapshot_reason": "initial_capture",
                        "payload": {"slug": "bitcoin-up-or-down-on-april-20-2026"},
                    },
                    {
                        "observed_at": "2026-04-20T12:10:00+00:00",
                        "market_slug": "bitcoin-up-or-down-on-april-20-2026",
                        "signal_window_id": "bitcoin-up-or-down-on-april-20-2026:UP:2026-04-20T15:45:00+00:00",
                        "market_classification": "tradable",
                        "classification_reason": "overlap_window_live",
                        "best_side": "UP",
                        "best_net_edge": Decimal("0.02"),
                        "net_edge_up": Decimal("0.02"),
                        "net_edge_down": Decimal("-0.05"),
                        "binance_signal_value": Decimal("0.38"),
                        "binance_signal_kind": "spot_option_blend",
                        "current_spot_price": Decimal("75520"),
                        "reference_price": Decimal("75768"),
                        "up_best_bid": Decimal("0.29"),
                        "up_best_ask": Decimal("0.30"),
                        "down_best_bid": Decimal("0.70"),
                        "down_best_ask": Decimal("0.71"),
                        "selected_option_expiry": "2026-04-21T08:00:00+00:00",
                        "forced_exit_time": "2026-04-20T15:45:00+00:00",
                        "snapshot_reason": "tradable_interval",
                        "payload": {"slug": "bitcoin-up-or-down-on-april-20-2026"},
                    },
                    {
                        "observed_at": "2026-04-20T12:20:00+00:00",
                        "market_slug": "bitcoin-up-or-down-on-april-20-2026",
                        "signal_window_id": "bitcoin-up-or-down-on-april-20-2026:UP:2026-04-20T15:45:00+00:00",
                        "market_classification": "observable",
                        "classification_reason": "edge_decay",
                        "best_side": "UP",
                        "best_net_edge": Decimal("0.00"),
                        "net_edge_up": Decimal("0.00"),
                        "net_edge_down": Decimal("-0.03"),
                        "binance_signal_value": Decimal("0.36"),
                        "binance_signal_kind": "spot_option_blend",
                        "current_spot_price": Decimal("75490"),
                        "reference_price": Decimal("75768"),
                        "up_best_bid": Decimal("0.31"),
                        "up_best_ask": Decimal("0.32"),
                        "down_best_bid": Decimal("0.68"),
                        "down_best_ask": Decimal("0.69"),
                        "selected_option_expiry": "2026-04-21T08:00:00+00:00",
                        "forced_exit_time": "2026-04-20T15:45:00+00:00",
                        "snapshot_reason": "state_change",
                        "payload": {"slug": "bitcoin-up-or-down-on-april-20-2026"},
                    },
                ]
            )

            snapshots = store.list_snapshots("bitcoin-up-or-down-on-april-20-2026")
            self.assertEqual(3, len(snapshots))

            replays = replay_tradable_windows(snapshots, min_net_edge=Decimal("0.01"))
            self.assertEqual(1, len(replays))
            self.assertEqual(Decimal("0.06"), replays[0].realized_move)
            self.assertEqual("classification_change", replays[0].exit_reason)

            summary = summarize_replays(replays)
            self.assertEqual(1, summary["n_replays"])
            self.assertEqual(1.0, summary["positive_ratio"])


class _MutableTimeMarketDataProvider:
    ready = True

    def __init__(self, current_ts: float):
        self.current_ts = current_ts

    def time(self):
        return self.current_ts

    def initialize_candles_feed(self, candles_config):
        return None
