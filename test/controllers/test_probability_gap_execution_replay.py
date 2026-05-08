from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest import TestCase

from controllers.generic.probability_gap_execution_replay import (
    ExecutionReplayConfig,
    build_maker_adverse_selection_events,
    build_future_diagnostics,
    bucket_execution_trades,
    replay_maker_first,
    replay_taker_baseline,
    replay_taker_entry_hold,
    run_parameter_grid,
    run_execution_research,
    summarize_adverse_selection,
)


class ProbabilityGapExecutionReplayTest(TestCase):
    def test_future_diagnostics_choose_first_snapshot_at_or_after_horizon(self):
        start = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
        snapshots = [
            _snapshot(start, best_side="UP", fair_up="0.55", taker_edge_up="0.04", up_bid="0.50", up_ask="0.51"),
            _snapshot(start + timedelta(seconds=31), best_side="UP", fair_up="0.57", taker_edge_up="0.03", up_bid="0.52", up_ask="0.53"),
            _snapshot(start + timedelta(seconds=121), best_side="UP", fair_up="0.60", taker_edge_up="0.02", up_bid="0.58", up_ask="0.59"),
            _snapshot(start + timedelta(seconds=301), best_side="UP", fair_up="0.62", taker_edge_up="0.01", up_bid="0.61", up_ask="0.62"),
        ]

        diagnostics = build_future_diagnostics(snapshots)

        first = diagnostics[0]
        self.assertEqual(Decimal("0.03"), first.edge_after_30s)
        self.assertEqual(Decimal("0.02"), first.edge_after_2m)
        self.assertEqual(Decimal("0.01"), first.edge_after_5m)
        self.assertEqual(Decimal("0.05"), first.fair_change_after_2m)
        self.assertEqual(Decimal("0.58"), first.max_bid_reachable_next_5m)
        self.assertEqual(Decimal("0.53"), first.min_ask_reachable_next_5m)

    def test_future_diagnostics_use_complement_consistent_down_book(self):
        start = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
        snapshots = [
            _snapshot(start, best_side="DOWN", fair_up="0.25", taker_edge_down="0.04", up_bid="0.23", up_ask="0.24"),
            _snapshot(start + timedelta(seconds=30), best_side="DOWN", fair_up="0.24", taker_edge_down="0.03", up_bid="0.26", up_ask="0.27"),
            _snapshot(start + timedelta(seconds=120), best_side="DOWN", fair_up="0.23", taker_edge_down="0.02", up_bid="0.25", up_ask="0.26"),
        ]

        diagnostics = build_future_diagnostics(snapshots)

        first = diagnostics[0]
        self.assertEqual(Decimal("0.73"), first.best_bid_after_30s)
        self.assertEqual(Decimal("0.74"), first.best_ask_after_30s)
        self.assertEqual(Decimal("0.74"), first.max_bid_reachable_next_5m)
        self.assertEqual(Decimal("0.74"), first.min_ask_reachable_next_5m)

    def test_taker_hold_does_not_exit_on_edge_decay(self):
        start = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
        snapshots = [
            _snapshot(start, best_side="UP", taker_edge_up="0.04", up_bid="0.49", up_ask="0.50"),
            _snapshot(
                start + timedelta(minutes=1),
                classification="observable",
                reason="edge_decay",
                best_side="UP",
                taker_edge_up="0",
                up_bid="0.52",
                up_ask="0.53",
            ),
            _snapshot(
                start + timedelta(minutes=2),
                classification="observable",
                reason="edge_decay",
                best_side="UP",
                taker_edge_up="0",
                up_bid="0.56",
                up_ask="0.57",
            ),
        ]
        config = ExecutionReplayConfig(min_edge=Decimal("0.02"), take_profit=Decimal("0.05"))

        baseline = replay_taker_baseline(snapshots, config)
        hold = replay_taker_entry_hold(snapshots, config)

        self.assertEqual("classification_change", baseline[0].exit_reason)
        self.assertEqual("take_profit", hold[0].exit_reason)
        self.assertEqual(Decimal("0.06"), hold[0].realized_move)

    def test_maker_fill_assumptions_are_explicit_and_different(self):
        start = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
        snapshots = [
            _snapshot(start, best_side="DOWN", fair_up="0.20", maker_edge_down="0.06", up_bid="0.23", up_ask="0.24"),
            _snapshot(start + timedelta(seconds=30), best_side="DOWN", fair_up="0.20", maker_edge_down="0.06", up_bid="0.26", up_ask="0.24"),
            _snapshot(start + timedelta(seconds=60), best_side="DOWN", fair_up="0.20", maker_edge_down="0.06", up_bid="0.27", up_ask="0.22"),
            _snapshot(start + timedelta(seconds=120), best_side="DOWN", fair_up="0.20", maker_edge_down="0.06", up_bid="0.20", up_ask="0.21"),
        ]
        conservative = replay_maker_first(
            snapshots,
            ExecutionReplayConfig(
                min_edge=Decimal("0.02"),
                quote_buffer=Decimal("0.05"),
                fill_assumption="conservative",
                take_profit=Decimal("0.03"),
            ),
        )
        strict = replay_maker_first(
            snapshots,
            ExecutionReplayConfig(
                min_edge=Decimal("0.02"),
                quote_buffer=Decimal("0.05"),
                fill_assumption="strict",
                take_profit=Decimal("0.03"),
            ),
        )

        self.assertEqual(start + timedelta(seconds=30), conservative[0].entry_time)
        self.assertEqual(start + timedelta(seconds=60), strict[0].entry_time)
        self.assertEqual("conservative", conservative[0].fill_assumption)
        self.assertEqual("strict", strict[0].fill_assumption)

    def test_bucket_report_groups_execution_dimensions(self):
        start = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
        snapshots = [
            _snapshot(start, best_side="UP", taker_edge_up="0.04", up_bid="0.49", up_ask="0.50"),
            _snapshot(start + timedelta(minutes=2), best_side="UP", taker_edge_up="0.03", up_bid="0.56", up_ask="0.57"),
        ]
        config = ExecutionReplayConfig(min_edge=Decimal("0.02"), take_profit=Decimal("0.05"))

        report = run_execution_research(snapshots, config)
        bucket_report = bucket_execution_trades(replay_taker_entry_hold(snapshots, config))

        self.assertEqual("iv_digital_v1", report["model_version"])
        self.assertEqual(2, report["snapshot_count"])
        self.assertEqual("taker_hold", bucket_report[0]["mode"])
        self.assertEqual("UP", bucket_report[0]["side"])
        self.assertEqual("3-5c", bucket_report[0]["edge_bucket"])

    def test_maker_adverse_selection_flags_bad_post_fill_path(self):
        start = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
        snapshots = [
            _snapshot(start, best_side="DOWN", fair_up="0.20", maker_edge_down="0.06", up_bid="0.23", up_ask="0.24"),
            _snapshot(start + timedelta(seconds=6), best_side="DOWN", fair_up="0.30", maker_edge_down="-0.01", up_bid="0.26", up_ask="0.24"),
            _snapshot(start + timedelta(seconds=10), best_side="DOWN", fair_up="0.32", maker_edge_down="-0.02", up_bid="0.31", up_ask="0.32"),
            _snapshot(start + timedelta(seconds=31), best_side="DOWN", fair_up="0.35", maker_edge_down="-0.02", up_bid="0.30", up_ask="0.31"),
        ]
        config = ExecutionReplayConfig(
            min_edge=Decimal("0.02"),
            quote_buffer=Decimal("0.05"),
            fill_assumption="conservative",
            stop_loss=Decimal("0.02"),
        )

        events = build_maker_adverse_selection_events(snapshots, config)
        report = summarize_adverse_selection(events)

        self.assertTrue(events[0].adverse_fair_move)
        self.assertTrue(events[0].edge_disappeared)
        self.assertTrue(events[0].bid_below_entry)
        self.assertTrue(events[0].stop_loss_touched)
        five_second_bucket = next(row for row in report if row["horizon_seconds"] == 5)
        self.assertEqual(1.0, five_second_bucket["adverse_fair_ratio"])

    def test_parameter_grid_reports_stability_dimensions(self):
        start = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
        snapshots = [
            _snapshot(start, best_side="DOWN", fair_up="0.20", maker_edge_down="0.06", up_bid="0.23", up_ask="0.24"),
            _snapshot(start + timedelta(seconds=30), best_side="DOWN", fair_up="0.20", maker_edge_down="0.06", up_bid="0.26", up_ask="0.24"),
            _snapshot(start + timedelta(seconds=60), best_side="DOWN", fair_up="0.19", maker_edge_down="0.07", up_bid="0.20", up_ask="0.21"),
        ]

        grid = run_parameter_grid(
            snapshots,
            ExecutionReplayConfig(min_edge=Decimal("0.02"), fill_assumption="conservative"),
            buffers=(Decimal("0.03"), Decimal("0.05")),
            take_profits=(Decimal("0.01"),),
            stop_losses=(Decimal("0.02"),),
            cooldown_seconds_values=(0, 300),
            gamma_sets=(("low",),),
            min_time_to_expiry_minutes_values=(Decimal("30"),),
        )

        self.assertEqual(4, grid["row_count"])
        self.assertIn("stable_regions", grid)
        self.assertEqual({"0.03", "0.05"}, {row["buffer"] for row in grid["top_rows"] + grid["bottom_rows"]})


def _snapshot(
    observed_at,
    classification="tradable",
    reason="iv_digital_live",
    best_side="UP",
    model_version="iv_digital_v1",
    fair_up="0.55",
    taker_edge_up="0.04",
    taker_edge_down="-0.04",
    maker_edge_up="0.05",
    maker_edge_down="0.05",
    up_bid="0.50",
    up_ask="0.51",
    spot="100",
    reference="101",
):
    fair_up_decimal = Decimal(fair_up)
    up_bid_decimal = Decimal(up_bid)
    up_ask_decimal = Decimal(up_ask)
    return {
        "observed_at": observed_at,
        "market_slug": "bitcoin-up-or-down-on-may-5-2026",
        "signal_window_id": f"slug:{best_side}:2026-05-05T16:00:00+00:00",
        "market_classification": classification,
        "classification_reason": reason,
        "best_side": best_side,
        "best_net_edge": Decimal(taker_edge_up if best_side == "UP" else taker_edge_down),
        "net_edge_up": Decimal(taker_edge_up),
        "net_edge_down": Decimal(taker_edge_down),
        "taker_edge_up": Decimal(taker_edge_up),
        "taker_edge_down": Decimal(taker_edge_down),
        "maker_edge_up": Decimal(maker_edge_up),
        "maker_edge_down": Decimal(maker_edge_down),
        "binance_signal_value": fair_up_decimal,
        "binance_signal_kind": "iv_digital",
        "model_version": model_version,
        "fair_value_up": fair_up_decimal,
        "fair_value_down": Decimal("1") - fair_up_decimal,
        "gamma_risk": "low",
        "model_confidence": "medium",
        "current_spot_price": Decimal(spot),
        "reference_price": Decimal(reference),
        "up_best_bid": up_bid_decimal,
        "up_best_ask": up_ask_decimal,
        "down_best_bid": Decimal("1") - up_ask_decimal,
        "down_best_ask": Decimal("1") - up_bid_decimal,
        "selected_option_expiry": datetime(2026, 5, 5, 16, 0, tzinfo=UTC),
        "forced_exit_time": datetime(2026, 5, 5, 15, 45, tzinfo=UTC),
        "payload": {},
    }
