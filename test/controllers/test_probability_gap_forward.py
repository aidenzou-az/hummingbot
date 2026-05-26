from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest import TestCase

from controllers.generic.probability_gap_forward import estimate_forward_basis


class ProbabilityGapForwardTest(TestCase):
    def test_delivery_future_has_precedence_when_close_to_market_end(self):
        now = datetime(2026, 5, 9, 8, 0, tzinfo=UTC)
        market_end = now + timedelta(hours=8)

        estimate = estimate_forward_basis(
            now=now,
            market_end_time=market_end,
            spot_price=Decimal("100000"),
            perp_mark_price=Decimal("100050"),
            delivery_candidates=[
                {
                    "symbol": "BTCUSD_260509",
                    "delivery_time": market_end + timedelta(minutes=30),
                    "price": Decimal("100120"),
                },
                {
                    "symbol": "BTCUSD_260626",
                    "delivery_time": market_end + timedelta(days=48),
                    "price": Decimal("101000"),
                },
            ],
        )

        self.assertEqual("delivery_futures", estimate.source)
        self.assertEqual("BTCUSD_260509", estimate.delivery_symbol)
        self.assertEqual(Decimal("100120"), estimate.estimated_forward_price)
        self.assertGreater(estimate.basis_annualized, Decimal("0"))

    def test_perp_mark_is_used_when_delivery_is_missing(self):
        now = datetime(2026, 5, 9, 8, 0, tzinfo=UTC)

        estimate = estimate_forward_basis(
            now=now,
            market_end_time=now + timedelta(hours=8),
            spot_price=Decimal("100000"),
            perp_mark_price=Decimal("99980"),
            perp_index_price=Decimal("99990"),
            perp_last_funding_rate=Decimal("0.0001"),
            perp_next_funding_time=now + timedelta(hours=1),
        )

        self.assertEqual("perp_mark", estimate.source)
        self.assertEqual(Decimal("99980"), estimate.estimated_forward_price)
        self.assertEqual(Decimal("99990"), estimate.perp_index_price)
        self.assertLess(estimate.basis_annualized, Decimal("0"))

    def test_spot_fallback_is_explicitly_degraded(self):
        now = datetime(2026, 5, 9, 8, 0, tzinfo=UTC)

        estimate = estimate_forward_basis(
            now=now,
            market_end_time=now + timedelta(hours=8),
            spot_price=Decimal("100000"),
        )

        self.assertEqual("spot_fallback", estimate.source)
        self.assertEqual(Decimal("100000"), estimate.estimated_forward_price)
        self.assertEqual(Decimal("0"), estimate.basis_annualized)
        self.assertEqual("missing_delivery_and_perp_forward_inputs", estimate.reason)
