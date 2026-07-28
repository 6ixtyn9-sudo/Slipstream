#!/usr/bin/env python3
"""Throw a stick at Polymarket.

Read-only reachability + shape probe. Confirms every endpoint Slipstream
depends on is alive and returns what the HANDOVER says it returns.

Costs nothing, needs no auth, touches no capital.

    PYTHONPATH=src python3 scripts/probe_polymarket.py
"""
from __future__ import annotations

import sys

from slipstream.sources.polymarket import (
    fetch_book,
    fetch_markets,
    fetch_reward_markets,
    fetch_trades,
    fetch_wallet_history,
    resolution_of,
)

OK, FAIL = "  ok  ", " FAIL "


def check(label: str, fn):
    try:
        detail = fn()
        print(f"[{OK}] {label:<38} {detail}")
        return True
    except Exception as e:  # noqa: BLE001 - a probe must report, not crash
        print(f"[{FAIL}] {label:<38} {type(e).__name__}: {e}")
        return False


def main() -> int:
    print("Slipstream probe — Polymarket public API (read-only)\n")
    results = []

    # 1. Gamma discovery
    state = {}

    def _markets():
        ms = fetch_markets(limit=50, closed=False)
        state["open"] = ms
        return f"{len(ms)} open markets"

    results.append(check("gamma /markets (open)", _markets))

    # 2. Resolution truth — the thing wallet PnL depends on
    def _resolved():
        ms = fetch_markets(limit=25, closed=True)
        res = [resolution_of(m) for m in ms]
        good = sum(1 for r in res if r is not None)
        state["closed"] = ms
        return f"{good}/{len(ms)} cleanly resolvable"

    results.append(check("gamma /markets (closed) + resolution", _resolved))

    # 3. Public trade feed — carries proxyWallet, the whole premise
    def _trades():
        ts = fetch_trades(limit=20)
        if not ts:
            raise RuntimeError("empty trade feed")
        need = {"proxyWallet", "price", "size", "side", "timestamp", "slug"}
        missing = need - set(ts[0])
        if missing:
            raise RuntimeError(f"missing fields: {missing}")
        state["wallet"] = ts[0]["proxyWallet"]
        return f"{len(ts)} trades, all required fields present"

    results.append(check("data /trades (public feed)", _trades))

    # 4. Per-wallet history + pagination
    def _history():
        w = state.get("wallet")
        if not w:
            raise RuntimeError("no sample wallet from previous step")
        h = fetch_wallet_history(w, max_trades=1000)
        mkts = len({t["slug"] for t in h})
        return f"{len(h)} trades / {mkts} markets for {w[:10]}..."

    results.append(check("data /trades?user= (pagination)", _history))

    # 5. Order book depth (for the later maker question)
    def _book():
        import json as _json

        for m in state.get("open", []):
            raw = m.get("clobTokenIds")
            if not raw:
                continue
            tok = (_json.loads(raw) if isinstance(raw, str) else raw)[0]
            b = fetch_book(tok)
            bids, asks = b.get("bids") or [], b.get("asks") or []
            if not (bids and asks):
                continue
            bb = max(float(x["price"]) for x in bids)
            ba = min(float(x["price"]) for x in asks)
            mid = (bb + ba) / 2
            return f"bid {bb:.3f} ask {ba:.3f} spread {(ba-bb)/mid*100:.1f}% of mid"
        raise RuntimeError("no two-sided book found in sample")

    results.append(check("clob /book (depth)", _book))

    # 6. Reward params — capital math inputs
    def _rewards():
        rm = fetch_reward_markets(limit=100)
        with_r = [m for m in rm if (m.get("rewards") or {}).get("min_size")]
        if not with_r:
            return f"{len(rm)} sampling markets, none with min_size"
        r = with_r[0]["rewards"]
        return f"{len(with_r)}/{len(rm)} w/ rewards; e.g. min_size={r.get('min_size')} max_spread={r.get('max_spread')}"

    results.append(check("clob /sampling-markets (rewards)", _rewards))

    passed = sum(results)
    print(f"\n{passed}/{len(results)} checks passed")
    if passed == len(results):
        print("\nAll dependencies alive. Next: scripts/test_persistence.py")
        print("(that is the falsification test — it can kill the thesis)")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
