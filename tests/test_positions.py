import pytest
from slipstream.positions import build_positions, resolutions_for

def test_resolutions_for():
    markets = [
        {"conditionId": "c1", "closed": True, "outcomePrices": '["1", "0"]'},
        {"conditionId": "c2", "closed": True, "outcomePrices": '["0", "1"]'},
        {"conditionId": "c3", "closed": True, "outcomePrices": '["0.5", "0.5"]'},
        {"conditionId": "c4", "closed": False, "outcomePrices": '["1", "0"]'}
    ]
    res = resolutions_for(markets)
    assert res == {"c1": 0, "c2": 1}

def test_build_positions_winning_buy():
    trades = [
        {"conditionId": "c1", "outcomeIndex": 0, "side": "BUY", "size": 10, "price": 0.4, "slug": "m1"}
    ]
    res = {"c1": 0}
    pos, skips = build_positions(trades, res)
    assert skips == {"flat_or_short": 0, "unresolved": 0, "negative_or_zero_cost": 0}
    assert len(pos) == 1
    assert pos[0] == {"slug": "m1", "conditionId": "c1", "outcomeIndex": 0, "shares": 10.0, "cost": 4.0, "payout": 10.0, "won": True}

def test_build_positions_losing_buy():
    trades = [
        {"conditionId": "c1", "outcomeIndex": 1, "side": "BUY", "size": 10, "price": 0.4, "slug": "m1"}
    ]
    res = {"c1": 0}
    pos, skips = build_positions(trades, res)
    assert len(pos) == 1
    assert pos[0] == {"slug": "m1", "conditionId": "c1", "outcomeIndex": 1, "shares": 10.0, "cost": 4.0, "payout": 0.0, "won": False}

def test_build_positions_partial_sell():
    trades = [
        {"conditionId": "c1", "outcomeIndex": 0, "side": "BUY", "size": 10, "price": 0.4, "slug": "m1"},
        {"conditionId": "c1", "outcomeIndex": 0, "side": "SELL", "size": 5, "price": 0.6, "slug": "m1"}
    ]
    res = {"c1": 0}
    pos, skips = build_positions(trades, res)
    assert len(pos) == 1
    assert pos[0]["shares"] == 5.0
    assert pos[0]["cost"] == (4.0 - 3.0)  # 1.0
    assert pos[0]["payout"] == 5.0

def test_build_positions_full_sell_skipped():
    trades = [
        {"conditionId": "c1", "outcomeIndex": 0, "side": "BUY", "size": 10, "price": 0.4, "slug": "m1"},
        {"conditionId": "c1", "outcomeIndex": 0, "side": "SELL", "size": 10, "price": 0.6, "slug": "m1"}
    ]
    res = {"c1": 0}
    pos, skips = build_positions(trades, res)
    assert len(pos) == 0
    assert skips["flat_or_short"] == 1
    
def test_build_positions_unresolved_skipped():
    trades = [
        {"conditionId": "c2", "outcomeIndex": 0, "side": "BUY", "size": 10, "price": 0.4, "slug": "m2"}
    ]
    res = {"c1": 0} # c2 not in res
    pos, skips = build_positions(trades, res)
    assert len(pos) == 0
    assert skips["unresolved"] == 1

def test_build_positions_skip_counts_sum():
    trades = [
        # 1: flat
        {"conditionId": "c1", "outcomeIndex": 0, "side": "BUY", "size": 10, "price": 0.4},
        {"conditionId": "c1", "outcomeIndex": 0, "side": "SELL", "size": 10, "price": 0.6},
        
        # 2: unresolved
        {"conditionId": "c2", "outcomeIndex": 0, "side": "BUY", "size": 10, "price": 0.4},
        
        # 3: negative cost
        {"conditionId": "c1", "outcomeIndex": 1, "side": "BUY", "size": 10, "price": 0.4},
        {"conditionId": "c1", "outcomeIndex": 1, "side": "SELL", "size": 5, "price": 0.9}
    ]
    res = {"c1": 0, "c1": 1} # c1 has win index 1
    pos, skips = build_positions(trades, {"c1": 1})
    
    assert len(pos) == 0
    assert skips["flat_or_short"] == 1
    assert skips["unresolved"] == 1
    assert skips["negative_or_zero_cost"] == 1
    assert sum(skips.values()) == 3
