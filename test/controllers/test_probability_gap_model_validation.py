import json
import tempfile
import urllib.error
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch

from controllers.generic.probability_gap_model_validation import (
    build_model_validation_entries,
    build_settlement_labels,
    calibration_report,
    fetch_binance_1m_close,
    fetch_binance_rule_settlements,
    extract_binance_rule_settlement,
    extract_official_settlement,
    infer_proxy_settlement,
    run_model_validation,
    settlement_coverage,
    truth_table,
)


class ProbabilityGapModelValidationTest(TestCase):
    def test_extract_official_settlement_prefers_explicit_outcome(self):
        label = extract_official_settlement(
            "slug",
            {
                "resolvedOutcome": "Down",
                "closed": True,
                "outcomes": '["Up", "Down"]',
                "outcomePrices": '["1", "0"]',
                "resolvedAt": "2026-05-05T16:00:00Z",
            },
        )

        self.assertEqual("DOWN", label.outcome)
        self.assertEqual("official_gamma_resolvedOutcome", label.source)
        self.assertEqual("high", label.confidence)

    def test_extract_official_settlement_can_use_closed_binary_prices(self):
        label = extract_official_settlement(
            "slug",
            {
                "closed": True,
                "outcomes": '["Up", "Down"]',
                "outcomePrices": '["0", "1"]',
            },
        )

        self.assertEqual("DOWN", label.outcome)
        self.assertEqual("official_gamma_prices", label.source)

    def test_proxy_settlement_uses_snapshot_near_forced_exit(self):
        forced = datetime(2026, 5, 5, 16, 0, tzinfo=UTC)
        snapshots = [
            _snapshot(
                forced - timedelta(seconds=20),
                forced_exit_time=forced - timedelta(minutes=15),
                market_end_time=forced,
                spot="101",
                reference="100",
            ),
        ]

        label = infer_proxy_settlement("slug", snapshots, proxy_window_seconds=60)

        self.assertEqual("UP", label.outcome)
        self.assertEqual("proxy_near_market_end", label.source)
        self.assertEqual("medium", label.confidence)

    def test_official_label_takes_precedence_over_proxy(self):
        forced = datetime(2026, 5, 5, 16, 0, tzinfo=UTC)
        snapshots = [
            _snapshot(
                forced - timedelta(seconds=20),
                forced_exit_time=forced - timedelta(minutes=15),
                market_end_time=forced,
                spot="101",
                reference="100",
            ),
        ]

        labels = build_settlement_labels(
            snapshots,
            official_markets_by_slug={
                "bitcoin-up-or-down-on-may-5-2026": {
                    "resolvedOutcome": "DOWN",
                }
            },
        )

        label = labels["bitcoin-up-or-down-on-may-5-2026"]
        self.assertEqual("DOWN", label.outcome)
        self.assertTrue(label.source.startswith("official"))

    def test_binance_rule_settlement_uses_one_minute_close(self):
        label = extract_binance_rule_settlement(
            "slug",
            {
                "outcome": "UP",
                "reference_price": "100",
                "settlement_close": "100.01",
                "settlement_time": "2026-05-05T16:00:00Z",
            },
        )

        self.assertEqual("UP", label.outcome)
        self.assertEqual("binance_rule_1m_close", label.source)
        self.assertEqual("high", label.confidence)
        self.assertIn("tie_rule=DOWN_ON_TIE", label.reason)

    def test_binance_rule_label_takes_precedence_over_proxy(self):
        forced = datetime(2026, 5, 5, 15, 45, tzinfo=UTC)
        snapshots = [
            _snapshot(
                forced - timedelta(seconds=20),
                forced_exit_time=forced,
                spot="101",
                reference="100",
                market_end_time=forced + timedelta(minutes=15),
            ),
        ]

        labels = build_settlement_labels(
            snapshots,
            binance_settlements_by_slug={
                "bitcoin-up-or-down-on-may-5-2026": {
                    "outcome": "DOWN",
                    "reference_price": "100",
                    "settlement_close": "99.99",
                    "settlement_time": "2026-05-05T16:00:00Z",
                }
            },
        )

        label = labels["bitcoin-up-or-down-on-may-5-2026"]
        self.assertEqual("DOWN", label.outcome)
        self.assertEqual("binance_rule_1m_close", label.source)

    def test_binance_1m_close_retries_after_transient_failure(self):
        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return b'[["1777996800000","100","101","99","100.25"]]'

        with patch(
            "controllers.generic.probability_gap_model_validation.urllib.request.urlopen",
            side_effect=[urllib.error.URLError("connection reset"), _Response()],
        ):
            close = fetch_binance_1m_close(
                datetime(2026, 5, 5, 16, 0, tzinfo=UTC),
                retry_count=2,
                backoff_seconds=0,
            )

        self.assertEqual(Decimal("100.25"), close)

    def test_binance_rule_settlements_use_cache_when_network_fails(self):
        market_end = datetime(2026, 5, 5, 16, 0, tzinfo=UTC)
        snapshot = _snapshot(
            market_end - timedelta(hours=1),
            reference="100",
            forced_exit_time=market_end - timedelta(minutes=15),
            market_end_time=market_end,
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_path = f"{tmp_dir}/settlements.json"
            with open(cache_path, "w") as stream:
                json.dump(
                    {
                        "settlements": {
                            "bitcoin-up-or-down-on-may-5-2026": {
                                "outcome": "UP",
                                "reference_price": "100",
                                "settlement_close": "101",
                                "settlement_time": market_end.isoformat(),
                            }
                        }
                    },
                    stream,
                )

            with patch(
                "controllers.generic.probability_gap_model_validation.urllib.request.urlopen",
                side_effect=urllib.error.URLError("connection reset"),
            ):
                settlements = fetch_binance_rule_settlements(
                    [snapshot],
                    cache_path=cache_path,
                    now=market_end + timedelta(minutes=1),
                    retry_count=1,
                    backoff_seconds=0,
                )

        self.assertEqual("UP", settlements["bitcoin-up-or-down-on-may-5-2026"]["outcome"])
        labels = build_settlement_labels([snapshot], binance_settlements_by_slug=settlements)
        self.assertEqual("binance_rule_1m_close", labels["bitcoin-up-or-down-on-may-5-2026"].source)

    def test_binance_rule_fetch_failure_is_not_silent_unavailable(self):
        market_end = datetime(2026, 5, 5, 16, 0, tzinfo=UTC)
        snapshot = _snapshot(
            market_end - timedelta(hours=1),
            reference="100",
            forced_exit_time=market_end - timedelta(minutes=15),
            market_end_time=market_end,
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch(
                "controllers.generic.probability_gap_model_validation.urllib.request.urlopen",
                side_effect=urllib.error.URLError("connection reset"),
            ):
                settlements = fetch_binance_rule_settlements(
                    [snapshot],
                    cache_path=f"{tmp_dir}/settlements.json",
                    now=market_end + timedelta(minutes=1),
                    retry_count=1,
                    backoff_seconds=0,
                )

        labels = build_settlement_labels([snapshot], binance_settlements_by_slug=settlements)
        label = labels["bitcoin-up-or-down-on-may-5-2026"]
        self.assertEqual("binance_rule_fetch_failed", label.source)
        self.assertIn("connection reset", label.reason)

    def test_model_validation_entries_compute_side_specific_settlement_pnl(self):
        snapshot = _snapshot(
            datetime(2026, 5, 5, 12, 0, tzinfo=UTC),
            best_side="DOWN",
            fair_up="0.20",
            up_bid="0.23",
            up_ask="0.24",
        )
        labels = build_settlement_labels(
            [snapshot],
            official_markets_by_slug={
                "bitcoin-up-or-down-on-may-5-2026": {"resolvedOutcome": "DOWN"}
            },
        )

        entries = build_model_validation_entries([snapshot], labels)

        self.assertEqual(1, len(entries))
        self.assertEqual(Decimal("0.77"), entries[0]["entry_ask"])
        self.assertEqual(Decimal("0.23"), entries[0]["settlement_pnl"])
        self.assertEqual(Decimal("0.03"), entries[0]["a_edge"])
        self.assertEqual(Decimal("0.035"), entries[0]["a_residual"])

    def test_calibration_and_truth_table_do_not_merge_sources(self):
        snapshots = [
            _snapshot(datetime(2026, 5, 5, 12, 0, tzinfo=UTC), fair_up="0.80", up_bid="0.76", up_ask="0.77"),
            _snapshot(
                datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
                market_slug="bitcoin-up-or-down-on-may-6-2026",
                fair_up="0.20",
                best_side="DOWN",
                up_bid="0.23",
                up_ask="0.24",
            ),
        ]
        labels = build_settlement_labels(
            snapshots,
            official_markets_by_slug={
                "bitcoin-up-or-down-on-may-5-2026": {"resolvedOutcome": "UP"},
                "bitcoin-up-or-down-on-may-6-2026": {"resolvedOutcome": "DOWN"},
            },
        )

        entries = build_model_validation_entries(snapshots, labels)
        calibration = calibration_report(entries)
        table = truth_table(entries, "a_edge")

        self.assertEqual(2, calibration["n"])
        self.assertLess(calibration["brier"], 0.05)
        self.assertEqual(2, sum(row["n"] for row in table))

    def test_run_model_validation_separates_official_binance_proxy_unavailable(self):
        forced = datetime(2026, 5, 5, 16, 0, tzinfo=UTC)
        snapshots = [
            _snapshot(forced - timedelta(seconds=20), forced_exit_time=forced),
            _snapshot(
                forced - timedelta(seconds=20),
                market_slug="bitcoin-up-or-down-on-may-6-2026",
                forced_exit_time=forced,
            ),
            _snapshot(
                forced - timedelta(seconds=20),
                market_slug="bitcoin-up-or-down-on-may-7-2026",
                forced_exit_time=forced - timedelta(minutes=15),
                market_end_time=forced,
            ),
            _snapshot(
                forced - timedelta(hours=2),
                market_slug="bitcoin-up-or-down-on-may-8-2026",
                forced_exit_time=forced,
            ),
        ]

        report = run_model_validation(
            snapshots,
            official_markets_by_slug={
                "bitcoin-up-or-down-on-may-5-2026": {"resolvedOutcome": "UP"},
            },
            binance_settlements_by_slug={
                "bitcoin-up-or-down-on-may-6-2026": {
                    "outcome": "DOWN",
                    "reference_price": "100",
                    "settlement_close": "99",
                    "settlement_time": "2026-05-06T16:00:00Z",
                }
            },
        )

        coverage = report["settlement_coverage"]
        self.assertEqual(1, coverage["official_markets"])
        self.assertEqual(1, coverage["binance_rule_markets"])
        self.assertEqual(1, coverage["proxy_markets"])
        self.assertEqual(1, coverage["unavailable_markets"])
        self.assertIn("official_gamma_resolvedOutcome", report["by_source"])
        self.assertIn("binance_rule_1m_close", report["by_source"])
        self.assertIn("proxy_near_market_end", report["by_source"])


def _snapshot(
    observed_at,
    market_slug="bitcoin-up-or-down-on-may-5-2026",
    best_side="UP",
    fair_up="0.55",
    up_bid="0.50",
    up_ask="0.51",
    spot="101",
    reference="100",
    forced_exit_time=None,
    market_end_time=None,
):
    forced_exit_time = forced_exit_time or datetime(2026, 5, 5, 16, 0, tzinfo=UTC)
    fair_up_decimal = Decimal(fair_up)
    up_bid_decimal = Decimal(up_bid)
    up_ask_decimal = Decimal(up_ask)
    return {
        "observed_at": observed_at,
        "market_slug": market_slug,
        "signal_window_id": f"{market_slug}:{best_side}:2026-05-05T16:00:00+00:00",
        "market_classification": "tradable",
        "classification_reason": "iv_digital_live",
        "best_side": best_side,
        "fair_value_up": fair_up_decimal,
        "fair_value_down": Decimal("1") - fair_up_decimal,
        "current_spot_price": Decimal(spot),
        "reference_price": Decimal(reference),
        "up_best_bid": up_bid_decimal,
        "up_best_ask": up_ask_decimal,
        "down_best_bid": Decimal("1") - up_ask_decimal,
        "down_best_ask": Decimal("1") - up_bid_decimal,
        "forced_exit_time": forced_exit_time,
        "gamma_risk": "low",
        "model_confidence": "medium",
        "payload": {
            "market_end_time": market_end_time.isoformat() if market_end_time is not None else None,
        },
    }
