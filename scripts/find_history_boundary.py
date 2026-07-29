#!/usr/bin/env python3
"""
TASK 1 — Establish the usable-history boundary.

Key distinction: `endDate` is the market's deadline (can be years in the future
even for closed markets). `closedTime` is when the market actually resolved.
We bucket by closedTime and walk backwards in closedTime to find where
pct_resolvable drops below 0.95.

Paging: endDate desc is the only ordering that doesn't 422 at offset>0, so
we still use it for paging — but we bucket each market by its closedTime month.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

from slipstream.sources.polymarket import fetch_markets, resolution_of


def main():
    print("Fetching closed markets to find history boundary...")
    print("Bucketing by closedTime (actual resolution date), paging by endDate desc.\n")

    offset = 0
    limit = 100  # Gamma silently caps limit at 100 regardless of what is requested
    max_markets = 5000
    scanned = 0

    # closedTime month (YYYY-MM) -> {"n": 0, "resolvable": 0}
    buckets = defaultdict(lambda: {"n": 0, "resolvable": 0})

    while scanned < max_markets:
        print(f"  fetching offset {offset}...")
        try:
            markets = fetch_markets(limit=limit, closed=True, offset=offset, recent_first=True)
            if not markets:
                print("  empty page, stopping.")
                break
        except Exception as e:
            print(f"  stopped: {e}")
            break

        for m in markets:
            closed_time_str = m.get("closedTime")
            if not closed_time_str:
                continue

            # closedTime format: "2026-07-18 22:27:43+00" — take first 7 chars for YYYY-MM
            month = str(closed_time_str)[:7]
            if not month or month < "2020-01":
                continue

            buckets[month]["n"] += 1
            if resolution_of(m) is not None:
                buckets[month]["resolvable"] += 1

        actual = len(markets)
        scanned += actual
        offset += actual  # stride = actual rows returned, not the requested limit

    print(f"\nScanned {scanned} markets, found data for {len(buckets)} months.\n")

    # Sort newest-first for the boundary walk
    by_month = sorted(
        [
            {
                "month": month,
                "n": buckets[month]["n"],
                "resolvable": buckets[month]["resolvable"],
                "pct": buckets[month]["resolvable"] / buckets[month]["n"]
                if buckets[month]["n"] > 0
                else 0.0,
            }
            for month in buckets
        ],
        key=lambda x: x["month"],
        reverse=True,  # newest first
    )

    # Walk backwards in time: boundary = oldest month where pct >= 0.95
    # AND every newer month also clears 0.95.
    boundary_month = None
    for m_data in by_month:  # newest first
        if m_data["pct"] >= 0.95:
            boundary_month = m_data["month"]
        else:
            # A gap — stop here; everything older is unreliable
            break

    if not boundary_month:
        print("ERROR: Even the newest month failed pct_resolvable >= 0.95 — cannot establish boundary.")
        sys.exit(1)

    recommended_min_date = f"{boundary_month}-01"

    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "boundary_month": boundary_month,
        "recommended_min_date": recommended_min_date,
        "markets_scanned": scanned,
        "by_month": by_month,
    }

    os.makedirs("localdata", exist_ok=True)
    with open("localdata/history_boundary.json", "w") as f:
        json.dump(out, f, indent=2)

    print(f"{'Month':<10} | {'Markets':<8} | {'Resolvable':<10} | {'Pct':<7}")
    print("-" * 46)
    for m_data in by_month:
        flag = " ← BOUNDARY" if m_data["month"] == boundary_month else ""
        print(
            f"{m_data['month']:<10} | {m_data['n']:<8} | {m_data['resolvable']:<10} | {m_data['pct']:.1%}{flag}"
        )

    print(f"\nBoundary Month      : {boundary_month}")
    print(f"Recommended min date: {recommended_min_date}")
    print(f"Written             : localdata/history_boundary.json")


if __name__ == "__main__":
    main()
