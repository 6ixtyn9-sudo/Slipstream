#!/usr/bin/env python3
"""
TASK 3 — The falsification test
Does a persistently skilled wallet cohort exist?
Walk-forward split: rank on period A, measure on period B.
"""
import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone
from typing import List

from slipstream.config import GATES
from slipstream.assay import score_wallet
from slipstream.positions import build_positions, resolutions_for
from slipstream.sources.polymarket import fetch_trades, fetch_markets, fetch_wallet_history


def parse_date(ds) -> datetime:
    if isinstance(ds, (int, float)):
        return datetime.fromtimestamp(ds, tz=timezone.utc)
    if isinstance(ds, str):
        # Could be ISO format or string integer
        if ds.isdigit():
            return datetime.fromtimestamp(int(ds), tz=timezone.utc)
        # simplistic ISO 8601 parser (e.g. 2026-07-28T20:00:00Z)
        d_str = ds.replace('Z', '+00:00')
        return datetime.fromisoformat(d_str)
    return datetime.fromtimestamp(0, tz=timezone.utc)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-wallets", type=int, default=300)
    parser.add_argument("--split", type=str, default=GATES.split_date)
    args = parser.parse_args()

    # Check boundary
    boundary_path = "localdata/history_boundary.json"
    if not os.path.exists(boundary_path):
        print(f"ERROR: {boundary_path} not found. Run Task 1 first.")
        sys.exit(1)
        
    with open(boundary_path) as f:
        boundary = json.load(f)
        
    rec_min_date = boundary.get("recommended_min_date", "2020-01-01")
    if args.split < rec_min_date:
        print(f"ERROR: Split date {args.split} is before recommended minimum {rec_min_date}.")
        print("Cannot run walk-forward with unresolvable data. Exiting.")
        sys.exit(1)
        
    print(f"Sampling {args.min_wallets} wallets...")
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
    
    print("Fetching closed markets to build resolution map...")
    markets = []
    m_offset = 0
    scanned_months = set()
    # Fetch up to the boundary year-month roughly, or just fetch 5000
    while len(markets) < 5000:
        try:
            batch = fetch_markets(limit=500, closed=True, offset=m_offset, recent_first=True)
            if not batch:
                break
            markets.extend(batch)
            m_offset += 500
            
            # Check if we passed the recommended min date
            oldest_in_batch = min((m.get("endDate", "9999") for m in batch), default="9999")
            if oldest_in_batch < args.split:
                break
        except Exception:
            break

    resolutions = resolutions_for(markets)
    print(f"Fetched {len(markets)} markets, built {len(resolutions)} resolutions.")
    
    print("Fetching wallet histories and splitting...")
    split_dt = parse_date(f"{args.split}T00:00:00Z")
    
    scored_wallets = []
    
    for i, w in enumerate(list(wallet_addrs)):
        if (i+1) % 50 == 0:
            print(f"  processed {i+1} / {len(wallet_addrs)} wallets...")
        
        hist = fetch_wallet_history(w, max_trades=2000)
        
        trades_A = []
        trades_B = []
        for t in hist:
            t_str = t.get("timestamp")
            if not t_str:
                continue
            try:
                dt = parse_date(t_str)
                if dt < split_dt:
                    trades_A.append(t)
                else:
                    trades_B.append(t)
            except ValueError:
                continue
                
        pos_A, _ = build_positions(trades_A, resolutions)
        pos_B, _ = build_positions(trades_B, resolutions)
        
        s_A = score_wallet(w, pos_A, min_n=GATES.min_trades_rank)
        s_B = score_wallet(w, pos_B, min_n=GATES.min_trades_test)
        
        scored_wallets.append((s_A, s_B))
        
    print(f"\nEvaluating persistence split at {args.split}")
    
    # Eligible in A
    eligible_A = [w for w in scored_wallets if w[0].n_trades >= GATES.min_trades_rank and w[0].n_markets >= GATES.min_markets]
    print(f"Wallets eligible in A: {len(eligible_A)}")
    
    if len(eligible_A) == 0:
        print("ERROR: No wallets eligible in A.")
        sys.exit(1)
        
    # Rank in A
    eligible_A.sort(key=lambda x: x[0].wilson_lb, reverse=True)
    cohort = eligible_A[:GATES.cohort_top_n]
    cohort_size = len(cohort)
    
    # Compute B ROI for a list of wallets, filtering out those without enough B trades
    def compute_b_roi(wallet_list) -> float:
        staked = 0.0
        pnl = 0.0
        for (_, sb) in wallet_list:
            if sb.n_trades >= GATES.min_trades_test:
                staked += sb.staked
                pnl += sb.pnl
        return pnl / staked if staked > 0 else 0.0
        
    cohort_roi_B = compute_b_roi(cohort)
    population_roi_B = compute_b_roi(eligible_A)
    edge = cohort_roi_B - population_roi_B
    
    # Null baseline
    null_edges = []
    for _ in range(20):
        shuffled = eligible_A[:]
        random.shuffle(shuffled)
        rand_cohort = shuffled[:cohort_size]
        rand_cohort_roi = compute_b_roi(rand_cohort)
        null_edges.append(rand_cohort_roi - population_roi_B)
        
    null_mean = sum(null_edges) / len(null_edges)
    null_var = sum((x - null_mean)**2 for x in null_edges) / len(null_edges)
    null_sd = null_var ** 0.5
    
    # Verdict
    is_noise = (null_mean - null_sd) <= edge <= (null_mean + null_sd)
    
    if is_noise:
        verdict = f"NOISE (indistinguishable from random, within 1 SD of {null_mean:+.3f})"
    elif edge >= GATES.min_cohort_edge:
        verdict = "THESIS SUPPORTED"
    elif edge >= 0:
        verdict = "WEAK / INCONCLUSIVE"
    else:
        verdict = "THESIS REJECTED"
        
    print("\nResults:")
    print(f"  Wallets sampled: {len(wallet_addrs)}")
    print(f"  Eligible in A: {len(eligible_A)}")
    print(f"  Cohort size: {cohort_size}")
    print(f"  Cohort ROI (B): {cohort_roi_B:.2%}")
    print(f"  Population ROI (B): {population_roi_B:.2%}")
    print(f"  Edge: {edge*100:+.2f} pp")
    print(f"  Null baseline edge: {null_mean*100:+.2f} pp (SD: {null_sd*100:.2f} pp)")
    print(f"  Verdict: {verdict}")
    
    out = {
        "split_date": args.split,
        "wallets_sampled": len(wallet_addrs),
        "eligible_A": len(eligible_A),
        "cohort_size": cohort_size,
        "cohort_roi_B": cohort_roi_B,
        "population_roi_B": population_roi_B,
        "edge": edge,
        "null_mean": null_mean,
        "null_sd": null_sd,
        "verdict": verdict
    }
    
    os.makedirs("localdata", exist_ok=True)
    with open("localdata/persistence_report.json", "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
