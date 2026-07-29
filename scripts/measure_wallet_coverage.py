#!/usr/bin/env python3
"""
Measurement: Trade-first, resolve-on-demand coverage check.
1. Sample ~20 wallets from the public feed.
2. Fetch their full trade histories.
3. Extract unique conditionIds.
4. Look up each conditionId individually in Gamma and cache resolutions.
5. Measure what fraction of trades are resolvable.
"""

import json
import os
import time
import urllib.parse
import urllib.request
from collections import defaultdict

from slipstream.config import GAMMA_BASE, REQUEST_TIMEOUT_SEC, REQUEST_DELAY_SEC
from slipstream.sources.polymarket import fetch_trades, fetch_wallet_history, resolution_of

HEADERS = {"User-Agent": "slipstream-research/0.1"}

def fetch_single_market(condition_id: str):
    """Fetch a single market by conditionId from Gamma."""
    q = urllib.parse.urlencode({"condition_ids": condition_id})
    url = f"{GAMMA_BASE}/markets?{q}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
            return data[0] if data else None
    except Exception as e:
        return None

def main():
    print("Sampling 20 wallets from public feed...")
    wallet_addrs = set()
    offset = 0
    while len(wallet_addrs) < 20:
        trades = fetch_trades(limit=500, offset=offset)
        if not trades:
            break
        for t in trades:
            pw = t.get("proxyWallet")
            if pw:
                wallet_addrs.add(pw)
                if len(wallet_addrs) >= 20:
                    break
        offset += 500
        time.sleep(REQUEST_DELAY_SEC)

    wallets = list(wallet_addrs)[:20]
    print(f"Collected {len(wallets)} wallets.")

    cache_path = "localdata/resolutions.json"
    resolutions = {}
    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            resolutions = json.load(f)
    print(f"Loaded {len(resolutions)} cached resolutions.")

    all_trades_by_wallet = {}
    unique_cids = set()

    print("\nFetching trade histories...")
    for i, w in enumerate(wallets):
        hist = fetch_wallet_history(w, max_trades=2000)
        all_trades_by_wallet[w] = hist
        for t in hist:
            cid = t.get("conditionId")
            if cid:
                unique_cids.add(cid)
        print(f"  Wallet {i+1}/20: {len(hist)} trades")
        time.sleep(REQUEST_DELAY_SEC)

    print(f"\nExtracted {len(unique_cids)} unique conditionIds across all 20 wallets.")

    cids_to_fetch = [cid for cid in unique_cids if cid not in resolutions]
    print(f"Need to fetch {len(cids_to_fetch)} un-cached conditionIds...")

    fetched = 0
    for i, cid in enumerate(cids_to_fetch):
        m = fetch_single_market(cid)
        if m:
            res = resolution_of(m)
            # Store even if None, so we know we checked it
            # But wait, if it's still open, it might close later.
            # For this diagnostic, we store the current state.
            resolutions[cid] = {
                "question": m.get("question"),
                "closed": m.get("closed", False),
                "resolution": res
            }
        else:
            resolutions[cid] = {"question": "NOT_FOUND", "closed": False, "resolution": None}
            
        fetched += 1
        if fetched % 50 == 0:
            print(f"  Fetched {fetched}/{len(cids_to_fetch)}...")
            # Save cache periodically
            with open(cache_path, "w") as f:
                json.dump(resolutions, f, indent=2)
        time.sleep(REQUEST_DELAY_SEC)

    # Final save
    with open(cache_path, "w") as f:
        json.dump(resolutions, f, indent=2)

    print("\nCalculating coverage per wallet...")
    
    total_trades = 0
    total_resolved = 0
    
    for i, w in enumerate(wallets):
        trades = all_trades_by_wallet[w]
        n_trades = len(trades)
        if n_trades == 0:
            continue
            
        n_resolved = 0
        n_crypto = 0
        
        for t in trades:
            cid = t.get("conditionId")
            if not cid:
                continue
            rinfo = resolutions.get(cid, {})
            if rinfo.get("resolution") is not None:
                n_resolved += 1
                
            q = rinfo.get("question", "").lower()
            if "bitcoin" in q or "btc" in q or "ethereum" in q or "eth" in q or "xrp" in q:
                n_crypto += 1

        total_trades += n_trades
        total_resolved += n_resolved
        
        pct_res = n_resolved / n_trades * 100
        pct_crypto = n_crypto / n_trades * 100
        print(f"Wallet {i+1:>2}: {n_trades:>4} trades | {n_resolved:>4} resolved ({pct_res:>5.1f}%) | {pct_crypto:>5.1f}% crypto related")
        
    if total_trades > 0:
        print(f"\nOverall Coverage: {total_resolved}/{total_trades} trades resolved ({total_resolved/total_trades*100:.1f}%)")

if __name__ == "__main__":
    main()
