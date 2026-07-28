"""Assay core for wallets, not slices.

Deliberately mirrors Edge-Factory's src/edgefactory/assay.py. Same Wilson
machinery, same grade ladder vocabulary inherited from Ma Golide's Assayer —
applied to a new object: traders instead of betting rules.

The non-negotiables:
- Wilson lower bound, never raw hit rate, for any ranking decision.
- Walk-forward only. Rank on period A, measure on period B.
- ROI alongside hit rate, always.
- Small n => UNGRADED, never inflated.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict

Z95 = 1.959963984540054
Z80 = 1.2815515655446004


def wilson_bounds(wins: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval (lower, upper) for a binomial proportion."""
    if n <= 0:
        return 0.0, 0.0
    p = wins / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return (centre - spread) / denom, (centre + spread) / denom


def wilson_lb(wins: int, n: int, z: float = Z95) -> float:
    return wilson_bounds(wins, n, z)[0]


def wilson_ub(wins: int, n: int, z: float = Z95) -> float:
    return wilson_bounds(wins, n, z)[1]


def shrunk_rate(wins: int, n: int, prior_w: int = 2, prior_n: int = 4) -> float:
    """Bayesian shrinkage toward 50%: (wins + 2) / (n + 4).

    Same form used by Ma Golide's Assayer. Pulls small-sample wallets toward
    the population mean so a 3-for-3 wallet cannot outrank a 300-trade one.
    """
    if n <= 0:
        return 0.5
    return (wins + prior_w) / (n + prior_n)


# ── grading ────────────────────────────────────────────────────────────
# Vocabulary inherited from Ma Golide. Thresholds are on the Wilson LB of the
# wallet's resolved-win rate, NOT the raw rate.

GRADES = [
    (0.80, "PLATINUM"),
    (0.70, "GOLD"),
    (0.60, "SILVER"),
    (0.52, "BRONZE"),
    (0.45, "COPPER"),
]


def grade(wins: int, n: int, min_n: int = 30) -> str:
    """Grade a wallet by its Wilson lower bound. Small n => UNGRADED.

    NOTE the deliberate divergence from Ma Golide's classify_tier(), which
    returned ROBBER for BOTH "n < 10" and "win_rate < 0.50" — collapsing
    "insufficient evidence" and "reliably bad" into one label. That bug is
    recorded in the Slipstream handover. Here they are distinct: UNGRADED
    means unknown, CHARCOAL means known-bad.
    """
    if n < min_n:
        return "UNGRADED"
    lb = wilson_lb(wins, n)
    for threshold, name in GRADES:
        if lb >= threshold:
            return name
    return "CHARCOAL"


# ── wallet scorecard ───────────────────────────────────────────────────


@dataclass
class WalletScore:
    wallet: str
    n_trades: int
    n_markets: int
    wins: int
    win_rate: float
    wilson_lb: float
    shrunk: float
    roi: float
    staked: float
    pnl: float
    grade: str

    def to_dict(self) -> dict:
        return asdict(self)


def score_wallet(wallet: str, positions: list[dict], min_n: int = 30) -> WalletScore:
    """Score one wallet from its RESOLVED positions.

    Each position dict needs: cost (USDC staked), payout (USDC returned),
    won (bool), slug (market identity).

    ROI is payout-minus-cost over cost — the only number that matters. Hit
    rate alone is not a betting claim (Racket-Factory doctrine: "Do not judge
    the system by raw win rate alone").
    """
    n = len(positions)
    if n == 0:
        return WalletScore(wallet, 0, 0, 0, 0.0, 0.0, 0.5, 0.0, 0.0, 0.0, "UNGRADED")

    wins = sum(1 for p in positions if p["won"])
    staked = sum(float(p["cost"]) for p in positions)
    returned = sum(float(p["payout"]) for p in positions)
    pnl = returned - staked
    roi = (pnl / staked) if staked > 0 else 0.0
    markets = len({p["slug"] for p in positions})

    return WalletScore(
        wallet=wallet,
        n_trades=n,
        n_markets=markets,
        wins=wins,
        win_rate=wins / n,
        wilson_lb=wilson_lb(wins, n),
        shrunk=shrunk_rate(wins, n),
        roi=roi,
        staked=staked,
        pnl=pnl,
        grade=grade(wins, n, min_n=min_n),
    )
