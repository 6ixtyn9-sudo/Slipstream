#!/usr/bin/env python3
"""
TASK 3 — The falsification test.
Does a persistently skilled wallet cohort exist?
Walk-forward: rank on period A (before split), measure on period B (after split).

Bug-fix notes:
  1. Split date must be validated against the real history boundary (closedTime,
     not endDate). Guard refuses to run if split is outside the usable era.
  2. Period B emptiness is detected and treated as a hard error, not NOISE.
  3. population_roi_B is computed from the complement (eligible_A minus cohort),
     not the full eligible set which would include the cohort.
  4. Guard: refuse to run if eligible_A < 2 * cohort_top_n — cohort would be
     most of the population and the comparison is meaningless.
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone
from typing import List, Tuple

from slipstream.config import GATES
from slipstream.assay import score_wallet, WalletScore
from slipstream.positions import build_positions, resolutions_for
from slipstream.sources.polymarket import fetch_trades, fetch_markets, fetch_wallet_history


def parse_timestamp(ts) -> datetime:
    """Parse trade or market timestamp to UTC datetime."""
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    if isinstance(ts, str):
        ts = ts.strip()
        if ts.isdigit():
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
        # ISO format: "2026-07-28T20:00:00Z" or "2026-07-28 20:00:00+00"
        ts = ts.replace(" ", "T")
        if ts.endswith("+00"):
            ts = ts[:-3] + "+00:00"
        ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)
    raise ValueError(f"Cannot parse timestamp: {ts!r}")


def stake_weighted_roi(wallets: List[Tuple[WalletScore, WalletScore]], min_b_trades: int) -> Tuple[float, int, float]:
    """Compute stake-weighted ROI in period B for a list of (score_A, score_B) pairs.
    Returns (roi, n_eligible_wallets, total_staked).
    """
    staked = 0.0
    pnl = 0.0
    n = 0
    for _, sb in wallets:
        if sb.n_trades >= min_b_trades:
            staked += sb.staked
            pnl += sb.pnl
            n += 1
    roi = pnl / staked if staked > 0 else None
    return roi, n, staked


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-wallets", type=int, default=300)
    parser.add_argument("--split", type=str, default=GATES.split_date)
    args = parser.parse_args()

    # ── Load boundary from Task 1 ──────────────────────────────────────────
    boundary_path = "localdata/history_boundary.json"
    if not os.path.exists(boundary_path):
        print(f"ERROR: {boundary_path} not found. Run find_history_boundary.py first.")
        sys.exit(1)

    with open(boundary_path) as f:
        boundary = json.load(f)

    rec_min_date = boundary.get("recommended_min_date", "2020-01-01")

    if args.split < rec_min_date:
        print(f"ERROR: Split date {args.split!r} is before the usable history boundary {rec_min_date!r}.")
        print("Period A would contain markets with unrecoverable resolution truth.")
        print(f"Choose a split date on or after {rec_min_date}.")
        sys.exit(1)

    # Quick sense check: split should be in the past
    split_dt = parse_timestamp(f"{args.split}T00:00:00Z")
    now_utc = datetime.now(timezone.utc)
    if split_dt >= now_utc:
        print(f"ERROR: Split date {args.split!r} is in the future ({split_dt.date()} >= today).")
        print("Period B would be empty. Choose a past date with real trade volume.")
        sys.exit(1)

    print(f"Split date : {args.split}  (boundary: {rec_min_date})")

    # ── Step 1: Sample wallets ─────────────────────────────────────────────
    print(f"\nSampling ≥ {args.min_wallets} wallets from the public feed...")
    wallet_addrs = set()
    offset = 0
    pages = 0
    while len(wallet_addrs) < args.min_wallets:
        trades = fetch_trades(limit=500, offset=offset)
        if not trades:
            break
        for t in trades:
            pw = t.get("proxyWallet")
            if pw:
                wallet_addrs.add(pw)
        offset += 500
        pages += 1

    print(f"Collected {len(wallet_addrs)} wallets in {pages} pages.")
    print("NOTE: Sample is biased toward currently-active wallets (recency filter on public feed).")

    # ── Step 2: Build resolution map ──────────────────────────────────────
    print("\nFetching closed markets to build resolution map...")
    markets = []
    m_offset = 0
    while len(markets) < 5000:
        try:
            batch = fetch_markets(limit=500, closed=True, offset=m_offset, recent_first=True)
            if not batch:
                break
            markets.extend(batch)
            m_offset += 500
        except Exception:
            break

    resolutions = resolutions_for(markets)
    print(f"Fetched {len(markets)} markets → {len(resolutions)} resolvable condition IDs.")

    # ── Step 3: Fetch each wallet, split trades by period ─────────────────
    print(f"\nFetching wallet histories and splitting at {args.split}...")
    wallet_list = list(wallet_addrs)
    scored_wallets: List[Tuple[WalletScore, WalletScore]] = []
    n_no_b_trades = 0

    for i, w in enumerate(wallet_list):
        if (i + 1) % 50 == 0:
            print(f"  {i+1} / {len(wallet_list)} wallets processed...")

        hist = fetch_wallet_history(w, max_trades=2000)

        trades_A = []
        trades_B = []
        for t in hist:
            ts = t.get("timestamp")
            if not ts:
                continue
            try:
                dt = parse_timestamp(ts)
                if dt < split_dt:
                    trades_A.append(t)
                else:
                    trades_B.append(t)
            except (ValueError, OSError):
                continue

        if not trades_B:
            n_no_b_trades += 1

        pos_A, _ = build_positions(trades_A, resolutions)
        pos_B, _ = build_positions(trades_B, resolutions)

        s_A = score_wallet(w, pos_A, min_n=GATES.min_trades_rank)
        s_B = score_wallet(w, pos_B, min_n=GATES.min_trades_test)

        scored_wallets.append((s_A, s_B))

    print(f"Done. {n_no_b_trades}/{len(wallet_list)} wallets had zero B-period trades.")

    # ── Step 4: Filter eligible wallets in A ──────────────────────────────
    eligible_A = [
        (sa, sb)
        for sa, sb in scored_wallets
        if sa.n_trades >= GATES.min_trades_rank and sa.n_markets >= GATES.min_markets
    ]
    print(f"\nEligible in A (≥{GATES.min_trades_rank} trades, ≥{GATES.min_markets} markets): {len(eligible_A)}")

    # Guard: need at least 2× cohort size to make the comparison meaningful
    if len(eligible_A) < 2 * GATES.cohort_top_n:
        print(
            f"ERROR: Only {len(eligible_A)} wallets eligible in A; need ≥ {2 * GATES.cohort_top_n} "
            f"(2 × cohort_top_n={GATES.cohort_top_n}) for a meaningful cohort-vs-population comparison."
        )
        print("Lower --min-wallets is unlikely to help — try a wider date range or more wallet sampling.")
        sys.exit(1)

    # ── Step 5: Rank on A, take top cohort ────────────────────────────────
    eligible_A.sort(key=lambda x: x[0].wilson_lb, reverse=True)
    cohort = eligible_A[: GATES.cohort_top_n]
    complement = eligible_A[GATES.cohort_top_n :]  # Bug 3 fix: exclude cohort from population baseline
    cohort_size = len(cohort)
    print(f"Cohort (top-{cohort_size} by Wilson LB in A), complement: {len(complement)}")

    # ── Step 6: Measure on B ──────────────────────────────────────────────
    cohort_roi_B, cohort_n_B, cohort_staked_B = stake_weighted_roi(cohort, GATES.min_trades_test)
    complement_roi_B, complement_n_B, complement_staked_B = stake_weighted_roi(complement, GATES.min_trades_test)

    # Hard guard: B must have real data
    if cohort_roi_B is None or complement_roi_B is None:
        print("\nERROR: Period B has zero stake for cohort or complement.")
        print(f"  Cohort B trades: {cohort_n_B}, staked: {cohort_staked_B:.2f}")
        print(f"  Complement B trades: {complement_n_B}, staked: {complement_staked_B:.2f}")
        print("The split date may be too recent. Choose an earlier split with B-period volume.")
        sys.exit(1)

    edge = cohort_roi_B - complement_roi_B

    # ── Step 7: Null baseline (20 shuffles) ───────────────────────────────
    null_edges = []
    for _ in range(20):
        shuffled = eligible_A[:]
        random.shuffle(shuffled)
        rand_cohort = shuffled[:cohort_size]
        rand_complement = shuffled[cohort_size:]
        rc_roi, _, rc_staked = stake_weighted_roi(rand_cohort, GATES.min_trades_test)
        rp_roi, _, rp_staked = stake_weighted_roi(rand_complement, GATES.min_trades_test)
        if rc_roi is not None and rp_roi is not None:
            null_edges.append(rc_roi - rp_roi)

    null_mean = sum(null_edges) / len(null_edges) if null_edges else 0.0
    null_var = (
        sum((x - null_mean) ** 2 for x in null_edges) / len(null_edges) if null_edges else 0.0
    )
    null_sd = null_var ** 0.5

    # ── Step 8: Verdict ───────────────────────────────────────────────────
    is_noise = abs(edge - null_mean) <= null_sd

    if is_noise:
        verdict = f"NOISE (edge {edge:+.3f} is within 1 SD of null {null_mean:+.3f} ± {null_sd:.3f})"
    elif edge >= GATES.min_cohort_edge:
        verdict = "THESIS SUPPORTED"
    elif edge >= 0:
        verdict = "WEAK / INCONCLUSIVE"
    else:
        verdict = "THESIS REJECTED"

    # ── Output ────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PERSISTENCE FALSIFICATION REPORT")
    print("=" * 60)
    print(f"  Split date          : {args.split}")
    print(f"  Wallets sampled     : {len(wallet_addrs)}")
    print(f"  Eligible in A       : {len(eligible_A)}")
    print(f"  Cohort size         : {cohort_size}")
    print(f"  Cohort B wallets    : {cohort_n_B}  (staked: ${cohort_staked_B:.2f})")
    print(f"  Complement B wallets: {complement_n_B}  (staked: ${complement_staked_B:.2f})")
    print(f"  Cohort ROI (B)      : {cohort_roi_B:+.3f}")
    print(f"  Complement ROI (B)  : {complement_roi_B:+.3f}")
    print(f"  Edge                : {edge:+.3f}  ({edge*100:+.2f} pp)")
    print(f"  Null mean (20x shuf): {null_mean:+.3f}  SD: {null_sd:.3f}")
    print(f"  Verdict             : {verdict}")
    print("=" * 60)

    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "split_date": args.split,
        "boundary_min_date": rec_min_date,
        "wallets_sampled": len(wallet_addrs),
        "eligible_A": len(eligible_A),
        "cohort_size": cohort_size,
        "cohort_n_B": cohort_n_B,
        "cohort_staked_B": cohort_staked_B,
        "complement_n_B": complement_n_B,
        "complement_staked_B": complement_staked_B,
        "cohort_roi_B": cohort_roi_B,
        "complement_roi_B": complement_roi_B,
        "edge": edge,
        "null_mean": null_mean,
        "null_sd": null_sd,
        "is_noise": is_noise,
        "verdict": verdict,
        "sampling_bias_note": "Public feed ordered by recency — sample biased toward currently-active wallets.",
    }

    os.makedirs("localdata", exist_ok=True)
    with open("localdata/persistence_report.json", "w") as f:
        json.dump(out, f, indent=2)

    print("\nWritten: localdata/persistence_report.json")


if __name__ == "__main__":
    main()
