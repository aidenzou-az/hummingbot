from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest import TestCase

from controllers.generic.probability_gap_model_evolution import (
    DEFAULT_MODEL_SPECS,
    build_calibrated_iv_entries,
    build_market_features,
    build_model_entries,
    fair_interval_for_snapshot,
    forward_basis_iv_probability,
    horizon_smile_iv_probability,
    horizon_smile_sigma_estimate,
    run_model_evolution_report,
    smile_call_spread_probability,
    variance_strike_iv_probability,
)
from controllers.generic.probability_gap_model_validation import build_settlement_labels


class ProbabilityGapModelEvolutionTest(TestCase):
    def test_report_contains_ordered_phase_scorecards(self):
        snapshots = _sample_snapshots()

        report = run_model_evolution_report(
            snapshots,
            official_markets_by_slug={
                "bitcoin-up-or-down-on-may-5-2026": {"resolvedOutcome": "UP"},
                "bitcoin-up-or-down-on-may-6-2026": {"resolvedOutcome": "DOWN"},
            },
        )

        self.assertEqual(2, report["settlement_coverage"]["official_markets"])
        self.assertIn("baseline_iv_digital_v1", report["phase_1_settlement_objective"])
        self.assertIn("naive_always_up", report["phase_1_settlement_objective"]["naive_baselines"])
        self.assertIn("naive_buy_cheaper_side", report["phase_1_settlement_objective"]["naive_baselines"])
        self.assertIn("iv_digital_bucket_shrinkage", report["phase_2_calibration"]["calibrated_models"])
        self.assertIn("ensemble_equal_iv_rv_mid", report["phase_3_ensemble"]["ensemble_models"])
        self.assertIn("iv_digital_v2_raw_candidates", report)
        self.assertIn("market_stability", report["iv_digital_v2_raw_candidates"])
        self.assertEqual(
            "implemented",
            report["iv_digital_v2_raw_candidates"]["feasibility"]["iv_digital_smile_call_spread_v2"]["status"],
        )
        self.assertGreater(report["phase_3_ensemble"]["weight_grid"]["n_candidates"], 0)
        self.assertTrue(
            any(
                "non_actionable_sample_bias_risk" in row["flags"]
                for row in report["phase_3_ensemble"]["weight_grid"]["top_by_avg_settlement_pnl"]
            )
        )
        self.assertEqual(
            "collect_more_settled_markets_before_live_model_change",
            report["decision"]["recommendation"],
        )
        self.assertIn("calibration_status", report["decision"])

    def test_candidate_models_emit_bounded_complement_consistent_entries(self):
        snapshots = _sample_snapshots()
        labels = build_settlement_labels(
            snapshots,
            official_markets_by_slug={
                "bitcoin-up-or-down-on-may-5-2026": {"resolvedOutcome": "UP"},
                "bitcoin-up-or-down-on-may-6-2026": {"resolvedOutcome": "DOWN"},
            },
        )
        features = build_market_features(snapshots)

        entries = build_model_entries(snapshots, labels, features, DEFAULT_MODEL_SPECS)

        self.assertIn("iv_digital_v1", entries)
        self.assertIn("iv_digital_variance_strike_v2", entries)
        self.assertIn("iv_digital_forward_rf_v2", entries)
        self.assertIn("iv_digital_forward_basis_v2", entries)
        self.assertIn("iv_digital_smile_call_spread_v2", entries)
        self.assertIn("iv_digital_horizon_smile_v2", entries)
        self.assertIn("naive_always_up", entries)
        self.assertIn("naive_always_down", entries)
        self.assertIn("naive_buy_cheaper_side", entries)
        self.assertIn("old_delta_spot_blend", entries)
        self.assertIn("polymarket_mid", entries)
        self.assertGreater(len(entries["ensemble_iv_mid_70_30"]), 0)
        for model_entries in entries.values():
            for entry in model_entries:
                self.assertGreaterEqual(entry["fair_up"], Decimal("0"))
                self.assertLessEqual(entry["fair_up"], Decimal("1"))
                self.assertIn(entry["side"], ("UP", "DOWN"))

    def test_raw_iv_v2_candidates_are_bounded_and_emit_fair_interval(self):
        snapshot = _sample_snapshots()[0]

        probability = variance_strike_iv_probability(snapshot)
        interval = fair_interval_for_snapshot(snapshot)

        self.assertIsNotNone(probability)
        self.assertGreaterEqual(probability, Decimal("0"))
        self.assertLessEqual(probability, Decimal("1"))
        self.assertIsNotNone(interval)
        fair_low, raw, fair_high = interval
        self.assertLessEqual(fair_low, raw)
        self.assertLessEqual(raw, fair_high)

    def test_forward_basis_candidate_uses_persisted_forward_price(self):
        snapshot = _sample_snapshots()[0]

        raw = snapshot["fair_value_up"]
        probability = forward_basis_iv_probability(snapshot)

        self.assertIsNotNone(probability)
        self.assertGreater(probability, raw)
        self.assertLessEqual(probability, Decimal("1"))

    def test_smile_call_spread_candidate_uses_only_ok_estimates(self):
        snapshot = _sample_snapshots()[0]

        probability = smile_call_spread_probability(snapshot)

        self.assertEqual(Decimal("0.61"), probability)

    def test_horizon_smile_candidate_projects_chain_iv_to_market_end(self):
        snapshot = _sample_snapshots()[0]

        sigma_estimate = horizon_smile_sigma_estimate(snapshot)
        probability = horizon_smile_iv_probability(snapshot)

        self.assertEqual("ok", sigma_estimate.status)
        self.assertIsNotNone(probability)
        self.assertGreaterEqual(probability, Decimal("0"))
        self.assertLessEqual(probability, Decimal("1"))

    def test_leave_one_market_calibration_scores_only_excluded_market(self):
        snapshots = _sample_snapshots()
        labels = build_settlement_labels(
            snapshots,
            official_markets_by_slug={
                "bitcoin-up-or-down-on-may-5-2026": {"resolvedOutcome": "UP"},
                "bitcoin-up-or-down-on-may-6-2026": {"resolvedOutcome": "DOWN"},
            },
        )
        features = build_market_features(snapshots)

        entries = build_calibrated_iv_entries(
            snapshots,
            labels,
            features,
            excluded_market="bitcoin-up-or-down-on-may-6-2026",
        )

        self.assertGreater(len(entries), 0)
        self.assertEqual({"bitcoin-up-or-down-on-may-6-2026"}, {entry["market_slug"] for entry in entries})


def _sample_snapshots():
    start = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
    market_end_1 = datetime(2026, 5, 5, 16, 0, tzinfo=UTC)
    market_end_2 = datetime(2026, 5, 6, 16, 0, tzinfo=UTC)
    snapshots = []
    for index, spot in enumerate(("100", "101", "102", "103")):
        snapshots.append(
            _snapshot(
                observed_at=start + timedelta(minutes=index * 15),
                market_slug="bitcoin-up-or-down-on-may-5-2026",
                market_end_time=market_end_1,
                spot=spot,
                reference="100",
                fair_up=str(Decimal("0.55") + Decimal(index) * Decimal("0.03")),
                up_bid=str(Decimal("0.50") + Decimal(index) * Decimal("0.02")),
                up_ask=str(Decimal("0.52") + Decimal(index) * Decimal("0.02")),
            )
        )
    for index, spot in enumerate(("103", "102", "101", "100")):
        snapshots.append(
            _snapshot(
                observed_at=start + timedelta(days=1, minutes=index * 15),
                market_slug="bitcoin-up-or-down-on-may-6-2026",
                market_end_time=market_end_2,
                spot=spot,
                reference="103",
                fair_up=str(Decimal("0.45") - Decimal(index) * Decimal("0.03")),
                up_bid=str(Decimal("0.46") - Decimal(index) * Decimal("0.02")),
                up_ask=str(Decimal("0.48") - Decimal(index) * Decimal("0.02")),
            )
        )
    return snapshots


def _snapshot(
    observed_at,
    market_slug,
    market_end_time,
    spot,
    reference,
    fair_up,
    up_bid,
    up_ask,
):
    fair_up_decimal = Decimal(fair_up)
    up_bid_decimal = Decimal(up_bid)
    up_ask_decimal = Decimal(up_ask)
    return {
        "observed_at": observed_at,
        "market_slug": market_slug,
        "signal_window_id": f"{market_slug}:2026-05-05T16:00:00+00:00",
        "market_classification": "tradable",
        "classification_reason": "iv_digital_live",
        "best_side": "UP",
        "fair_value_up": fair_up_decimal,
        "fair_value_down": Decimal("1") - fair_up_decimal,
        "current_spot_price": Decimal(spot),
        "reference_price": Decimal(reference),
        "forward_source": "perp_mark",
        "estimated_forward_price": Decimal(spot) * Decimal("1.001"),
        "basis_annualized": Decimal("0.10"),
        "perp_mark_price": Decimal(spot) * Decimal("1.001"),
        "perp_index_price": Decimal(spot),
        "perp_last_funding_rate": Decimal("0.0001"),
        "perp_next_funding_time": observed_at + timedelta(hours=8),
        "delivery_symbol": "",
        "delivery_price": None,
        "forward_basis_reason": "perp_mark_basis_fallback",
        "option_chain_slice_count": 4,
        "option_chain_slice_source": "binance_eapi_mark_ticker",
        "option_chain_slice_expiry": market_end_time,
        "option_chain_horizon_mismatch_minutes": Decimal("0"),
        "smile_call_spread_probability": Decimal("0.61"),
        "smile_call_spread_status": "ok",
        "smile_call_spread_reason": "finite_difference_call_spread",
        "option_chain_slice": [
            {"side": "CALL", "strike": Decimal(reference) - Decimal("1"), "mark_iv": Decimal("0.30")},
            {"side": "PUT", "strike": Decimal(reference) - Decimal("1"), "mark_iv": Decimal("0.34")},
            {"side": "CALL", "strike": Decimal(reference) + Decimal("1"), "mark_iv": Decimal("0.40")},
            {"side": "PUT", "strike": Decimal(reference) + Decimal("1"), "mark_iv": Decimal("0.44")},
        ],
        "up_best_bid": up_bid_decimal,
        "up_best_ask": up_ask_decimal,
        "down_best_bid": Decimal("1") - up_ask_decimal,
        "down_best_ask": Decimal("1") - up_bid_decimal,
        "forced_exit_time": market_end_time - timedelta(hours=8),
        "gamma_risk": "low",
        "model_confidence": "medium",
        "payload": {
            "market_end_time": market_end_time.isoformat(),
            "selected_option_expiry": (market_end_time - timedelta(hours=8)).isoformat(),
            "interpolated_option_delta": str(fair_up_decimal + Decimal("0.05")),
            "lower_strike": str(Decimal(reference) - Decimal("100")),
            "upper_strike": str(Decimal(reference) + Decimal("100")),
            "lower_iv": "0.30",
            "upper_iv": "0.36",
            "option_iv": "0.33",
            "risk_free_rate": "0.00",
            "forward_source": "perp_mark",
            "estimated_forward_price": str(Decimal(spot) * Decimal("1.001")),
            "basis_annualized": "0.10",
            "perp_mark_price": str(Decimal(spot) * Decimal("1.001")),
            "perp_index_price": spot,
            "perp_last_funding_rate": "0.0001",
            "perp_next_funding_time": (observed_at + timedelta(hours=8)).isoformat(),
            "forward_basis_reason": "perp_mark_basis_fallback",
            "smile_call_spread_probability": "0.61",
            "smile_call_spread_status": "ok",
            "smile_call_spread_reason": "finite_difference_call_spread",
        },
    }
