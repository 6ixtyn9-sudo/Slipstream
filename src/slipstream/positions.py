from collections import defaultdict
from typing import Tuple

from slipstream.sources.polymarket import resolution_of

def build_positions(trades: list[dict], resolutions: dict[str, int]) -> Tuple[list[dict], dict]:
    """trades: raw rows from fetch_trades / fetch_wallet_history
       resolutions: {conditionId: winning_outcome_index}
       returns: (positions, skip_counts)
       where positions is [{slug, conditionId, outcomeIndex, shares, cost, payout, won}]
    """
    
    # Group trades by (conditionId, outcomeIndex)
    # Each group stores: buy_shares, sell_shares, buy_cost, sell_proceeds, slug
    groups = defaultdict(lambda: {
        "buy_shares": 0.0,
        "sell_shares": 0.0,
        "buy_cost": 0.0,
        "sell_proceeds": 0.0,
        "slug": ""
    })
    
    for t in trades:
        cid = t.get("conditionId")
        outcome_idx_str = t.get("outcomeIndex")
        
        if not cid or outcome_idx_str is None:
            continue
            
        try:
            outcome_idx = int(outcome_idx_str)
        except ValueError:
            continue
            
        key = (cid, outcome_idx)
        
        side = str(t.get("side")).upper()
        
        try:
            size = float(t.get("size", 0.0))
            price = float(t.get("price", 0.0))
        except (ValueError, TypeError):
            continue
            
        g = groups[key]
        if not g["slug"]:
            g["slug"] = t.get("slug", "")
            
        if side == "BUY":
            g["buy_shares"] += size
            g["buy_cost"] += size * price
        elif side == "SELL":
            g["sell_shares"] += size
            g["sell_proceeds"] += size * price
            
    skip_counts = {
        "flat_or_short": 0,
        "unresolved": 0,
        "negative_or_zero_cost": 0
    }
    
    positions = []
    
    for (cid, outcome_idx), g in groups.items():
        net_shares = g["buy_shares"] - g["sell_shares"]
        cost = g["buy_cost"] - g["sell_proceeds"]
        
        if net_shares <= 1e-6:
            skip_counts["flat_or_short"] += 1
            continue
            
        if cid not in resolutions:
            skip_counts["unresolved"] += 1
            continue
            
        if cost <= 1e-6:
            skip_counts["negative_or_zero_cost"] += 1
            continue
            
        won = (outcome_idx == resolutions[cid])
        payout = net_shares if won else 0.0
        
        positions.append({
            "slug": g["slug"],
            "conditionId": cid,
            "outcomeIndex": outcome_idx,
            "shares": net_shares,
            "cost": cost,
            "payout": payout,
            "won": won
        })
        
    return positions, skip_counts


def resolutions_for(markets: list[dict]) -> dict[str, int]:
    """Maps conditionId -> winning index using resolution_of()"""
    res = {}
    for m in markets:
        cid = m.get("conditionId")
        if cid:
            win_idx = resolution_of(m)
            if win_idx is not None:
                res[cid] = win_idx
    return res
