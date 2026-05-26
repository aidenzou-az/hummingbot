import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from controllers.generic.probability_gap_model_validation import (
    SettlementLabel,
    build_model_validation_entries,
    build_settlement_labels,
    calibration_report,
    closeout_vs_settlement_report,
    settlement_coverage,
    truth_table,
)
from controllers.generic.probability_gap_option_chain import estimate_horizon_smile_sigma
from controllers.generic.probability_gap_sampling import ONE, ZERO, _entry_ask, _exit_bid


YEAR_MINUTES = Decimal("525600")
MIN_SIGMA = Decimal("0.01")
MAX_SIGMA = Decimal("5")


@dataclass(frozen=True)
class ModelSpec:
    name: str
    kind: str
    components: Optional[Dict[str, Decimal]] = None


DEFAULT_MODEL_SPECS = [
    ModelSpec("naive_always_up", "always_up"),
    ModelSpec("naive_always_down", "always_down"),
    ModelSpec("naive_buy_cheaper_side", "buy_cheaper_side"),
    ModelSpec("iv_digital_v1", "raw_iv"),
    ModelSpec("iv_digital_variance_strike_v2", "variance_strike_iv"),
    ModelSpec("iv_digital_forward_rf_v2", "forward_rf_iv"),
    ModelSpec("iv_digital_forward_basis_v2", "forward_basis_iv"),
    ModelSpec("iv_digital_smile_call_spread_v2", "smile_call_spread"),
    ModelSpec("iv_digital_horizon_smile_v2", "horizon_smile_iv"),
    ModelSpec("old_delta_spot_blend", "old_delta_spot_blend"),
    ModelSpec("realized_vol_digital", "realized_vol_digital"),
    ModelSpec("spot_rv_brownian", "spot_rv_brownian"),
    ModelSpec("polymarket_mid", "polymarket_mid"),
    ModelSpec(
        "ensemble_equal_iv_rv_mid",
        "ensemble",
        {"iv_digital_v1": Decimal("1"), "realized_vol_digital": Decimal("1"), "polymarket_mid": Decimal("1")},
    ),
    ModelSpec(
        "ensemble_iv_mid_70_30",
        "ensemble",
        {"iv_digital_v1": Decimal("0.7"), "polymarket_mid": Decimal("0.3")},
    ),
    ModelSpec(
        "ensemble_iv_rv_mid_50_25_25",
        "ensemble",
        {"iv_digital_v1": Decimal("0.5"), "realized_vol_digital": Decimal("0.25"), "polymarket_mid": Decimal("0.25")},
    ),
]


def run_model_evolution_report(
    snapshots: Sequence[Dict[str, Any]],
    official_markets_by_slug: Optional[Dict[str, Dict[str, Any]]] = None,
    binance_settlements_by_slug: Optional[Dict[str, Dict[str, Any]]] = None,
    proxy_window_seconds: int = 60,
) -> Dict[str, Any]:
    labels = build_settlement_labels(
        snapshots,
        official_markets_by_slug=official_markets_by_slug,
        binance_settlements_by_slug=binance_settlements_by_slug,
        proxy_window_seconds=proxy_window_seconds,
    )
    market_features = build_market_features(snapshots)
    baseline_entries = build_model_validation_entries(snapshots, labels)
    raw_model_entries = build_model_entries(snapshots, labels, market_features, DEFAULT_MODEL_SPECS)
    calibration_entries = build_calibrated_iv_entries(snapshots, labels, market_features)
    model_entries = dict(raw_model_entries)
    if calibration_entries:
        model_entries["iv_digital_bucket_shrinkage"] = calibration_entries

    calibration_lomo = leave_one_market_out_calibration(snapshots, labels, market_features)
    naive_scorecard = {
        name: score_model_entries(entries)
        for name, entries in sorted(raw_model_entries.items())
        if name.startswith("naive_")
    }
    raw_candidate_report = build_iv_digital_v2_candidate_report(snapshots, labels, market_features, raw_model_entries)
    return {
        "settlement_coverage": settlement_coverage(labels),
        "phase_1_settlement_objective": {
            "baseline_entries_count": len(baseline_entries),
            "baseline_iv_digital_v1": score_model_entries(baseline_entries),
            "naive_baselines": naive_scorecard,
            "raw_model_scorecard": {
                name: score_model_entries(entries)
                for name, entries in sorted(raw_model_entries.items())
            },
        },
        "phase_2_calibration": {
            "calibrated_models": {
                "iv_digital_bucket_shrinkage": score_model_entries(calibration_entries),
            },
            "leave_one_market_out": calibration_lomo,
        },
        "phase_3_ensemble": {
            "ensemble_models": {
                name: score_model_entries(entries)
                for name, entries in sorted(model_entries.items())
                if name.startswith("ensemble_")
            },
            "weight_grid": build_ensemble_weight_grid(snapshots, labels, market_features),
            "all_model_summary": {
                name: _compact_model_summary(score_model_entries(entries))
                for name, entries in sorted(model_entries.items())
            },
        },
        "iv_digital_v2_raw_candidates": raw_candidate_report,
        "decision": model_evolution_decision(model_entries, calibration_lomo, naive_scorecard),
    }


def build_market_features(snapshots: Sequence[Dict[str, Any]], lookback_returns: int = 12) -> Dict[int, Dict[str, Any]]:
    features: Dict[int, Dict[str, Any]] = {}
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        grouped[snapshot.get("market_slug", "")].append(snapshot)
    for market_snapshots in grouped.values():
        ordered = sorted(market_snapshots, key=lambda item: (item.get("observed_at"), item.get("signal_window_id", "")))
        returns: List[Tuple[Decimal, Decimal]] = []
        previous = None
        for snapshot in ordered:
            if previous is not None:
                returns.extend(_spot_return(previous, snapshot))
            rolling = returns[-lookback_returns:]
            features[id(snapshot)] = {
                "realized_vol": _annualized_realized_vol(rolling),
            }
            previous = snapshot
    return features


def build_model_entries(
    snapshots: Sequence[Dict[str, Any]],
    labels: Dict[str, SettlementLabel],
    market_features: Dict[int, Dict[str, Any]],
    model_specs: Iterable[ModelSpec],
) -> Dict[str, List[Dict[str, Any]]]:
    base_probabilities = {
        spec.name: build_model_probabilities(snapshots, market_features, spec)
        for spec in model_specs
        if spec.kind != "ensemble"
    }
    entries_by_model: Dict[str, List[Dict[str, Any]]] = {}
    for spec in model_specs:
        if spec.kind == "ensemble":
            probabilities = build_ensemble_probabilities(snapshots, base_probabilities, spec.components or {})
        else:
            probabilities = base_probabilities.get(spec.name, {})
        entries_by_model[spec.name] = build_entries_from_probabilities(snapshots, labels, probabilities, spec.name)
    return entries_by_model


def build_model_probabilities(
    snapshots: Sequence[Dict[str, Any]],
    market_features: Dict[int, Dict[str, Any]],
    spec: ModelSpec,
) -> Dict[int, Decimal]:
    probabilities: Dict[int, Decimal] = {}
    for snapshot in snapshots:
        if spec.kind == "always_up":
            probability = ONE
        elif spec.kind == "always_down":
            probability = ZERO
        elif spec.kind == "buy_cheaper_side":
            probability = cheaper_side_probability(snapshot)
        elif spec.kind == "raw_iv":
            probability = snapshot.get("fair_value_up")
        elif spec.kind == "variance_strike_iv":
            probability = variance_strike_iv_probability(snapshot)
        elif spec.kind == "forward_rf_iv":
            probability = forward_rf_iv_probability(snapshot)
        elif spec.kind == "forward_basis_iv":
            probability = forward_basis_iv_probability(snapshot)
        elif spec.kind == "smile_call_spread":
            probability = smile_call_spread_probability(snapshot)
        elif spec.kind == "horizon_smile_iv":
            probability = horizon_smile_iv_probability(snapshot)
        elif spec.kind == "old_delta_spot_blend":
            probability = old_delta_spot_blend_probability(snapshot)
        elif spec.kind == "realized_vol_digital":
            probability = realized_vol_digital_probability(snapshot, market_features.get(id(snapshot), {}).get("realized_vol"), drift_adjusted=False)
        elif spec.kind == "spot_rv_brownian":
            probability = realized_vol_digital_probability(snapshot, market_features.get(id(snapshot), {}).get("realized_vol"), drift_adjusted=True)
        elif spec.kind == "polymarket_mid":
            probability = polymarket_mid_probability(snapshot)
        else:
            probability = None
        if probability is not None:
            probabilities[id(snapshot)] = _clamp_probability(probability)
    return probabilities


def build_iv_digital_v2_candidate_report(
    snapshots: Sequence[Dict[str, Any]],
    labels: Dict[str, SettlementLabel],
    market_features: Dict[int, Dict[str, Any]],
    model_entries: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    candidate_names = [
        "iv_digital_v1",
        "iv_digital_variance_strike_v2",
        "iv_digital_forward_rf_v2",
        "iv_digital_forward_basis_v2",
        "iv_digital_smile_call_spread_v2",
        "iv_digital_horizon_smile_v2",
    ]
    scorecard = {
        name: score_model_entries(model_entries.get(name, []))
        for name in candidate_names
    }
    return {
        "feasibility": raw_candidate_feasibility(snapshots),
        "scorecard": scorecard,
        "market_stability": {
            name: _market_stability_summary(score)
            for name, score in scorecard.items()
        },
        "fair_interval": fair_interval_report(snapshots, labels),
        "probability_delta": probability_delta_report(snapshots, market_features),
        "decision": raw_candidate_decision(scorecard),
    }


def raw_candidate_feasibility(snapshots: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    tradable = [snapshot for snapshot in snapshots if snapshot.get("market_classification") == "tradable"]
    total = len(tradable)
    variance_supported = sum(1 for snapshot in tradable if variance_strike_iv_probability(snapshot) is not None)
    forward_supported = sum(1 for snapshot in tradable if forward_rf_iv_probability(snapshot) is not None)
    forward_basis_supported = sum(1 for snapshot in tradable if forward_basis_iv_probability(snapshot) is not None)
    smile_supported = sum(1 for snapshot in tradable if smile_call_spread_probability(snapshot) is not None)
    horizon_smile_supported = sum(1 for snapshot in tradable if horizon_smile_iv_probability(snapshot) is not None)
    fair_interval_supported = sum(1 for snapshot in tradable if fair_interval_for_snapshot(snapshot) is not None)
    forward_source_counts: Dict[str, int] = defaultdict(int)
    for snapshot in tradable:
        source = snapshot.get("forward_source") or (snapshot.get("payload") or {}).get("forward_source") or "missing"
        forward_source_counts[str(source)] += 1
    smile_status_counts: Dict[str, int] = defaultdict(int)
    for snapshot in tradable:
        status = snapshot.get("smile_call_spread_status") or (snapshot.get("payload") or {}).get("smile_call_spread_status") or "missing"
        smile_status_counts[str(status)] += 1
    horizon_smile_status_counts: Dict[str, int] = defaultdict(int)
    for snapshot in tradable:
        horizon_smile_status_counts[horizon_smile_sigma_estimate(snapshot).status] += 1
    return {
        "tradable_snapshots": total,
        "iv_digital_variance_strike_v2": _candidate_status(
            total,
            variance_supported,
            "implemented",
            "requires lower/upper strike and IV provenance",
        ),
        "iv_digital_forward_rf_v2": _candidate_status(
            total,
            forward_supported,
            "fallback",
            "uses risk_free_rate forward fallback; true futures basis is not stored",
        ),
        "iv_digital_forward_basis_v2": {
            **_candidate_status(
                total,
                forward_basis_supported,
                "implemented",
                "requires estimated_forward_price plus option IV",
            ),
            "forward_source_counts": dict(sorted(forward_source_counts.items())),
        },
        "iv_digital_smile_call_spread_v2": {
            **_smile_candidate_status(total, smile_supported, smile_status_counts),
            "status_counts": dict(sorted(smile_status_counts.items())),
        },
        "iv_digital_horizon_smile_v2": {
            **_candidate_status(
                total,
                horizon_smile_supported,
                "implemented",
                "uses local option-chain IV interpolation projected to Polymarket market_end_time",
            ),
            "status_counts": dict(sorted(horizon_smile_status_counts.items())),
        },
        "fair_interval_uncertainty": _candidate_status(
            total,
            fair_interval_supported,
            "implemented",
            "uses lower/upper IV provenance as an uncertainty interval around raw fair",
        ),
    }


def fair_interval_report(
    snapshots: Sequence[Dict[str, Any]],
    labels: Dict[str, SettlementLabel],
) -> Dict[str, Any]:
    rows = []
    for snapshot in snapshots:
        if snapshot.get("market_classification") != "tradable":
            continue
        interval = fair_interval_for_snapshot(snapshot)
        if interval is None:
            continue
        fair_low, fair_mid, fair_high = interval
        width = fair_high - fair_low
        rows.append({
            "market_slug": snapshot.get("market_slug", ""),
            "width": width,
            "contains_raw": fair_low <= fair_mid <= fair_high,
            "outcome": labels.get(snapshot.get("market_slug", "")).outcome if labels.get(snapshot.get("market_slug", "")) else None,
        })
    if not rows:
        return {"n": 0, "avg_width": None, "wide_interval_rate": None, "contains_raw_rate": None}
    return {
        "n": len(rows),
        "avg_width": float(sum((row["width"] for row in rows), ZERO) / Decimal(str(len(rows)))),
        "wide_interval_rate": sum(1 for row in rows if row["width"] >= Decimal("0.05")) / len(rows),
        "contains_raw_rate": sum(1 for row in rows if row["contains_raw"]) / len(rows),
    }


def probability_delta_report(
    snapshots: Sequence[Dict[str, Any]],
    market_features: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    deltas: Dict[str, List[Decimal]] = defaultdict(list)
    rows = []
    for snapshot in snapshots:
        if snapshot.get("market_classification") != "tradable":
            continue
        horizon = horizon_smile_iv_probability(snapshot)
        if horizon is None:
            continue
        comparisons = {
            "vs_iv_digital_v1": snapshot.get("fair_value_up"),
            "vs_iv_digital_forward_basis_v2": forward_basis_iv_probability(snapshot),
            "vs_iv_digital_variance_strike_v2": variance_strike_iv_probability(snapshot),
            "vs_realized_vol_digital": realized_vol_digital_probability(
                snapshot,
                market_features.get(id(snapshot), {}).get("realized_vol"),
                drift_adjusted=False,
            ),
        }
        row = {
            "market_slug": snapshot.get("market_slug", ""),
            "observed_at": snapshot.get("observed_at"),
            "horizon_smile": horizon,
        }
        for name, probability in comparisons.items():
            if probability is None:
                continue
            delta = horizon - probability
            deltas[name].append(delta)
            row[name] = delta
        rows.append(row)
    return {
        "n": len(rows),
        "summary": {
            name: _decimal_distribution(values)
            for name, values in sorted(deltas.items())
        },
        "latest_rows": [
            _serialize_probability_delta_row(row)
            for row in rows[-5:]
        ],
    }


def raw_candidate_decision(scorecard: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    raw = _compact_model_summary(scorecard.get("iv_digital_v1", {}))
    best_name = None
    best_summary = None
    for name, score in scorecard.items():
        if name == "iv_digital_v1":
            continue
        summary = _compact_model_summary(score)
        avg_pnl = summary.get("avg_settlement_pnl")
        if avg_pnl is None:
            continue
        if best_summary is None or avg_pnl > best_summary.get("avg_settlement_pnl", float("-inf")):
            best_name = name
            best_summary = summary
    raw_avg = raw.get("avg_settlement_pnl")
    best_avg = (best_summary or {}).get("avg_settlement_pnl")
    if best_name is not None and raw_avg is not None and best_avg is not None and best_avg > raw_avg:
        recommendation = "raw_candidate_requires_more_markets_before_live_change"
        reason = "best raw candidate beats iv_digital_v1 in-sample, but current market count remains below the 5-10 market threshold."
    else:
        recommendation = "keep_raw_iv_digital_v1"
        reason = "no implemented raw candidate improves the current raw baseline under the available settlement-aware scorecard."
    return {
        "best_candidate": best_name,
        "best_candidate_summary": best_summary,
        "best_candidate_market_stability": _market_stability_summary(scorecard.get(best_name, {})) if best_name else None,
        "raw_iv_digital_v1": raw,
        "raw_iv_digital_v1_market_stability": _market_stability_summary(scorecard.get("iv_digital_v1", {})),
        "recommendation": recommendation,
        "reason": reason,
    }


def build_ensemble_probabilities(
    snapshots: Sequence[Dict[str, Any]],
    base_probabilities: Dict[str, Dict[int, Decimal]],
    weights: Dict[str, Decimal],
) -> Dict[int, Decimal]:
    probabilities: Dict[int, Decimal] = {}
    for snapshot in snapshots:
        weighted_total = ZERO
        weight_total = ZERO
        for model_name, weight in weights.items():
            probability = base_probabilities.get(model_name, {}).get(id(snapshot))
            if probability is None or weight <= ZERO:
                continue
            weighted_total += probability * weight
            weight_total += weight
        if weight_total > ZERO:
            probabilities[id(snapshot)] = _clamp_probability(weighted_total / weight_total)
    return probabilities


def build_ensemble_weight_grid(
    snapshots: Sequence[Dict[str, Any]],
    labels: Dict[str, SettlementLabel],
    market_features: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    component_specs = [
        ModelSpec("iv_digital_v1", "raw_iv"),
        ModelSpec("realized_vol_digital", "realized_vol_digital"),
        ModelSpec("polymarket_mid", "polymarket_mid"),
    ]
    base_probabilities = {
        spec.name: build_model_probabilities(snapshots, market_features, spec)
        for spec in component_specs
    }
    rows = []
    grid_values = [Decimal("0"), Decimal("0.25"), Decimal("0.5"), Decimal("0.75"), Decimal("1")]
    for iv_weight in grid_values:
        for rv_weight in grid_values:
            for mid_weight in grid_values:
                total = iv_weight + rv_weight + mid_weight
                if total != ONE:
                    continue
                weights = {
                    "iv_digital_v1": iv_weight,
                    "realized_vol_digital": rv_weight,
                    "polymarket_mid": mid_weight,
                }
                probabilities = build_ensemble_probabilities(snapshots, base_probabilities, weights)
                entries = build_entries_from_probabilities(
                    snapshots,
                    labels,
                    probabilities,
                    f"ensemble_grid_iv_{iv_weight}_rv_{rv_weight}_mid_{mid_weight}",
                )
                summary = _compact_model_summary(score_model_entries(entries))
                rows.append({
                    "flags": ensemble_candidate_flags(weights, summary),
                    "weights": {key: float(value) for key, value in weights.items()},
                    "summary": summary,
                })
    return {
        "n_candidates": len(rows),
        "top_by_avg_settlement_pnl": sorted(
            rows,
            key=lambda row: row["summary"]["avg_settlement_pnl"] if row["summary"]["avg_settlement_pnl"] is not None else float("-inf"),
            reverse=True,
        )[:5],
        "top_by_brier": sorted(
            rows,
            key=lambda row: row["summary"]["brier"] if row["summary"]["brier"] is not None else float("inf"),
        )[:5],
    }


def build_calibrated_iv_entries(
    snapshots: Sequence[Dict[str, Any]],
    labels: Dict[str, SettlementLabel],
    market_features: Dict[int, Dict[str, Any]],
    excluded_market: Optional[str] = None,
    model_name: str = "iv_digital_bucket_shrinkage",
) -> List[Dict[str, Any]]:
    raw_probabilities = build_model_probabilities(snapshots, market_features, ModelSpec("iv_digital_v1", "raw_iv"))
    calibrator = fit_bucket_shrinkage_calibrator(snapshots, labels, raw_probabilities, excluded_market=excluded_market)
    calibrated = {
        snapshot_id: calibrator(probability)
        for snapshot_id, probability in raw_probabilities.items()
    }
    target_snapshots = [
        snapshot for snapshot in snapshots
        if excluded_market is None or snapshot.get("market_slug") == excluded_market
    ]
    return build_entries_from_probabilities(target_snapshots, labels, calibrated, model_name)


def fit_bucket_shrinkage_calibrator(
    snapshots: Sequence[Dict[str, Any]],
    labels: Dict[str, SettlementLabel],
    raw_probabilities: Dict[int, Decimal],
    excluded_market: Optional[str] = None,
    prior_strength: Decimal = Decimal("20"),
):
    values: List[Tuple[Decimal, Decimal]] = []
    buckets: Dict[str, List[Tuple[Decimal, Decimal]]] = defaultdict(list)
    for snapshot in snapshots:
        market_slug = snapshot.get("market_slug")
        if excluded_market is not None and market_slug == excluded_market:
            continue
        label = labels.get(market_slug)
        probability = raw_probabilities.get(id(snapshot))
        if label is None or label.outcome is None or probability is None:
            continue
        actual = ONE if label.outcome == "UP" else ZERO
        values.append((probability, actual))
        buckets[_probability_bucket(probability)].append((probability, actual))

    global_rate = _mean((actual for _, actual in values), Decimal("0.5"))
    bucket_rates = {}
    for bucket, bucket_values in buckets.items():
        actual_sum = sum((actual for _, actual in bucket_values), ZERO)
        n = Decimal(str(len(bucket_values)))
        bucket_rates[bucket] = (actual_sum + global_rate * prior_strength) / (n + prior_strength)

    def calibrate(probability: Decimal) -> Decimal:
        bucket_rate = bucket_rates.get(_probability_bucket(probability), global_rate)
        n = Decimal(str(len(buckets.get(_probability_bucket(probability), []))))
        blend_weight = n / (n + prior_strength) if n + prior_strength > ZERO else ZERO
        return _clamp_probability((bucket_rate * blend_weight) + (probability * (ONE - blend_weight)))

    return calibrate


def leave_one_market_out_calibration(
    snapshots: Sequence[Dict[str, Any]],
    labels: Dict[str, SettlementLabel],
    market_features: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    settled_markets = sorted(slug for slug, label in labels.items() if label.outcome is not None)
    rows = []
    for market_slug in settled_markets:
        entries = build_calibrated_iv_entries(
            snapshots,
            labels,
            market_features,
            excluded_market=market_slug,
            model_name="iv_digital_bucket_shrinkage_lomo",
        )
        rows.append({
            "market_slug": market_slug,
            "score": _compact_model_summary(score_model_entries(entries)),
        })
    return {
        "n_markets": len(settled_markets),
        "warning": "too_few_markets_for_strong_out_of_sample_claim" if len(settled_markets) < 5 else None,
        "rows": rows,
    }


def build_entries_from_probabilities(
    snapshots: Sequence[Dict[str, Any]],
    labels: Dict[str, SettlementLabel],
    fair_up_by_snapshot_id: Dict[int, Decimal],
    model_name: str,
) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        grouped[snapshot.get("market_slug", "")].append(snapshot)
    entries: List[Dict[str, Any]] = []
    for market_slug, market_snapshots in grouped.items():
        label = labels.get(market_slug)
        if label is None or label.outcome is None:
            continue
        ordered = sorted(market_snapshots, key=lambda item: (item.get("observed_at"), item.get("signal_window_id", "")))
        for index, snapshot in enumerate(ordered):
            if snapshot.get("market_classification") != "tradable":
                continue
            fair_up = fair_up_by_snapshot_id.get(id(snapshot))
            if fair_up is None:
                continue
            up_ask = _entry_ask(snapshot, "UP")
            down_ask = _entry_ask(snapshot, "DOWN")
            if up_ask is None or down_ask is None:
                continue
            fair_down = ONE - fair_up
            up_edge = fair_up - up_ask
            down_edge = fair_down - down_ask
            side = "UP" if up_edge >= down_edge else "DOWN"
            ask = up_ask if side == "UP" else down_ask
            fair = fair_up if side == "UP" else fair_down
            mid = polymarket_mid_probability(snapshot)
            if mid is None:
                continue
            side_mid = mid if side == "UP" else ONE - mid
            settlement_price = ONE if side == label.outcome else ZERO
            entries.append(
                {
                    "model_name": model_name,
                    "market_slug": market_slug,
                    "observed_at": snapshot.get("observed_at"),
                    "side": side,
                    "outcome": label.outcome,
                    "settlement_source": label.source,
                    "settlement_confidence": label.confidence,
                    "fair_up": fair_up,
                    "side_fair": fair,
                    "entry_ask": ask,
                    "side_mid": side_mid,
                    "a_edge": fair - ask,
                    "a_residual": fair - side_mid,
                    "settlement_pnl": settlement_price - ask,
                    "settlement_win": side == label.outcome,
                    "ret_5m": _future_return(ordered, index, side, ask, 300),
                    "ret_20m": _future_return(ordered, index, side, ask, 1200),
                    "gamma_risk": snapshot.get("gamma_risk", ""),
                    "model_confidence": snapshot.get("model_confidence", ""),
                    "time_to_expiry_bucket": _time_to_expiry_bucket(snapshot),
                    "spread_bucket": _spread_bucket(_side_spread(snapshot, side)),
                }
            )
    return entries


def score_model_entries(entries: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    settlement_pnls = [entry["settlement_pnl"] for entry in entries]
    return {
        "n_entries": len(entries),
        "calibration": calibration_report(entries),
        "settlement_pnl": _pnl_summary(settlement_pnls),
        "side_bias": {
            "UP": sum(1 for entry in entries if entry["side"] == "UP"),
            "DOWN": sum(1 for entry in entries if entry["side"] == "DOWN"),
        },
        "by_market": _by_market_summary(entries),
        "a_edge_truth_table": truth_table(entries, "a_edge"),
        "a_residual_truth_table": truth_table(entries, "a_residual"),
        "closeout_vs_settlement": closeout_vs_settlement_report(entries),
    }


def model_evolution_decision(
    model_entries: Dict[str, Sequence[Dict[str, Any]]],
    calibration_lomo: Optional[Dict[str, Any]] = None,
    naive_scorecard: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    summaries = {
        name: _compact_model_summary(score_model_entries(entries))
        for name, entries in model_entries.items()
    }
    raw = summaries.get("iv_digital_v1", {})
    best_name = None
    best_avg = None
    for name, summary in summaries.items():
        avg_pnl = summary.get("avg_settlement_pnl")
        if avg_pnl is None:
            continue
        if best_avg is None or avg_pnl > best_avg:
            best_name = name
            best_avg = avg_pnl
    lomo_rows = (calibration_lomo or {}).get("rows", [])
    lomo_negative_rows = [
        row for row in lomo_rows
        if row.get("score", {}).get("avg_settlement_pnl") is not None
        and row["score"]["avg_settlement_pnl"] < 0
    ]
    calibration_status = (
        "in_sample_only_rejected_by_leave_one_market_out"
        if lomo_negative_rows
        else "insufficient_market_count"
    )
    naive_summaries = {
        name: _compact_model_summary(score)
        for name, score in (naive_scorecard or {}).items()
    }
    return {
        "best_avg_settlement_pnl_model": best_name,
        "calibration_status": calibration_status,
        "negative_lomo_markets": [row["market_slug"] for row in lomo_negative_rows],
        "naive_baselines": naive_summaries,
        "market_baseline_policy": "polymarket_mid_is_non_actionable_unless_it_beats_naive_baselines_without_one_sided_or_lomo_failure",
        "raw_iv_digital_v1": raw,
        "recommendation": "collect_more_settled_markets_before_live_model_change",
        "reason": "WU-010 is offline research; calibration can look strong in-sample but current leave-one-market-out evidence is too weak or negative.",
    }


def old_delta_spot_blend_probability(snapshot: Dict[str, Any]) -> Optional[Decimal]:
    spot_signal = _spot_probability_proxy(snapshot.get("current_spot_price"), snapshot.get("reference_price"))
    if spot_signal is None:
        return None
    payload = snapshot.get("payload") or {}
    delta = _safe_decimal(payload.get("interpolated_option_delta"))
    option_expiry = _parse_datetime(payload.get("selected_option_expiry")) or snapshot.get("selected_option_expiry")
    observed_at = snapshot.get("observed_at")
    market_end = _snapshot_market_end_time(snapshot)
    if delta is None or option_expiry is None or observed_at is None or market_end is None:
        return spot_signal
    minutes_to_settlement = Decimal(str((market_end - observed_at).total_seconds() / 60))
    minutes_to_option_expiry = Decimal(str((option_expiry - observed_at).total_seconds() / 60))
    if minutes_to_settlement <= ZERO or minutes_to_option_expiry <= ZERO:
        return None
    overlap_penalty = abs(minutes_to_option_expiry - minutes_to_settlement) / Decimal("1440")
    weight = max(ZERO, ONE - overlap_penalty)
    return _clamp_probability(delta * weight + spot_signal * (ONE - weight))


def variance_strike_iv_probability(snapshot: Dict[str, Any]) -> Optional[Decimal]:
    payload = snapshot.get("payload") or {}
    lower_strike = _safe_decimal(payload.get("lower_strike"))
    upper_strike = _safe_decimal(payload.get("upper_strike"))
    lower_iv = _safe_decimal(payload.get("lower_iv"))
    upper_iv = _safe_decimal(payload.get("upper_iv"))
    reference = snapshot.get("reference_price")
    if lower_strike is None or upper_strike is None or lower_iv is None or upper_iv is None or reference is None:
        return None
    if lower_iv <= ZERO or upper_iv <= ZERO:
        return None
    if upper_strike == lower_strike:
        sigma = lower_iv
    else:
        weight = (reference - lower_strike) / (upper_strike - lower_strike)
        weight = min(ONE, max(ZERO, weight))
        interpolated_variance = (lower_iv * lower_iv) + ((upper_iv * upper_iv) - (lower_iv * lower_iv)) * weight
        if interpolated_variance <= ZERO:
            return None
        sigma = Decimal(str(math.sqrt(float(interpolated_variance))))
    return iv_digital_probability(snapshot, sigma=sigma, use_forward=False)


def forward_rf_iv_probability(snapshot: Dict[str, Any]) -> Optional[Decimal]:
    sigma = snapshot.get("option_iv") or _safe_decimal((snapshot.get("payload") or {}).get("option_iv"))
    return iv_digital_probability(snapshot, sigma=sigma, use_forward=True)


def forward_basis_iv_probability(snapshot: Dict[str, Any]) -> Optional[Decimal]:
    payload = snapshot.get("payload") or {}
    sigma = snapshot.get("option_iv") or _safe_decimal(payload.get("option_iv"))
    forward = snapshot.get("estimated_forward_price") or _safe_decimal(payload.get("estimated_forward_price"))
    reference = snapshot.get("reference_price")
    observed_at = snapshot.get("observed_at")
    market_end = _snapshot_market_end_time(snapshot)
    if forward is None or reference is None or reference <= ZERO or observed_at is None or market_end is None:
        return None
    sigma = _clamp_sigma(sigma)
    if sigma is None:
        return None
    tau = Decimal(str((market_end - observed_at).total_seconds() / 60)) / YEAR_MINUTES
    if tau <= ZERO:
        return None
    numerator = Decimal(str(math.log(float(forward / reference))))
    numerator -= Decimal("0.5") * sigma * sigma * tau
    denominator = sigma * Decimal(str(math.sqrt(float(tau))))
    if denominator <= ZERO:
        return None
    return _clamp_probability(Decimal(str(_normal_cdf(float(numerator / denominator)))))


def smile_call_spread_probability(snapshot: Dict[str, Any]) -> Optional[Decimal]:
    status = snapshot.get("smile_call_spread_status") or (snapshot.get("payload") or {}).get("smile_call_spread_status")
    if status != "ok":
        return None
    probability = snapshot.get("smile_call_spread_probability")
    if probability is None:
        probability = _safe_decimal((snapshot.get("payload") or {}).get("smile_call_spread_probability"))
    if probability is None:
        return None
    return _clamp_probability(probability)


def horizon_smile_sigma_estimate(snapshot: Dict[str, Any]):
    reference = snapshot.get("reference_price")
    if reference is None or reference <= ZERO:
        return estimate_horizon_smile_sigma([], Decimal("0"))
    rows = snapshot.get("option_chain_slice")
    if rows is None:
        rows = (snapshot.get("payload") or {}).get("option_chain_slice", [])
    if not isinstance(rows, list):
        rows = []
    return estimate_horizon_smile_sigma(rows, reference)


def horizon_smile_iv_probability(snapshot: Dict[str, Any]) -> Optional[Decimal]:
    sigma_estimate = horizon_smile_sigma_estimate(snapshot)
    if sigma_estimate.status != "ok" or sigma_estimate.sigma is None:
        return None
    payload = snapshot.get("payload") or {}
    forward = snapshot.get("estimated_forward_price") or _safe_decimal(payload.get("estimated_forward_price"))
    if forward is not None:
        return _iv_digital_probability_from_underlying(
            snapshot=snapshot,
            underlying_price=forward,
            sigma=sigma_estimate.sigma,
            drift_adjusted=True,
        )
    return iv_digital_probability(snapshot, sigma=sigma_estimate.sigma, use_forward=False)


def fair_interval_for_snapshot(snapshot: Dict[str, Any]) -> Optional[Tuple[Decimal, Decimal, Decimal]]:
    payload = snapshot.get("payload") or {}
    lower_iv = _safe_decimal(payload.get("lower_iv"))
    upper_iv = _safe_decimal(payload.get("upper_iv"))
    raw = snapshot.get("fair_value_up")
    if lower_iv is None or upper_iv is None or raw is None:
        return None
    low_probability = iv_digital_probability(snapshot, sigma=min(lower_iv, upper_iv), use_forward=False)
    high_probability = iv_digital_probability(snapshot, sigma=max(lower_iv, upper_iv), use_forward=False)
    if low_probability is None or high_probability is None:
        return None
    fair_low = min(low_probability, high_probability, raw)
    fair_high = max(low_probability, high_probability, raw)
    return fair_low, raw, fair_high


def iv_digital_probability(snapshot: Dict[str, Any], sigma: Optional[Decimal], use_forward: bool) -> Optional[Decimal]:
    spot = snapshot.get("current_spot_price")
    reference = snapshot.get("reference_price")
    observed_at = snapshot.get("observed_at")
    market_end = _snapshot_market_end_time(snapshot)
    if spot is None or reference is None or reference <= ZERO or observed_at is None or market_end is None:
        return None
    sigma = _clamp_sigma(sigma)
    if sigma is None:
        return None
    tau = Decimal(str((market_end - observed_at).total_seconds() / 60)) / YEAR_MINUTES
    if tau <= ZERO:
        return None
    risk_free_rate = snapshot.get("risk_free_rate")
    if risk_free_rate is None:
        risk_free_rate = _safe_decimal((snapshot.get("payload") or {}).get("risk_free_rate")) or ZERO
    numerator = Decimal(str(math.log(float(spot / reference))))
    if use_forward:
        forward = spot * Decimal(str(math.exp(float(risk_free_rate * tau))))
        numerator = Decimal(str(math.log(float(forward / reference))))
        numerator -= Decimal("0.5") * sigma * sigma * tau
    else:
        numerator += (risk_free_rate - Decimal("0.5") * sigma * sigma) * tau
    denominator = sigma * Decimal(str(math.sqrt(float(tau))))
    if denominator <= ZERO:
        return None
    return _clamp_probability(Decimal(str(_normal_cdf(float(numerator / denominator)))))


def _iv_digital_probability_from_underlying(
    snapshot: Dict[str, Any],
    underlying_price: Optional[Decimal],
    sigma: Optional[Decimal],
    drift_adjusted: bool,
) -> Optional[Decimal]:
    reference = snapshot.get("reference_price")
    observed_at = snapshot.get("observed_at")
    market_end = _snapshot_market_end_time(snapshot)
    if underlying_price is None or underlying_price <= ZERO or reference is None or reference <= ZERO or observed_at is None or market_end is None:
        return None
    sigma = _clamp_sigma(sigma)
    if sigma is None:
        return None
    tau = Decimal(str((market_end - observed_at).total_seconds() / 60)) / YEAR_MINUTES
    if tau <= ZERO:
        return None
    numerator = Decimal(str(math.log(float(underlying_price / reference))))
    if drift_adjusted:
        numerator -= Decimal("0.5") * sigma * sigma * tau
    denominator = sigma * Decimal(str(math.sqrt(float(tau))))
    if denominator <= ZERO:
        return None
    return _clamp_probability(Decimal(str(_normal_cdf(float(numerator / denominator)))))


def realized_vol_digital_probability(snapshot: Dict[str, Any], realized_vol: Optional[Decimal], drift_adjusted: bool) -> Optional[Decimal]:
    spot = snapshot.get("current_spot_price")
    reference = snapshot.get("reference_price")
    market_end = _snapshot_market_end_time(snapshot)
    observed_at = snapshot.get("observed_at")
    if spot is None or reference is None or reference <= ZERO or market_end is None or observed_at is None:
        return None
    sigma = _clamp_sigma(realized_vol)
    if sigma is None:
        return None
    tau = Decimal(str((market_end - observed_at).total_seconds() / 60)) / YEAR_MINUTES
    if tau <= ZERO:
        return None
    numerator = Decimal(str(math.log(float(spot / reference))))
    if drift_adjusted:
        numerator -= Decimal("0.5") * sigma * sigma * tau
    denominator = sigma * Decimal(str(math.sqrt(float(tau))))
    if denominator <= ZERO:
        return None
    return _clamp_probability(Decimal(str(_normal_cdf(float(numerator / denominator)))))


def polymarket_mid_probability(snapshot: Dict[str, Any]) -> Optional[Decimal]:
    up_bid = snapshot.get("up_best_bid")
    up_ask = snapshot.get("up_best_ask")
    if up_bid is None or up_ask is None:
        return None
    return _clamp_probability((up_bid + up_ask) / Decimal("2"))


def cheaper_side_probability(snapshot: Dict[str, Any]) -> Optional[Decimal]:
    up_ask = _entry_ask(snapshot, "UP")
    down_ask = _entry_ask(snapshot, "DOWN")
    if up_ask is None or down_ask is None:
        return None
    return ONE if up_ask <= down_ask else ZERO


def ensemble_candidate_flags(weights: Dict[str, Decimal], summary: Dict[str, Any]) -> List[str]:
    flags = []
    side_bias = summary.get("side_bias", {})
    n_entries = summary.get("n_entries") or 0
    if n_entries and (side_bias.get("UP", 0) == n_entries or side_bias.get("DOWN", 0) == n_entries):
        flags.append("one_sided_selection")
    if weights.get("polymarket_mid", ZERO) >= Decimal("0.75"):
        flags.append("polymarket_mid_heavy")
    if "one_sided_selection" in flags or "polymarket_mid_heavy" in flags:
        flags.append("non_actionable_sample_bias_risk")
    return flags


def _pnl_summary(values: Sequence[Decimal]) -> Dict[str, Any]:
    if not values:
        return {"n": 0, "avg": None, "total": None, "positive_rate": None}
    count = Decimal(str(len(values)))
    return {
        "n": len(values),
        "avg": float(sum(values, ZERO) / count),
        "total": float(sum(values, ZERO)),
        "positive_rate": sum(1 for value in values if value > ZERO) / len(values),
    }


def _decimal_distribution(values: Sequence[Decimal]) -> Dict[str, Any]:
    if not values:
        return {"n": 0, "avg": None, "min": None, "max": None, "abs_avg": None}
    count = Decimal(str(len(values)))
    return {
        "n": len(values),
        "avg": float(sum(values, ZERO) / count),
        "min": float(min(values)),
        "max": float(max(values)),
        "abs_avg": float(sum((abs(value) for value in values), ZERO) / count),
    }


def _serialize_probability_delta_row(row: Dict[str, Any]) -> Dict[str, Any]:
    serialized = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            serialized[key] = float(value)
        elif isinstance(value, datetime):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


def _by_market_summary(entries: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        grouped[entry["market_slug"]].append(entry)
    return {
        market_slug: {
            "n_entries": len(market_entries),
            "settlement_pnl": _pnl_summary([entry["settlement_pnl"] for entry in market_entries]),
            "side_bias": {
                "UP": sum(1 for entry in market_entries if entry["side"] == "UP"),
                "DOWN": sum(1 for entry in market_entries if entry["side"] == "DOWN"),
            },
        }
        for market_slug, market_entries in sorted(grouped.items())
    }


def _compact_model_summary(score: Dict[str, Any]) -> Dict[str, Any]:
    pnl = score.get("settlement_pnl", {})
    calibration = score.get("calibration", {})
    return {
        "n_entries": score.get("n_entries", 0),
        "avg_settlement_pnl": pnl.get("avg"),
        "total_settlement_pnl": pnl.get("total"),
        "positive_pnl_rate": pnl.get("positive_rate"),
        "brier": calibration.get("brier"),
        "log_loss": calibration.get("log_loss"),
        "side_bias": score.get("side_bias", {}),
    }


def _market_stability_summary(score: Dict[str, Any]) -> Dict[str, Any]:
    by_market = score.get("by_market", {})
    market_pnls = [
        market_score.get("settlement_pnl", {}).get("total")
        for market_score in by_market.values()
        if market_score.get("settlement_pnl", {}).get("total") is not None
    ]
    if not market_pnls:
        return {"n_markets": 0, "positive_markets": 0, "negative_markets": 0, "min_total_pnl": None, "max_total_pnl": None}
    return {
        "n_markets": len(market_pnls),
        "positive_markets": sum(1 for pnl in market_pnls if pnl > 0),
        "negative_markets": sum(1 for pnl in market_pnls if pnl < 0),
        "min_total_pnl": min(market_pnls),
        "max_total_pnl": max(market_pnls),
    }


def _candidate_status(total: int, supported: int, status: str, reason: str) -> Dict[str, Any]:
    return {
        "status": status if supported > 0 else "blocked_by_missing_data",
        "supported_snapshots": supported,
        "coverage": supported / total if total else 0,
        "reason": reason if supported > 0 else f"missing required fields: {reason}",
    }


def _smile_candidate_status(total: int, supported: int, status_counts: Dict[str, int]) -> Dict[str, Any]:
    if supported > 0:
        status = "implemented"
        reason = "adjacent call marks are available and option expiry is aligned with Polymarket market end"
    elif total == 0:
        status = "blocked_by_missing_data"
        reason = "no tradable snapshots to evaluate"
    elif status_counts and set(status_counts.keys()) <= {"horizon_mismatch"}:
        status = "blocked_by_horizon_mismatch"
        reason = "call-spread data exists, but option expiry is not close enough to Polymarket market end"
    elif status_counts and set(status_counts.keys()) <= {"missing", ""}:
        status = "blocked_by_missing_data"
        reason = "current snapshots do not store option-chain slice or call-spread status"
    else:
        status = "blocked_by_data_quality"
        reason = "option-chain slice exists but lacks usable adjacent call marks or monotonic prices"
    return {
        "status": status,
        "supported_snapshots": supported,
        "coverage": supported / total if total else 0,
        "reason": reason,
    }


def _spot_return(previous: Dict[str, Any], current: Dict[str, Any]) -> List[Tuple[Decimal, Decimal]]:
    previous_spot = previous.get("current_spot_price")
    current_spot = current.get("current_spot_price")
    previous_time = previous.get("observed_at")
    current_time = current.get("observed_at")
    if previous_spot is None or current_spot is None or previous_spot <= ZERO or current_spot <= ZERO:
        return []
    if previous_time is None or current_time is None:
        return []
    minutes = Decimal(str((current_time - previous_time).total_seconds() / 60))
    if minutes <= ZERO:
        return []
    log_return = Decimal(str(math.log(float(current_spot / previous_spot))))
    return [(log_return, minutes / YEAR_MINUTES)]


def _annualized_realized_vol(returns: Sequence[Tuple[Decimal, Decimal]]) -> Optional[Decimal]:
    if len(returns) < 2:
        return None
    total_years = sum((dt for _, dt in returns), ZERO)
    if total_years <= ZERO:
        return None
    realized_variance = sum((ret * ret for ret, _ in returns), ZERO) / total_years
    return _clamp_sigma(Decimal(str(math.sqrt(float(realized_variance)))))


def _future_return(ordered: Sequence[Dict[str, Any]], index: int, side: str, entry_price: Decimal, horizon_seconds: int) -> Optional[Decimal]:
    observed_at = ordered[index].get("observed_at")
    if observed_at is None:
        return None
    target = observed_at.timestamp() + horizon_seconds
    for future in ordered[index + 1:]:
        future_time = future.get("observed_at")
        if future_time is not None and future_time.timestamp() >= target:
            bid = _exit_bid(future, side)
            return bid - entry_price if bid is not None else None
    return None


def _side_spread(snapshot: Dict[str, Any], side: str) -> Optional[Decimal]:
    ask = _entry_ask(snapshot, side)
    bid = _exit_bid(snapshot, side)
    if ask is None or bid is None:
        return None
    return max(ask - bid, ZERO)


def _time_to_expiry_bucket(snapshot: Dict[str, Any]) -> str:
    observed_at = snapshot.get("observed_at")
    market_end = _snapshot_market_end_time(snapshot)
    if observed_at is None or market_end is None:
        return "unknown"
    minutes = Decimal(str((market_end - observed_at).total_seconds() / 60))
    if minutes < Decimal("60"):
        return "<1h"
    if minutes < Decimal("180"):
        return "1-3h"
    if minutes < Decimal("360"):
        return "3-6h"
    return ">6h"


def _spread_bucket(spread: Optional[Decimal]) -> str:
    if spread is None:
        return "unknown"
    if spread < Decimal("0.01"):
        return "<1c"
    if spread < Decimal("0.03"):
        return "1-3c"
    if spread < Decimal("0.05"):
        return "3-5c"
    return ">=5c"


def _snapshot_market_end_time(snapshot: Dict[str, Any]) -> Optional[datetime]:
    payload = snapshot.get("payload") or {}
    if isinstance(payload, dict):
        parsed = _parse_datetime(payload.get("market_end_time"))
        if parsed is not None:
            return parsed
    return None


def _parse_datetime(raw_value: Any) -> Optional[datetime]:
    if isinstance(raw_value, datetime):
        return raw_value.astimezone(UTC) if raw_value.tzinfo is not None else raw_value.replace(tzinfo=UTC)
    if not isinstance(raw_value, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _spot_probability_proxy(spot: Optional[Decimal], reference: Optional[Decimal]) -> Optional[Decimal]:
    if spot is None or reference is None or reference <= ZERO:
        return None
    return _clamp_probability(Decimal("0.5") + ((spot - reference) / reference) * Decimal("20"))


def _clamp_probability(value: Decimal) -> Decimal:
    return min(ONE, max(ZERO, value))


def _clamp_sigma(value: Optional[Decimal]) -> Optional[Decimal]:
    if value is None or value <= ZERO:
        return None
    return min(MAX_SIGMA, max(MIN_SIGMA, value))


def _safe_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _mean(values: Iterable[Decimal], default: Decimal) -> Decimal:
    materialized = list(values)
    if not materialized:
        return default
    return sum(materialized, ZERO) / Decimal(str(len(materialized)))


def _probability_bucket(probability: Decimal) -> str:
    index = int(max(0, min(9, math.floor(float(probability) * 10))))
    return f"{index * 10}-{(index + 1) * 10}%"


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))
