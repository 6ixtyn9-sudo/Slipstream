#!/usr/bin/env python3
"""
TASK 1 — Establish the usable-history boundary.
Paging closed markets backwards in time to find the oldest month
where pct_resolvable >= 0.95 and all newer months also clear 0.95.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

from slipstream.sources.polymarket import fetch_markets, resolution_of

def main():
    print("Fetching closed markets to find history boundary...")
    
    offset = 0
    limit = 500
    max_markets = 5000
    scanned = 0
    
    # month (YYYY-MM) -> {"n": 0, "resolvable": 0}
    buckets = defaultdict(lambda: {"n": 0, "resolvable": 0})
    
    while scanned < max_markets:
        print(f"  fetching offset {offset}...")
        try:
            markets = fetch_markets(limit=limit, closed=True, offset=offset, recent_first=True)
            if not markets:
                break
        except Exception as e:
            print(f"  stopped due to api limit or error: {e}")
            break
            
        reached_2020 = False
        for m in markets:
            end_date_str = m.get("endDate")
            if not end_date_str:
                continue
                
            # typical format: "2026-07-28T20:00:00Z"
            # just take the first 7 chars for YYYY-MM
            month = end_date_str[:7]
            if month.startswith("2020"):
                reached_2020 = True
                break
                
            buckets[month]["n"] += 1
            if resolution_of(m) is not None:
                buckets[month]["resolvable"] += 1
                
        scanned += len(markets)
        offset += limit
        
        if reached_2020:
            print("  reached 2020, stopping.")
            break

    # compute pct
    by_month = []
    for month in sorted(buckets.keys(), reverse=True): # newest first
        n = buckets[month]["n"]
        res = buckets[month]["resolvable"]
        pct = res / n if n > 0 else 0.0
        by_month.append({
            "month": month,
            "n": n,
            "resolvable": res,
            "pct": pct
        })
        
    # Walk backwards in time (which is forwards in by_month, since it's sorted newest first)
    boundary_month = None
    for m_data in by_month:
        if m_data["pct"] >= 0.95:
            boundary_month = m_data["month"]
        else:
            break
            
    if not boundary_month:
        print("ERROR: No valid boundary month found (even the newest month failed).")
        sys.exit(1)
        
    recommended_min_date = f"{boundary_month}-01"
    
    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "boundary_month": boundary_month,
        "recommended_min_date": recommended_min_date,
        "markets_scanned": scanned,
        "by_month": by_month
    }
    
    os.makedirs("localdata", exist_ok=True)
    with open("localdata/history_boundary.json", "w") as f:
        json.dump(out, f, indent=2)
        
    print("\nResolution Boundary Report:")
    print(f"{'Month':<10} | {'Markets':<8} | {'Resolvable':<10} | {'Pct':<6}")
    print("-" * 45)
    for m_data in by_month:
        print(f"{m_data['month']:<10} | {m_data['n']:<8} | {m_data['resolvable']:<10} | {m_data['pct']:.1%}")
        
    print(f"\nBoundary Month: {boundary_month}")
    print(f"Recommended minimum split date: {recommended_min_date}")

if __name__ == "__main__":
    main()
