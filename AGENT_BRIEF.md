# Slipstream — Agent Brief

**Read `HANDOVER.md` in full before writing a single line. It is the single
source of truth and it contains findings that will cost you days if ignored.**

You are picking up a research lab at skeleton stage. The skeleton is built,
tested and green. Your job is the next three tasks, in order, and then STOP.

---

## 0. Ground rules (non-negotiable, inherited from four prior repos)

1. **This project can be cancelled by its own next result.** Task 3 is a
   falsification test. If it fails, the correct action is to write that down
   and stop — not to loosen the gate until it passes.
2. **Wilson lower bound, never raw hit rate**, for any ranking decision.
3. **Walk-forward only.** Rank on period A, measure on period B. Never score
   and rank on the same rows.
4. **ROI alongside hit rate, always.** A wallet can win 75% of its bets and
   lose money. There is a unit test asserting exactly this.
5. **Small n => UNGRADED, never inflated.** "Unknown" and "reliably bad" are
   different labels. A prior repo collapsed them and it caused real damage.
6. **No new helper scripts, validators, reports or docs** beyond the three
   deliverables below. Use throwaway shell one-liners for diagnostics.
7. **No capital. No wallet key. No execution code.** Every endpoint needed is
   public and unauthenticated. If you find yourself needing a key, you have
   drifted.
8. **Do not commit `localdata/`.** It is gitignored except `.gitkeep`.
9. Update `HANDOVER.md` in place when you finish. Do not create new planning
   documents.

### Verify the skeleton before you start

```bash
pip install -r requirements.txt
PYTHONPATH=src python3 -m pytest tests/ -q          # expect: 11 passed
PYTHONPATH=src python3 scripts/probe_polymarket.py  # expect: 6/6 checks passed
```

If either fails, fix that first and report it. Do not build on a red base.

---

## TASK 1 — Establish the usable-history boundary

**Why:** `HANDOVER.md` records a measured finding — Gamma's default market
ordering returns 2020-era markets whose `outcomePrices` have degraded to
`["0","0"]` or to floats like `1.01e-6`. Resolution truth is **not
recoverable** for those. Measured 2026-07-28:

```
gamma default order          n=40  resolvable=0   all-zero=23  fractional=17
gamma order=endDate desc     n=40  resolvable=40  all-zero=0   fractional=0
```

You cannot place a walk-forward split earlier than the boundary, because
wallets would be scored against unrecoverable outcomes and the output would be
confident garbage.

**Deliverable:** `scripts/find_history_boundary.py`

**Behaviour:**
- Page through closed markets ordered by `endDate` descending
  (`fetch_markets(closed=True, recent_first=True, offset=...)`).
- Bucket every market by `endDate` month.
- Per month compute: `n_markets`, `n_resolvable` (via `resolution_of()`),
  `pct_resolvable`.
- Walk backwards in time; the boundary is the **oldest month where
  `pct_resolvable >= 0.95`** and every month newer than it also clears 0.95.
- Stop paging after 5,000 markets or when you reach 2020, whichever is first.

**Output:** `localdata/history_boundary.json`

```json
{
  "generated_at_utc": "...",
  "boundary_month": "YYYY-MM",
  "recommended_min_date": "YYYY-MM-01",
  "markets_scanned": 0,
  "by_month": [
    {"month": "YYYY-MM", "n": 0, "resolvable": 0, "pct": 0.0}
  ]
}
```

Also print a readable table to stdout.

**Acceptance:**
- Script runs clean with `PYTHONPATH=src`.
- JSON written and valid.
- `recommended_min_date` is a real date, not a guess.
- You report the boundary in your summary.

---

## TASK 2 — Reconstruct resolved positions per wallet

**Why:** `assay.score_wallet()` already exists and is tested, but it consumes
`positions`, not raw trades. Nothing currently builds them. This is the core
primitive and the only genuinely subtle code in the project.

**Deliverable:** add to `src/slipstream/positions.py` (new module)

```python
def build_positions(trades: list[dict], resolutions: dict[str, int]) -> list[dict]:
    """trades: raw rows from fetch_trades / fetch_wallet_history
       resolutions: {conditionId: winning_outcome_index}
       returns: [{slug, conditionId, outcomeIndex, shares, cost, payout, won}]
    """
```

**The netting rule — implement exactly this, do not improvise:**

1. Group trades by `(conditionId, outcomeIndex)`.
2. For each group:
   - `buy_shares  = sum(size) where side == "BUY"`
   - `sell_shares = sum(size) where side == "SELL"`
   - `buy_cost    = sum(size * price) where side == "BUY"`
   - `sell_proceeds = sum(size * price) where side == "SELL"`
   - `net_shares = buy_shares - sell_shares`
   - `cost = buy_cost - sell_proceeds`
3. **Skip the group entirely** if `net_shares <= 0` (flat or net short —
   ambiguous to settle from public data alone; record the count of skips).
4. **Skip** if `conditionId` is not in `resolutions` (unresolved market).
5. `won = (outcomeIndex == resolutions[conditionId])`
6. `payout = net_shares if won else 0.0`  (each winning share pays $1)
7. **Skip** if `cost <= 0` (free/negative basis breaks ROI; count it).

**Return a second value**: a dict of skip counts by reason. Do not silently
drop rows. Every exclusion must be countable and reported.

**Also add** `resolutions_for(markets: list[dict]) -> dict[str, int]` that maps
`conditionId -> winning index` using the existing `resolution_of()`.

**Deliverable:** `tests/test_positions.py` with, at minimum:
- a simple winning buy → `payout == shares`, `won is True`
- a simple losing buy → `payout == 0`, `won is False`
- buy-then-partial-sell → `net_shares` and `cost` both reduced correctly
- buy-then-full-sell → skipped, counted under the flat/short reason
- unresolved market → skipped, counted
- the skip-count dict sums to the number of excluded groups

**Acceptance:**
- All new tests pass. Existing 11 still pass. `pytest -q` shows 17+ passed.
- No network access in tests.

---

## TASK 3 — The falsification test (this can kill the project)

**Why:** open question 2 in `HANDOVER.md`. *Does a persistently skilled wallet
cohort exist?* If wallet ROI is not autocorrelated across time — if this
period's winners are random relative to last period's — the entire Slipstream
thesis is dead and the correct outcome is to stop.

**Deliverable:** `scripts/test_persistence.py`

**Behaviour:**

1. **Sample the wallet universe.** Page `fetch_trades(limit=500, offset=...)`
   over the public feed until you have collected at least `--min-wallets`
   distinct `proxyWallet` values (default 300). Record how many pages it took.
2. **Fetch resolution truth.** Page closed markets (recent-first, respecting
   Task 1's boundary) and build the `conditionId -> winner` map.
3. **Split.** `--split YYYY-MM-DD`, default from `GATES.split_date`, but it
   MUST be >= `recommended_min_date` from Task 1. Refuse to run and exit 1 if
   it is earlier — print why.
4. **Per wallet**, fetch history, build positions, and split them by trade
   timestamp into period A (before split) and period B (on/after).
5. **Score** each wallet separately on A and on B with `score_wallet()`.
6. **Rank on A only.** Eligible = `n_trades >= GATES.min_trades_rank` AND
   `n_markets >= GATES.min_markets`. Sort by `wilson_lb` descending. Take
   `GATES.cohort_top_n`.
7. **Measure on B.** Compare, for wallets with `n_trades >= min_trades_test`
   in B:
   - `cohort_roi_B`  = stake-weighted ROI of the top cohort in period B
   - `population_roi_B` = stake-weighted ROI of ALL eligible wallets in B
   - `edge = cohort_roi_B - population_roi_B`
8. **Verdict:**
   - `edge >= GATES.min_cohort_edge` → `THESIS SUPPORTED`
   - `0 <= edge < min_cohort_edge` → `WEAK / INCONCLUSIVE`
   - `edge < 0` → `THESIS REJECTED`
9. **Also report a null baseline.** Shuffle the A-period ranking randomly,
   take the same cohort size, and compute its B edge. Do this 20 times and
   report mean and standard deviation. **If the real edge is inside one
   standard deviation of the shuffled edge, the result is noise regardless of
   sign — say so explicitly in the verdict line.**

**Output:** `localdata/persistence_report.json` plus a readable stdout summary
containing at minimum: wallets sampled, wallets eligible in A, cohort size,
`cohort_roi_B`, `population_roi_B`, `edge`, shuffled mean/sd, and the verdict.

**Acceptance:**
- Runs end to end without auth.
- Prints one of the three verdicts plus the noise caveat.
- JSON written.
- **You report the actual numbers in your summary, whatever they are.**

---

## What to do with the result

- **THESIS REJECTED or noise-indistinguishable** → append the finding to
  `HANDOVER.md`, state plainly that Slipstream stops here, and do not build
  the capture layer. This is a successful outcome. A prior repo
  (Racket-Factory) cost three weeks to reach an equivalent negative result;
  reaching it in an afternoon is the whole point of this sequencing.
- **WEAK / INCONCLUSIVE** → record it, propose (do not build) the smallest
  next measurement that would disambiguate.
- **THESIS SUPPORTED** → record it, and note the next open question: *is the
  signal actionable after latency?* A smart wallet's trade is public only
  after it executes; if price has already moved, the information is worthless.
  Do not build the follower until that is measured.

---

## Do NOT build (explicitly out of scope)

- Book snapshot recorder / capture loop. It is needed eventually for the maker
  thesis, but `/orderbook-history` being dead means it only ever records
  forward — there is no point starting it before the thesis is validated.
- Any execution, order placement, or wallet-auth code.
- A dashboard, a WhatsApp notifier, a Supabase sync, a CI workflow.
- Kalshi support. Kalshi has no public per-trade attribution; it cannot
  support this thesis at all. This is settled in `HANDOVER.md`.

---

## Known traps

- **The resolution-era boundary** (Task 1). Gamma's default ordering silently
  hands you unusable 2020 data. A spot-check on the recent subset will look
  perfect and mislead you. This exact mistake was already made once during the
  skeleton build and caught by the probe.
- **Sign conventions.** In a prior repo a metric was read with the wrong sign
  and nearly caused a "fix" that would have blocked the best executions.
  Before trusting any bps/ROI figure, verify the sign on a case you can
  compute by hand.
- **Selection bias in the wallet sample.** The public `/trades` feed is
  ordered by recency, so sampling it favours currently-active wallets — which
  is itself a survivorship filter. Note this in the report; do not pretend the
  sample is random.
- **`size` vs `cost`.** `size` is shares. A share pays $1 on resolution. Cost
  is `size * price`. Getting this backwards inverts every ROI in the project.
