import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest import TestCase

from controllers.generic.probability_gap_sampling import (
    ProbabilityGapSnapshotStore,
    choose_snapshot_reason,
    replay_tradable_windows,
    summarize_replays,
)
from controllers.generic.probability_gap_scanner_utils import (
    PolymarketDailyMarket,
    calculate_digital_probability,
    calculate_probability_gap,
    overlap_reason_blocks_sampling,
)


class ProbabilityGapSamplingTest(TestCase):
    def test_iv_digital_probability_uses_d2_not_call_delta_proxy(self):
        p_up, d2, prob_delta = calculate_digital_probability(
            current_spot_price=Decimal("100"),
            reference_price=Decimal("100"),
            sigma=Decimal("0.80"),
            tau_years=Decimal("0.25"),
        )

        self.assertIsNotNone(p_up)
        self.assertIsNotNone(d2)
        self.assertIsNotNone(prob_delta)
        self.assertLess(p_up, Decimal("0.5"))

    def test_probability_gap_calculates_fee_aware_taker_edges(self):
        market = PolymarketDailyMarket(
            condition_id="condition",
            slug="bitcoin-up-or-down-on-may-3-2026",
            question="Bitcoin Up or Down on May 3?",
            market_date=datetime(2026, 5, 3, tzinfo=UTC).date(),
            end_time=datetime(2026, 5, 3, 16, 0, tzinfo=UTC),
            reference_time=datetime(2026, 5, 2, 16, 0, tzinfo=UTC),
            up_token_id="up",
            down_token_id="down",
            description="Resolves from Binance BTCUSDT",
            resolution_source="Binance BTCUSDT",
            up_best_bid=Decimal("0.26"),
            up_best_ask=Decimal("0.27"),
            up_mid=Decimal("0.265"),
            down_mid=Decimal("0.735"),
            liquidity_clob=Decimal("1000"),
        )

        gap = calculate_probability_gap(
            market=market,
            binance_signal=Decimal("0.25"),
            estimated_cost_buffer=Decimal("0.005"),
            polymarket_taker_fee_rate=Decimal("0.072"),
        )

        expected_down_fee = Decimal("0.072") * Decimal("0.74") * Decimal("0.26")
        self.assertEqual(expected_down_fee, gap.taker_fee_down)
        self.assertEqual(Decimal("0.75") - Decimal("0.74") - expected_down_fee - Decimal("0.005"), gap.taker_edge_down)
        self.assertEqual(gap.taker_edge_down, gap.net_edge_down)
        self.assertGreater(gap.maker_edge_down, gap.taker_edge_down)

    def test_choose_snapshot_reason_respects_tiered_policy(self):
        now = datetime(2026, 4, 20, 12, 0, tzinfo=UTC)
        current = {
            "observed_at": now.isoformat(),
            "market_classification": "tradable",
            "classification_reason": "overlap_window_live",
            "best_side": "UP",
            "best_net_edge": Decimal("0.05"),
            "forced_exit_time": "2026-04-20T12:20:00+00:00",
        }
        self.assertEqual(
            "initial_capture",
            choose_snapshot_reason(
                current_snapshot=current,
                previous_snapshot=None,
                now=now,
                baseline_interval_seconds=60,
                tradable_interval_seconds=10,
                near_exit_interval_seconds=3,
                near_exit_window_minutes=30,
                min_net_edge=Decimal("0.01"),
            ),
        )

        previous = {
            **current,
            "observed_at": "2026-04-20T11:59:58+00:00",
        }
        self.assertIsNone(
            choose_snapshot_reason(
                current_snapshot=current,
                previous_snapshot=previous,
                now=now,
                baseline_interval_seconds=60,
                tradable_interval_seconds=10,
                near_exit_interval_seconds=3,
                near_exit_window_minutes=30,
                min_net_edge=Decimal("0.01"),
            )
        )
        previous["observed_at"] = "2026-04-20T11:59:56+00:00"
        self.assertEqual(
            "near_exit_interval",
            choose_snapshot_reason(
                current_snapshot=current,
                previous_snapshot=previous,
                now=now,
                baseline_interval_seconds=60,
                tradable_interval_seconds=10,
                near_exit_interval_seconds=3,
                near_exit_window_minutes=30,
                min_net_edge=Decimal("0.01"),
            ),
        )

    def test_choose_snapshot_reason_does_not_repeat_rejected_lifecycle_rows(self):
        now = datetime(2026, 4, 22, 4, 0, tzinfo=UTC)
        current = {
            "observed_at": now.isoformat(),
            "market_classification": "rejected",
            "classification_reason": "outside_overlap_window",
            "best_side": "",
            "best_net_edge": Decimal("0"),
            "forced_exit_time": "",
        }
        previous = {
            **current,
            "observed_at": "2026-04-22T03:58:00+00:00",
        }
        self.assertIsNone(
            choose_snapshot_reason(
                current_snapshot=current,
                previous_snapshot=previous,
                now=now,
                baseline_interval_seconds=60,
                tradable_interval_seconds=10,
                near_exit_interval_seconds=3,
                near_exit_window_minutes=30,
                min_net_edge=Decimal("0.01"),
            )
        )

        transitioned = {
            **current,
            "classification_reason": "reference_price_not_fixed",
        }
        self.assertEqual(
            "state_change",
            choose_snapshot_reason(
                current_snapshot=transitioned,
                previous_snapshot=previous,
                now=now,
                baseline_interval_seconds=60,
                tradable_interval_seconds=10,
                near_exit_interval_seconds=3,
                near_exit_window_minutes=30,
                min_net_edge=Decimal("0.01"),
            ),
        )

    def test_outside_overlap_window_does_not_block_sampling(self):
        self.assertFalse(overlap_reason_blocks_sampling(None))
        self.assertFalse(overlap_reason_blocks_sampling("outside_overlap_window"))
        self.assertTrue(overlap_reason_blocks_sampling("inside_exit_buffer"))
        self.assertTrue(overlap_reason_blocks_sampling("market_already_settled"))

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

    def test_snapshot_store_persists_iv_digital_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "probability_gap.sqlite"
            store = ProbabilityGapSnapshotStore(str(db_path))
            store.record_snapshots(
                [
                    {
                        "observed_at": "2026-05-03T12:00:00+00:00",
                        "market_slug": "bitcoin-up-or-down-on-may-3-2026",
                        "signal_window_id": "slug:DOWN:2026-05-03T15:45:00+00:00",
                        "market_classification": "tradable",
                        "classification_reason": "iv_digital_live",
                        "best_side": "DOWN",
                        "best_net_edge": Decimal("0.02"),
                        "net_edge_up": Decimal("-0.05"),
                        "net_edge_down": Decimal("0.02"),
                        "binance_signal_value": Decimal("0.25"),
                        "binance_signal_kind": "iv_digital",
                        "model_version": "iv_digital_v1",
                        "fair_value_up": Decimal("0.25"),
                        "fair_value_down": Decimal("0.75"),
                        "option_iv": Decimal("0.62"),
                        "tau_years": Decimal("0.001"),
                        "d2": Decimal("-0.674"),
                        "prob_delta": Decimal("0.0001"),
                        "gamma_risk": "medium",
                        "model_confidence": "high",
                        "polymarket_taker_fee_rate": Decimal("0.072"),
                        "polymarket_taker_fee_up": Decimal("0.014"),
                        "polymarket_taker_fee_down": Decimal("0.014"),
                        "maker_edge_up": Decimal("-0.04"),
                        "maker_edge_down": Decimal("0.03"),
                        "taker_edge_up": Decimal("-0.05"),
                        "taker_edge_down": Decimal("0.02"),
                        "current_spot_price": Decimal("78000"),
                        "reference_price": Decimal("78400"),
                        "forward_source": "perp_mark",
                        "estimated_forward_price": Decimal("78012"),
                        "basis_annualized": Decimal("0.25"),
                        "perp_mark_price": Decimal("78012"),
                        "perp_index_price": Decimal("78000"),
                        "perp_last_funding_rate": Decimal("0.0001"),
                        "perp_next_funding_time": "2026-05-03T16:00:00+00:00",
                        "delivery_symbol": "",
                        "delivery_price": "",
                        "forward_basis_reason": "perp_mark_basis_fallback",
                        "option_chain_slice": [
                            {
                                "symbol": "BTC-260503-78000-C",
                                "strike": Decimal("78000"),
                                "side": "CALL",
                                "mark_price": Decimal("100"),
                            }
                        ],
                        "option_chain_slice_count": 1,
                        "option_chain_slice_source": "binance_eapi_mark_ticker",
                        "option_chain_slice_expiry": "2026-05-03T16:00:00+00:00",
                        "option_chain_horizon_mismatch_minutes": Decimal("0"),
                        "smile_call_spread_probability": Decimal("0.48"),
                        "smile_call_spread_status": "ok",
                        "smile_call_spread_reason": "finite_difference_call_spread",
                        "up_best_bid": Decimal("0.26"),
                        "up_best_ask": Decimal("0.27"),
                        "down_best_bid": Decimal("0.73"),
                        "down_best_ask": Decimal("0.74"),
                        "selected_option_expiry": "2026-05-03T16:00:00+00:00",
                        "forced_exit_time": "2026-05-03T15:45:00+00:00",
                        "snapshot_reason": "initial_capture",
                        "payload": {"model_version": "iv_digital_v1"},
                    },
                ]
            )

            snapshots = store.list_snapshots("bitcoin-up-or-down-on-may-3-2026")
            self.assertEqual("iv_digital_v1", snapshots[0]["model_version"])
            self.assertEqual(Decimal("0.62"), snapshots[0]["option_iv"])
            self.assertEqual(Decimal("0.02"), snapshots[0]["taker_edge_down"])
            self.assertEqual("perp_mark", snapshots[0]["forward_source"])
            self.assertEqual(Decimal("78012"), snapshots[0]["estimated_forward_price"])
            self.assertEqual(datetime(2026, 5, 3, 16, 0, tzinfo=UTC), snapshots[0]["perp_next_funding_time"])
            self.assertEqual(1, snapshots[0]["option_chain_slice_count"])
            self.assertEqual("BTC-260503-78000-C", snapshots[0]["option_chain_slice"][0]["symbol"])
            self.assertEqual(Decimal("0.48"), snapshots[0]["smile_call_spread_probability"])

    def test_replay_entry_respects_min_net_edge(self):
        snapshots = [
            {
                "observed_at": datetime(2026, 4, 21, 7, 0, tzinfo=UTC),
                "market_slug": "bitcoin-up-or-down-on-april-21-2026",
                "signal_window_id": "slug:UP:2026-04-21T08:00:00+00:00",
                "market_classification": "tradable",
                "classification_reason": "overlap_window_live",
                "best_side": "UP",
                "best_net_edge": Decimal("0.005"),
                "net_edge_up": Decimal("0.005"),
                "net_edge_down": Decimal("-0.04"),
                "binance_signal_value": Decimal("0.52"),
                "binance_signal_kind": "spot_option_blend",
                "current_spot_price": Decimal("75000"),
                "reference_price": Decimal("74900"),
                "up_best_bid": Decimal("0.49"),
                "up_best_ask": Decimal("0.50"),
                "down_best_bid": Decimal("0.50"),
                "down_best_ask": Decimal("0.51"),
                "selected_option_expiry": datetime(2026, 4, 21, 8, 0, tzinfo=UTC),
                "forced_exit_time": datetime(2026, 4, 21, 8, 0, tzinfo=UTC),
                "payload": {},
            },
            {
                "observed_at": datetime(2026, 4, 21, 7, 1, tzinfo=UTC),
                "market_slug": "bitcoin-up-or-down-on-april-21-2026",
                "signal_window_id": "slug:UP:2026-04-21T08:00:00+00:00",
                "market_classification": "observable",
                "classification_reason": "edge_decay",
                "best_side": "UP",
                "best_net_edge": Decimal("0"),
                "net_edge_up": Decimal("0"),
                "net_edge_down": Decimal("-0.03"),
                "binance_signal_value": Decimal("0.51"),
                "binance_signal_kind": "spot_option_blend",
                "current_spot_price": Decimal("75010"),
                "reference_price": Decimal("74900"),
                "up_best_bid": Decimal("0.51"),
                "up_best_ask": Decimal("0.52"),
                "down_best_bid": Decimal("0.48"),
                "down_best_ask": Decimal("0.49"),
                "selected_option_expiry": datetime(2026, 4, 21, 8, 0, tzinfo=UTC),
                "forced_exit_time": datetime(2026, 4, 21, 8, 0, tzinfo=UTC),
                "payload": {},
            },
            {
                "observed_at": datetime(2026, 4, 21, 7, 2, tzinfo=UTC),
                "market_slug": "bitcoin-up-or-down-on-april-21-2026",
                "signal_window_id": "slug:DOWN:2026-04-21T08:00:00+00:00",
                "market_classification": "tradable",
                "classification_reason": "overlap_window_live",
                "best_side": "DOWN",
                "best_net_edge": Decimal("-0.02"),
                "net_edge_up": Decimal("-0.04"),
                "net_edge_down": Decimal("-0.02"),
                "binance_signal_value": Decimal("0.48"),
                "binance_signal_kind": "spot_option_blend",
                "current_spot_price": Decimal("74980"),
                "reference_price": Decimal("74900"),
                "up_best_bid": Decimal("0.67"),
                "up_best_ask": Decimal("0.68"),
                "down_best_bid": Decimal("0.32"),
                "down_best_ask": Decimal("0.33"),
                "selected_option_expiry": datetime(2026, 4, 21, 8, 0, tzinfo=UTC),
                "forced_exit_time": datetime(2026, 4, 21, 8, 0, tzinfo=UTC),
                "payload": {},
            },
            {
                "observed_at": datetime(2026, 4, 21, 7, 3, tzinfo=UTC),
                "market_slug": "bitcoin-up-or-down-on-april-21-2026",
                "signal_window_id": "slug:UP:2026-04-21T08:00:00+00:00",
                "market_classification": "tradable",
                "classification_reason": "overlap_window_live",
                "best_side": "UP",
                "best_net_edge": Decimal("0.05"),
                "net_edge_up": Decimal("0.05"),
                "net_edge_down": Decimal("-0.08"),
                "binance_signal_value": Decimal("0.56"),
                "binance_signal_kind": "spot_option_blend",
                "current_spot_price": Decimal("75020"),
                "reference_price": Decimal("74900"),
                "up_best_bid": Decimal("0.54"),
                "up_best_ask": Decimal("0.55"),
                "down_best_bid": Decimal("0.45"),
                "down_best_ask": Decimal("0.46"),
                "selected_option_expiry": datetime(2026, 4, 21, 8, 0, tzinfo=UTC),
                "forced_exit_time": datetime(2026, 4, 21, 8, 0, tzinfo=UTC),
                "payload": {},
            },
            {
                "observed_at": datetime(2026, 4, 21, 7, 4, tzinfo=UTC),
                "market_slug": "bitcoin-up-or-down-on-april-21-2026",
                "signal_window_id": "slug:UP:2026-04-21T08:00:00+00:00",
                "market_classification": "observable",
                "classification_reason": "edge_decay",
                "best_side": "UP",
                "best_net_edge": Decimal("0"),
                "net_edge_up": Decimal("0"),
                "net_edge_down": Decimal("-0.03"),
                "binance_signal_value": Decimal("0.53"),
                "binance_signal_kind": "spot_option_blend",
                "current_spot_price": Decimal("75030"),
                "reference_price": Decimal("74900"),
                "up_best_bid": Decimal("0.58"),
                "up_best_ask": Decimal("0.59"),
                "down_best_bid": Decimal("0.41"),
                "down_best_ask": Decimal("0.42"),
                "selected_option_expiry": datetime(2026, 4, 21, 8, 0, tzinfo=UTC),
                "forced_exit_time": datetime(2026, 4, 21, 8, 0, tzinfo=UTC),
                "payload": {},
            },
        ]

        replays = replay_tradable_windows(snapshots, min_net_edge=Decimal("0.01"))
        self.assertEqual(1, len(replays))
        self.assertEqual(Decimal("0.05"), replays[0].entry_net_edge)
        self.assertEqual("UP", replays[0].side)
        self.assertEqual(Decimal("0.03"), replays[0].realized_move)

    def test_replay_uses_complement_consistent_down_book(self):
        snapshots = [
            {
                "observed_at": datetime(2026, 4, 22, 7, 33, tzinfo=UTC),
                "market_slug": "bitcoin-up-or-down-on-april-22-2026",
                "signal_window_id": "slug:DOWN:2026-04-22T08:00:00+00:00",
                "market_classification": "tradable",
                "classification_reason": "overlap_window_live",
                "best_side": "DOWN",
                "best_net_edge": Decimal("0.0124"),
                "net_edge_up": Decimal("-0.0424"),
                "net_edge_down": Decimal("0.0124"),
                "binance_signal_value": Decimal("0.0476"),
                "binance_signal_kind": "spot_option_blend",
                "current_spot_price": Decimal("93500"),
                "reference_price": Decimal("94000"),
                "up_best_bid": Decimal("0.94"),
                "up_best_ask": Decimal("0.95"),
                "down_best_bid": Decimal("0.94"),
                "down_best_ask": Decimal("0.06"),
                "selected_option_expiry": datetime(2026, 4, 22, 8, 0, tzinfo=UTC),
                "forced_exit_time": datetime(2026, 4, 22, 8, 0, tzinfo=UTC),
                "payload": {},
            },
            {
                "observed_at": datetime(2026, 4, 22, 8, 0, tzinfo=UTC),
                "market_slug": "bitcoin-up-or-down-on-april-22-2026",
                "signal_window_id": "slug:DOWN:2026-04-22T08:00:00+00:00",
                "market_classification": "observable",
                "classification_reason": "side_flip",
                "best_side": "UP",
                "best_net_edge": Decimal("0"),
                "net_edge_up": Decimal("0.01"),
                "net_edge_down": Decimal("-0.01"),
                "binance_signal_value": Decimal("0.51"),
                "binance_signal_kind": "spot_option_blend",
                "current_spot_price": Decimal("93600"),
                "reference_price": Decimal("94000"),
                "up_best_bid": Decimal("0.94"),
                "up_best_ask": Decimal("0.95"),
                "down_best_bid": Decimal("0.94"),
                "down_best_ask": Decimal("0.06"),
                "selected_option_expiry": datetime(2026, 4, 22, 8, 0, tzinfo=UTC),
                "forced_exit_time": datetime(2026, 4, 22, 8, 0, tzinfo=UTC),
                "payload": {},
            },
        ]

        replays = replay_tradable_windows(snapshots, min_net_edge=Decimal("0.01"))
        self.assertEqual(1, len(replays))
        self.assertEqual("DOWN", replays[0].side)
        self.assertEqual(Decimal("0.06"), replays[0].entry_price)
        self.assertEqual(Decimal("0.05"), replays[0].exit_price)
        self.assertEqual(Decimal("-0.01"), replays[0].realized_move)
