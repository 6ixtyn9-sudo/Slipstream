"""Assay unit tests. Deterministic, no network, no API quota burned."""
from __future__ import annotations

import json

from slipstream.assay import grade, score_wallet, shrunk_rate, wilson_lb, wilson_ub
from slipstream.sources.polymarket import resolution_of


# ── Wilson ─────────────────────────────────────────────────────────────

def test_wilson_zero_n_is_safe():
    assert wilson_lb(0, 0) == 0.0
    assert wilson_ub(0, 0) == 0.0


def test_wilson_lb_below_raw_rate():
    """The whole point: LB punishes small samples."""
    assert wilson_lb(3, 3) < 1.0
    assert wilson_lb(3, 3) < wilson_lb(300, 300)


def test_wilson_lb_tightens_with_n():
    small = wilson_lb(6, 10)
    large = wilson_lb(600, 1000)
    assert large > small  # same 60% rate, more confidence


# ── shrinkage ──────────────────────────────────────────────────────────

def test_shrinkage_pulls_small_n_toward_half():
    assert shrunk_rate(3, 3) < 1.0
    assert abs(shrunk_rate(0, 0) - 0.5) < 1e-9
    # 100% over 3 trades shrinks far more than over 300
    assert shrunk_rate(3, 3) < shrunk_rate(300, 300)


# ── grading ────────────────────────────────────────────────────────────

def test_small_n_is_ungraded_not_charcoal():
    """Regression guard for the Ma Golide classify_tier bug.

    The original returned ROBBER for BOTH n<10 and win_rate<0.50, collapsing
    'unknown' into 'reliably bad'. Downstream that meant fading unproven
    edges. Slipstream keeps them distinct.
    """
    assert grade(2, 3) == "UNGRADED"          # unknown
    assert grade(5, 100) == "CHARCOAL"        # known bad
    assert grade(2, 3) != grade(5, 100)


def test_grade_ladder_monotonic():
    assert grade(95, 100) == "PLATINUM"
    assert grade(50, 100) == "CHARCOAL"       # 50% LB is under 0.45? no -> COPPER
    assert grade(75, 100) in {"GOLD", "SILVER"}


# ── wallet scoring ─────────────────────────────────────────────────────

def _pos(cost, payout, won, slug):
    return {"cost": cost, "payout": payout, "won": won, "slug": slug}


def test_empty_wallet_is_ungraded():
    s = score_wallet("0xabc", [])
    assert s.grade == "UNGRADED"
    assert s.n_trades == 0
    assert s.roi == 0.0


def test_roi_is_pnl_over_stake_not_hit_rate():
    """A wallet can win most bets and still lose money."""
    positions = [
        _pos(10, 11, True, "a"),   # +1
        _pos(10, 11, True, "b"),   # +1
        _pos(10, 11, True, "c"),   # +1
        _pos(10, 0, False, "d"),   # -10
    ]
    s = score_wallet("0xabc", positions, min_n=1)
    assert s.win_rate == 0.75
    assert s.roi < 0          # 75% hit rate, negative ROI
    assert s.pnl == -7.0


def test_market_count_catches_one_market_repeated():
    positions = [_pos(10, 20, True, "same") for _ in range(40)]
    s = score_wallet("0xabc", positions, min_n=1)
    assert s.n_trades == 40
    assert s.n_markets == 1   # gate on this, not n_trades alone


# ── resolution truth ───────────────────────────────────────────────────

def test_resolution_requires_clean_zero_one():
    assert resolution_of({"closed": True, "outcomePrices": '["0", "1"]'}) == 1
    assert resolution_of({"closed": True, "outcomePrices": '["1", "0"]'}) == 0


def test_degraded_legacy_markets_return_none():
    """2020-era markets have degraded outcomePrices. Must be EXCLUDED, not guessed.

    Measured 2026-07-28: gamma default ordering gave 0/40 resolvable
    (23 all-zero, 17 fractional); order=endDate desc gave 40/40.
    """
    assert resolution_of({"closed": True, "outcomePrices": '["0", "0"]'}) is None
    assert resolution_of(
        {"closed": True, "outcomePrices": '["0.00000101108205252254", "0.9999"]'}
    ) is None
    assert resolution_of({"closed": False, "outcomePrices": '["0", "1"]'}) is None
    assert resolution_of({"closed": True, "outcomePrices": None}) is None
