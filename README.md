# NIAN — brand new autonomous Indian F&O bot

Profit-only objective. Indexes (NIFTY/BANKNIFTY/SENSEX) + Equities F&O.

Built from scratch — no reference to older bots.

## Quickstart
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env  # fill GROWW_API_KEY / TOTP_SECRET
.venv/bin/python scripts/download_data.py
.venv/bin/python scripts/run_backtest.py   # 12y walk-forward, full costs
.venv/bin/python scripts/run_paper.py --once
```

## What it trades
- Index futures (spot proxy) via Groww API — gap continuation, overnight drift (VIX-gated), VIX mean-reversion
- Equity F&O (10 liquid names, expandable to 180) — momentum, RSI2, breakout

All backtests use full NSE cost stack (`src/core/costs.py`): brokerage ₹20/order, STT, exchange, SEBI, stamp, GST, slippage — and conservative fill (stop before target).

## Risk
- 1% risk/trade, max 3 lots/₹10L, daily -2% / weekly -4% kill switches (`src/core/risk.py:1`)
- Square-off 15:18 forced flat

## Execution
- `src/execution/groww_broker.py:1` — TOTP auto-refresh, Bearer token, paper fallback
- `src/execution/orchestrator.py:1` — IST session loop, kill checks, square-off

## Results
See `results/backtest_report.json` after running `scripts/run_backtest.py`. Honest numbers — no curve-fit. Walk-forward OOS reported for every engine.

## Groww setup
1. Groww -> Trade API -> Create API key + TOTP secret
2. Put in `.env`: GROWW_API_KEY, GROWW_TOTP_SECRET, GROWW_API_SECRET (if any)
3. Run paper first: `execution.broker: paper` in `config/settings.yaml:55`
4. Flip to `groww` when paper tracking error <30% for 4-6 weeks

## Compliance
SEBI retail algo needs broker Algo ID + static IP whitelist. Paper mode has no restriction. Groww adapter will reject live without token.
