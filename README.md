# Slipstream

Polymarket attaches a `proxyWallet` address to every public trade. That field
does not exist on any sportsbook, anywhere. It means a trader's entire history
is reconstructable: what they bought, at what price, in what size, when — and
whether they were right.

**Slipstream ranks traders, not outcomes.**

> Status: skeleton. Probe green, thesis **untested**. The next script
> (`scripts/test_persistence.py`) is a falsification test that can end the
> project — by design.

## Quickstart

```bash
pip install -r requirements.txt
PYTHONPATH=src python3 -m pytest tests/ -q           # 11 passed
PYTHONPATH=src python3 scripts/probe_polymarket.py   # 6/6 checks passed
```

No credentials required. Every endpoint used is public and read-only.

## Layout

```
src/slipstream/config.py              gates, API bases, exclusion filters
src/slipstream/assay.py               Wilson LB, shrinkage, grades, score_wallet
src/slipstream/sources/polymarket.py  public API adapter
scripts/probe_polymarket.py           reachability + shape probe
tests/test_assay.py                   deterministic, no network
```

## Doctrine

- Wilson lower bound, never raw hit rate.
- Walk-forward only: rank on period A, measure on period B.
- ROI alongside hit rate, always.
- Small n => UNGRADED, never inflated. "Unknown" and "reliably bad" are
  different labels.

## Documents

- `HANDOVER.md` — single source of truth. Thesis, verified API surface,
  constraints, capital arithmetic, open questions. **Read first.**
- `AGENT_BRIEF.md` — the next three tasks, specified to be actioned directly.
