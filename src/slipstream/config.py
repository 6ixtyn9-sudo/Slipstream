"""Slipstream gates. These numbers are the law — no wallet gets ranked
"skilled" without clearing every one of them out of sample.

Doctrine inherited from Edge-Factory and Price:
- Wilson lower bound, never raw hit rate, for any ranking decision.
- Walk-forward only. Rank on period A, measure on period B.
- ROI alongside hit rate, always.
- Small n => UNGRADED, never inflated.
"""
from __future__ import annotations

from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# ── Polymarket API bases (all public, no auth needed for research) ──
GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
DATA_BASE = "https://data-api.polymarket.com"

# Polite rate limiting. Same doctrine as Price/Edge-Factory: never hammer a
# free public endpoint.
REQUEST_DELAY_SEC = 0.35
REQUEST_TIMEOUT_SEC = 30
MAX_RETRIES = 3


@dataclass(frozen=True)
class Gates:
    """Thresholds for calling a wallet 'skilled'."""

    # Sample floors. A wallet with 12 trades at +40% is not skilled, it is
    # lucky. This is the same problem as slice ranking with small n.
    min_trades_rank: int = 30      # min trades in the ranking window
    min_trades_test: int = 15      # min trades in the out-of-sample window
    min_markets: int = 5           # must not be one market repeated

    # Skill thresholds, applied to the Wilson LB of resolved-win rate.
    min_wilson_lb: float = 0.52    # beat a coinflip with confidence
    min_roi: float = 0.00          # must be profitable, not merely accurate

    # Walk-forward. Rank on everything before the split; test after it.
    # NOTE: set per-run from CLI; this is the default only.
    split_date: str = "2026-06-01"

    # Autocorrelation test (open question 2). If the top cohort from period A
    # does not outperform the population in period B by at least this margin,
    # the Slipstream thesis is dead.
    cohort_top_n: int = 50
    min_cohort_edge: float = 0.02  # 2pp ROI over population baseline


GATES = Gates()

# Resolution truth. Gamma `outcomePrices` on a closed market resolves to
# ["0","1"] or ["1","0"]. Verified 2026-07-28: 20/20 recently-closed markets
# were resolvable. Anything else is treated as unresolved and EXCLUDED from
# scoring rather than guessed at.
RESOLVED_PRICES = {"0", "1", "0.0", "1.0"}

# Markets to exclude from skill scoring entirely. Resolution risk is a loss
# channel with no analogue in any prior repo (see HANDOVER constraint 4):
# oracle-judgement markets can resolve against a correct read of the world.
# Keep the filter explicit and auditable rather than silently dropping rows.
EXCLUDE_SLUG_PATTERNS: tuple[str, ...] = (
    "jesus",
    "alien",
    "god-",
)
