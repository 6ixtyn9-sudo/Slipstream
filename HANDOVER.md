# Slipstream — Handover

Date: 2026-07-28
Status: **DISCUSSION ONLY. No code written. No capital committed. Repo created 2026-07-28 (README + LICENSE + this file only).**
Purpose: prediction-market research lab. Rank *traders*, not outcomes.

---

## Single source of truth

This file is the handover. Update it in place. Do not create drifting build
reports or planning documents. Same convention as Price, Edge-Factory and
Racket-Factory.

---

## Name

**Slipstream** — you ride behind someone faster and get pulled along.

Naming convention across the portfolio: `*-Factory` = production pipeline
(Edge, Racket). Plain noun = research lab (Price). Slipstream is a research
lab, so plain noun. Alternatives considered and rejected: Prospector (keeps
Ma Golide metallurgy lineage, but overlaps Assayer), Wake, Ledger.

---

## The thesis

Every prior system in this portfolio — Gold Universe, Edge-Factory,
Racket-Factory, Price — asks the same question: **what will happen?** Each one
acquires messy external data, normalises it, computes descriptive features,
discovers slices, validates with Wilson LB / walk-forward, and emits picks.
Four builds of the same architecture. The operator is good at it now.

Slipstream asks a different question: **who already knows what will happen?**

Polymarket attaches a `proxyWallet` address to every public trade. That field
does not exist on any sportsbook, anywhere. It means a trader's entire history
is reconstructable: what they bought, at what price, in what size, when — and
whether they were right. Traders can therefore be ranked the same way slices
are ranked today, using the *same* Wilson LB + shrinkage machinery already
trusted in Edge-Factory and Price, applied to a new object.

Secondary thesis (operator's own framing, and the stronger version): **wallet
signal and consensus signal are the same question from opposite ends.** One is
revealed behaviour, the other is independent information. If a wallet ranked
smart takes a position AND Edge-Factory's 12-source consensus independently
agrees, that is confluence from two uncorrelated sources. Either alone is weak.
Together is not. Nobody else can run this combination because it requires
already owning a consensus engine — which Edge-Factory is.

---

## Why not the obvious alternatives

Operator explicitly rejected two framings on 2026-07-28:

- **(a) Same game, cheaper venue** — port Edge-Factory soccer picks to
  Polymarket to avoid the sportsbook overround. Rejected: *"won't teach me new
  things."* Correct — it is execution relocation, not new capability.
- **(b) New forecasting domain** — politics, weather, economics. Rejected:
  *"would introduce the same weaknesses I already have."* Correct — it rebuilds
  the source-acquisition pipeline in a domain with no consensus ecosystem,
  which is exactly what killed Racket-Factory.

Wallet-ranking is neither. The difficulty moves from data acquisition (a solved
problem here — clean JSON, no scraping) to **microstructure and attribution**,
which no prior repo has touched.

---

## Verified API surface (all checked live 2026-07-28, zero auth)

| API | endpoint | verified result |
|---|---|---|
| Gamma | `gamma-api.polymarket.com/markets` | question, slug, volume, liquidity, endDate, clobTokenIds, conditionId, outcomePrices |
| CLOB | `clob.polymarket.com/book?token_id=` | full depth both sides, tick size, min order size |
| CLOB | `/prices-history?market=<token>` | 708 hourly points on the market tested |
| CLOB | `/markets`, `/sampling-markets` | 1000/page paginated; `/sampling-markets` = reward-eligible only, carries `rewards{rates,min_size,max_spread}` |
| Data | `data-api.polymarket.com/trades` | **`proxyWallet`, side, size, price, timestamp, conditionId, slug, outcome, outcomeIndex, transactionHash** |

**Wallet history is paginated and works.** `?user=<addr>&limit=500&offset=N`
returned a full 500 rows at offset 0 and another 500 at offset 500 for a
randomly sampled wallet. That wallet's most recent 500 trades spanned
2026-07-23 → 2026-07-28, i.e. ~100 trades/day for an active account.

**Resolution truth is available.** `outcomePrices` on closed Gamma markets
resolves to `["0","1"]` or `["1","0"]`. Checked 20 most-recently-closed
markets: **20/20 resolvable, 0 unusable.** This is what makes wallet PnL
reconstructable — trades give entry price and size, `outcomePrices` gives the
payoff.

Trading (not needed for research) uses `py-clob-client`, wallet-based auth from
a Polygon private key, USDC on Polygon with token allowances. Same shape as
Alpaca. Read is free; only order placement needs credentials.

---

## Known constraints — read before building anything

### 1. `/orderbook-history` is DEAD (hard blocker for maker research)

The undocumented CLOB `/orderbook-history` endpoint **stopped producing new
snapshots around 2026-02-20 20:00 UTC** and returns `{"count":0,"data":[]}` for
any window after that. Platform-wide, confirmed across multiple high-volume
markets. Pre-cutoff history still retrievable. Believed related to the
Dome/domeapi.io → Predexon transition.

Consequence: **you cannot backtest limit-order fills from history.** Price
history tells you the price touched 0.42; it does not tell you whether your
resting order at 0.42 filled, or how much size was ahead of you in the queue.

This is the *exact* failure mode found in Price on 2026-07-28: a 38% expired
rate on entry limit orders that nobody had measured, biasing every realized
result toward retracement. Do not repeat it. **If maker viability is ever to be
assessed, book snapshots must be recorded forward, starting from day one.**

Wallet-ranking research does NOT hit this constraint — trade history is
complete and public. That is another point in its favour as the first workstream.

### 2. Liquidity is bimodal — the headline "tight spreads" is misleading

Measured live 2026-07-28:

    Jesus/GTA VI market       114,328 shares at touch   spread 2.0% of mid
    Brann v Cluj draw            938 / 1,403 shares     spread 4.9% of mid
    Liaoning Tieren FC win        $3 bid / $554 ask     spread 3.8% of mid
    Tecnico/Manta O/U corners     $1 bid / $55 ask      spread 196% of mid

Taker fee is ~2%. **On thin markets the spread is 4-5% — worse than the tennis
overround (-8.9%) already rejected in Racket-Factory.** "Polymarket is cheaper
than a sportsbook" is true only for liquid markets. The novelty/politics markets
are liquid; the obscure sports markets are not.

### 3. Soccer inventory does not match Edge-Factory coverage

Of the top 100 active markets by volume, 22 matched a soccer-ish keyword — but
the actual inventory was Taiwanese baseball, CS:GO map handicaps, table tennis,
and Ecuadorian corner totals. Genuine European football: **one market** (Brann
v Cluj, $998 volume).

Category mix of top 300 by volume: other 55, sports 26, politics 11, econ 5,
crypto 3.

Edge-Factory's 12 sources cover mainstream leagues. The overlap between
"markets Edge-Factory can price" and "markets Polymarket lists with real depth"
is currently close to empty. **Any consensus-confluence work must first measure
this overlap, not assume it.**

### 4. Resolution risk is a loss channel with no prior vocabulary

Sports settle mechanically. "Will Jesus Christ return before GTA VI" settles by
human judgement via UMA's oracle. Ambiguous wording, disputed resolutions and
oracle games are real and have no analogue in Gold Universe, Edge-Factory,
Racket-Factory or Price. Existing validation discipline can measure edge decay;
it has no way to measure "the oracle read the question differently than I did."

Operator instinct on 2026-07-28 was to avoid such markets. That instinct is
correct and should become an explicit filter: **only markets with (i) an
independent probability estimate available and (ii) mechanical resolution.**

### 5. Gamma `limit` silently capped at 100; offset ceiling ~2100

Measured 2026-07-29. Gamma returns 100 rows regardless of the `limit` param:

    limit=100   → 100 rows
    limit=500   → 100 rows  (silently capped — looks correct but is not)
    limit=1000  → 100 rows

Original code paged with `limit=500, offset += 500`. Because each call only
returned 100 rows, **every page skipped 400 markets** — yielding 100 unique
markets per 500-offset step. Five steps × 100 = 500 markets, which looked like
an API ceiling but was a paging bug.

Correct paging: `limit=100, offset += len(batch)` (stride = actual rows
returned). With correct stride, the offset ceiling is ~2100:

    offset  100 → 100 markets
    offset  200 → 100 markets
    ...
    offset 2100 → HTTP 422
    ──────────────────────────
    TOTAL: ~2,100 reachable closed markets (4.2× the buggy count)

**The "500-market cap" in the original smoke-test finding was a paging bug.**
The corrected stride is in both `find_history_boundary.py` and
`test_persistence.py`. The 42.3% unresolved rate and `eligible_A: 0` from the
first smoke-test must be re-evaluated with the fixed paging.

Inverted sampling (`/trades?market=<conditionId>`) remains a documented
fallback. Verified live 2026-07-29 that `?market=` correctly filters to one
conditionId's trades. Do not build until a re-run with correct paging
confirms 2,100 markets is still insufficient.


---

## Capital — researched, not committed

Live reward parameters pulled from `/sampling-markets` on 2026-07-28:

    min_order_size (to place any order):     5 shares
    reward min_size (to earn):               20-50 shares
    max_spread (reward qualifying band):     4.5-5.5 cents
    daily reward pool (small markets):       $2-5

Two-sided quoting at 20 shares / 50c = **~$20 USDC** to qualify on one small
market. Scoring is `((max_spread - order_spread)/max_spread)^2 * size`, and
payout is your share of that market's daily pool. Two-sided is near-mandatory:
base score is `Q_min` (the minimum across your two sides), and one-sided
quoting while mid is 0.10-0.90 divides score by 3.

Qualifying is not earning. On a $3/day pool against $20k of competing size:

    your size    40  ->  0.2% of pool  =  $0.006/day
    your size 1,000  ->  4.8% of pool  =  $0.143/day
    your size 5,000  -> 20.0% of pool  =  $0.600/day

**The real cost of market making is adverse selection, not fees.** A resting
order is a live bet. Quoting both sides means getting filled on the wrong side
precisely when someone informed hits you. The reward pool is compensation for
bearing that risk, not free yield.

Indicative sizing if this is ever pursued: **$50-100** = real learning capital,
enough to feel adverse selection with money that does not matter. $1,000-5,000
= matters on mid-tier pools but premature before inventory management is
proven. $10k+ = competitive and completely premature.

Unverified but interesting: one source claims **fewer than 2% of active
Polymarket wallets have ever earned more than $1 providing liquidity**, and
there is an unresolved $POLY airdrop where LP activity may weigh heavily. Treat
as a hypothesis to check, not a fact.

---

## Venue: Polymarket vs Kalshi

Kalshi is accessible from South Africa (not on the restricted list), but with
no local licensing, and some users report access failures despite eligibility.

| | Polymarket | Kalshi |
|---|---|---|
| maker economics | 0% + 20-50% rebate share + daily liquidity pools | 0% on most markets, **no published rebate** |
| taker at 50c | ~1.56 / 100 | ~1.75 / 100 |
| liquidity | deep on top markets | low on most, wider spreads |
| KYC | none | government ID |
| ZA funding | USDC on Polygon | debit/wire/crypto; no ACH for international |
| idle cash | 0% | ~4% APY |
| regulation | unregulated | CFTC-regulated DCM |
| trade attribution | **`proxyWallet` on every trade** | **none — no equivalent** |

**Kalshi cannot support the Slipstream thesis at all.** There is no public
per-trader attribution. It is also strictly worse for the maker thesis (no
structural maker incentive). Its advantages are legitimacy, USD rails and 4% on
idle balance — none of which matter for research.

**Decision: Polymarket. Not because it is better in general, but because the
`proxyWallet` field is the entire premise.**

---

## Open questions — to settle by discussion, before any code

1. **Which edge source?** Three genuinely different projects, wanting different
   data, code and venues:
   - (a) predict outcomes better — needs consensus sources
   - (b) earn spread / manage inventory — needs liquid markets + reward pools,
     subject matter irrelevant
   - (c) rank wallets, follow smart money — needs on-chain attribution,
     Polymarket-only
   Picking two is how projects stall. Current lean: **(c)**, because it is free
   to research, needs no capital, uses existing machinery on a new object, and
   naturally feeds (a) and (b) later.
2. **Does a persistently skilled wallet cohort actually exist?** The whole
   thesis dies if wallet ROI is not autocorrelated across time. This is the
   first thing to measure and it is measurable entirely from free public data.
3. **Is skill distinguishable from size/luck?** A wallet with 1000 trades at
   +2% is different from one with 12 trades at +40%. This is precisely what
   Wilson LB + shrinkage exists to separate — same problem as slice ranking
   with small n.
4. **Is the signal actionable after latency?** A smart wallet's trade is public
   only after it executes. If the price has already moved, the information is
   worthless. Must measure: price impact in the N minutes following a
   smart-wallet fill.
5. **What is the Edge-Factory / Polymarket market overlap?** Measure it; do not
   assume it. See constraint 3.

---

## Anti-drift rules (inherited, and they apply here)

- No code until the thesis question is settled. This document is discussion
  output, not a build plan.
- Do not create helper scripts, validators or extra docs unless explicitly
  asked.
- Measurement > code change. The Price session on 2026-07-28 shipped exactly
  one behavioural change and discarded two proposed changes that were built on
  a sign error and an n=2 sample. That ratio is healthy.
- Findings at small n get logged for re-testing, not acted on.
- **If fills matter to a strategy, measure fills first.** Non-negotiable, and
  learned the expensive way in Price.

---

## Operator context (2026-07-28)

- Concurrent projects: **Tender Getter RSA** (90k LOC in 3 weeks, approaching
  beta, XPRIZE deadline ~4 weeks out but operator explicitly not pressed —
  substantial RSA funding alternatives exist; currently blocked on a business
  SIM/number). **Price** (9 hours from its first clean discovery run after the
  merge-race fix). Edge-Factory (live, breaking even). Racket-Factory and Gold
  Universe (dormant, with findings recorded).
- Operator works at full speed by preference and defends it: *"better to find
  out quick that something doesn't work than to find out later."* Racket-Factory
  cost 3 weeks and produced a definitive answer (top-tier tennis is efficient,
  -8.9% blind ROI, n=13,150). That is cheap for a real result. The historical
  failure mode is not speed — it is starting the next thing before the last one
  produced evidence. The HANDOVER convention exists to fix exactly that, and it
  is working.
- Operator has a funded Polymarket account already.

---

## Next step

**Continue the discussion.** Specifically: settle open question 1 (which edge
source), then 2 (does a skilled cohort persist). Question 2 is answerable from
free public data with no capital and no repo — a single throwaway analysis
against `/trades` + `outcomePrices` would either validate or kill the thesis
before anything is built.

The repo now exists, which changes nothing about the sequencing: do not write
capture or strategy code until question 2 has an answer. An empty repo is a
placeholder, not a commitment.

---


## Task 3 — Falsification test: THESIS UNTESTABLE ON CURRENT DATA

**Result: 0.0% coverage.** 
A pure measurement of 20 wallets, 17,610 trades yielded 0 resolved positions. 
Confirmed on a wider sample: of the 120 most-traded markets from 2,000 recent trades:
- 116 still open (97%) — of these, 23 are priced at extremes (>=0.99) and settled in substance.
- 4 not found in Gamma (3%)
- **0 closed + resolvable (0%)**

**Mechanism:** 
Resolvable markets have a median age of **84 days** since resolution (only 6/100 resolved in the last 7 days). Gamma lags settlement by weeks-to-months. 
Meanwhile, the `/trades` feed only reaches back ~4 minutes. 

The observable window (trades today) and the scoreable window (Gamma resolution 3 months later) never overlap. Nothing you sample today can be scored today, and nothing scoreable today can be sampled anymore.

**Verdict: THESIS UNTESTABLE ON CURRENT DATA**
This is an instrument limitation, not a finding about wallet skill. 
The thesis isn't disproven, but testing it needs a capture-forward warehouse running for three months before it can answer anything. First real answer would be ~Q4 2026.

STOP. No capture layer, no gate loosening, no inverted sampling.

---

### Trap 4: ordering ≠ relevance — verify sample intersection before measuring

Three times in one session (2026-07-28/29) a plausible-looking sort order
produced a sample that didn't intersect the population being studied:

1. **`endDate` vs `closedTime`** (Task 1) — sorting closed markets by `endDate`
   desc surfaced future-dated markets that had already closed early. Boundary
   scan returned 3 months of fake-future data.
2. **Paging stride** (constraint 5) — `limit=500` returned 100 rows; using 500
   as the stride skipped 400 markets per page. "500-market cap" was a bug.
3. **`order=endDate` for the resolution map** (Task 3) — building the map from
   Gamma sorted by `endDate` returns novelty/futures markets while actual volume
   is in short-horizon markets. Zero overlap. Then: sampling from the live trade
   feed returns present-tense open markets. Also zero resolvable.

The generalisation: before measuring anything about a population, verify that
your sample actually intersects it. A spot-check on a small subset will look
fine and mislead you — `endDate`-sorted markets were all 100% resolvable.

## Build log — skeleton (2026-07-28)

Status change: **skeleton exists, probe green, thesis still untested.**

Structure, mirroring Edge-Factory conventions exactly:

    src/slipstream/config.py             gates + API bases + exclusion filters
    src/slipstream/assay.py              Wilson LB, shrinkage, grade ladder, score_wallet
    src/slipstream/sources/polymarket.py public API adapter (no auth, no classes)
    scripts/probe_polymarket.py          reachability + shape probe
    tests/test_assay.py                  11 tests, deterministic, no network

Adapter contract is Edge-Factory's: plain functions, return `list[dict]`, no
classes, no `normalize()` methods.

### Probe result (6/6 green)

    gamma /markets (open)                  50 open markets
    gamma /markets (closed) + resolution   25/25 cleanly resolvable
    data /trades (public feed)             20 trades, all required fields
    data /trades?user= (pagination)        1000 trades / 36 markets
    clob /book (depth)                     spread 2.0-7.5% of mid
    clob /sampling-markets (rewards)       947/1000 w/ rewards, min_size=20 max_spread=5.5

### NEW FINDING — resolution truth has an era boundary

The first probe run returned **0/25 resolvable**, contradicting the 20/20
recorded earlier in this handover. Cause found and measured:

    gamma default order                n=40  resolvable=0   all-zero=23  fractional=17
    gamma order=endDate&ascending=false n=40  resolvable=40  all-zero=0   fractional=0

Gamma's DEFAULT ordering surfaces 2020-era markets whose `outcomePrices` have
degraded to `["0","0"]` or to tiny floats (1.01e-6). **Resolution truth is not
recoverable for those markets.** The earlier 20/20 check had used
`order=endDate&ascending=false` and so silently sampled only the modern era.

Consequences, now encoded:
- `fetch_markets()` defaults to `recent_first=True` and documents why.
- `resolution_of()` returns None for degraded rows — excluded from scoring,
  never guessed.
- `tests/test_degraded_legacy_markets_return_none` locks the behaviour in.
- **Open question added:** where exactly is the usable-history boundary? It
  must be established BEFORE any wallet ranking, because it caps how far back
  a walk-forward split can be placed. A split earlier than the boundary would
  score wallets against unrecoverable outcomes and silently produce garbage.

This is the same class of error as the Price `signal_to_fill_bps` sign
mistake: a spot-check that happened to sample the favourable subset. Caught
here by the probe rather than by three weeks of downstream analysis.

### Deliberate divergence from Ma Golide

`assay.grade()` returns UNGRADED for small n and CHARCOAL for known-bad. Ma
Golide's `classify_tier()` returned ROBBER for both, collapsing "insufficient
evidence" into "reliably bad" — which downstream meant *fading* unproven
edges. A regression test guards this.

### Not built, deliberately

- No capture loop. No book snapshot recorder. No strategy code. No execution.
- `.env.example` lists execution credentials as commented placeholders only,
  with a note that research needs none.
- `localdata/` is gitignored except `.gitkeep`.

### Next

`scripts/test_persistence.py` — the falsification test for open question 2.
Rank wallets on period A, measure the same cohort on period B. If top-cohort
ROI in B does not beat the population baseline by `GATES.min_cohort_edge`,
the thesis is dead and Slipstream stops here.

Establish the usable-history boundary first; the split date depends on it.
