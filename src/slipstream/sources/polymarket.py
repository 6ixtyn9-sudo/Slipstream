"""Polymarket public API adapter.

Contract (same shape as Edge-Factory's source adapters):
  plain functions, no classes, no normalize() methods, return list[dict].

All endpoints here are PUBLIC and need NO authentication. Verified live
2026-07-28. Trading would need py-clob-client + a Polygon key; nothing in
this module trades.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from slipstream.config import (
    CLOB_BASE,
    DATA_BASE,
    GAMMA_BASE,
    MAX_RETRIES,
    REQUEST_DELAY_SEC,
    REQUEST_TIMEOUT_SEC,
    RESOLVED_PRICES,
)

HEADERS = {"User-Agent": "slipstream-research/0.1 (public API, read-only)"}


def _get(url: str, retries: int = MAX_RETRIES):
    """GET JSON with polite retry/backoff. Raises on final failure."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            time.sleep(REQUEST_DELAY_SEC)
            return data
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    return None


# ── Gamma: market discovery + resolution truth ─────────────────────────

def fetch_markets(limit: int = 500, closed: bool | None = None, offset: int = 0,
                  recent_first: bool = True) -> list[dict]:
    """List markets. closed=True gives resolved markets (our ground truth).

    recent_first=True orders by endDate desc. This is NOT cosmetic:

        default order   n=40  resolvable=0   all-zero=23  fractional=17
        recent endDate  n=40  resolvable=40  all-zero=0   fractional=0

    Gamma's default ordering surfaces 2020-era markets whose `outcomePrices`
    have degraded to ["0","0"] or to tiny floats like 1.01e-6 — resolution
    truth is NOT recoverable for them. Measured 2026-07-28. Any wallet
    scoring run must therefore be restricted to the modern era, and the
    usable-history boundary must be established before ranking anything.
    """
    q = {"limit": limit, "offset": offset}
    if closed is not None:
        q["closed"] = str(closed).lower()
    if recent_first:
        q["order"] = "endDate"
        q["ascending"] = "false"
    data = _get(f"{GAMMA_BASE}/markets?{urllib.parse.urlencode(q)}")
    return data if isinstance(data, list) else []


def resolution_of(market: dict) -> int | None:
    """Return winning outcome index, or None if not cleanly resolved.

    Gamma `outcomePrices` on a closed market is ["0","1"] or ["1","0"].
    Verified 2026-07-28: 20/20 recently-closed markets resolvable.
    Anything ambiguous returns None and MUST be excluded from scoring rather
    than guessed at.
    """
    if not market.get("closed"):
        return None
    raw = market.get("outcomePrices")
    try:
        prices = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return None
    if not prices or not all(str(p) in RESOLVED_PRICES for p in prices):
        return None
    winners = [i for i, p in enumerate(prices) if float(p) == 1.0]
    return winners[0] if len(winners) == 1 else None


# ── Data API: the whole point — per-wallet trade history ───────────────

def fetch_trades(user: str | None = None, limit: int = 500,
                 offset: int = 0) -> list[dict]:
    """Public trade feed. With `user=` it is one wallet's history.

    Verified paginating: limit=500&offset=0 and offset=500 both returned
    full pages for a sampled wallet.

    Fields: proxyWallet, side, size, price, timestamp, conditionId, slug,
    outcome, outcomeIndex, transactionHash, title, eventSlug.
    """
    q: dict = {"limit": limit, "offset": offset}
    if user:
        q["user"] = user
    data = _get(f"{DATA_BASE}/trades?{urllib.parse.urlencode(q)}")
    return data if isinstance(data, list) else []


def fetch_wallet_history(user: str, max_trades: int = 5000) -> list[dict]:
    """Page through one wallet's full history up to max_trades."""
    out: list[dict] = []
    offset = 0
    page = 500
    while len(out) < max_trades:
        batch = fetch_trades(user=user, limit=page, offset=offset)
        if not batch:
            break
        out.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return out[:max_trades]


# ── CLOB: order books (needed later for the maker thesis, not for Q2) ──

def fetch_book(token_id: str) -> dict:
    """Current order book depth for one token.

    NOTE: /orderbook-history is DEAD platform-wide since ~2026-02-20 and
    returns empty for any recent window. Book depth CANNOT be backfilled —
    if maker viability is ever assessed, snapshots must be recorded FORWARD
    from day one. See HANDOVER constraint 1, and the Price 38%-fill-rate
    lesson that motivates it.
    """
    return _get(f"{CLOB_BASE}/book?token_id={token_id}") or {}


def fetch_reward_markets(limit: int = 500) -> list[dict]:
    """Reward-eligible markets, carrying rewards{rates,min_size,max_spread}."""
    data = _get(f"{CLOB_BASE}/sampling-markets?limit={limit}")
    return (data or {}).get("data", [])
