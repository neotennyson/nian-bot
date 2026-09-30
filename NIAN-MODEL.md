# NIAN — Complete Model & System Documentation
> **READ THIS FIRST if you are an AI LLM, agent, or new maintainer.** This file describes every part of `nian-bot/` — what it is, why it exists, how each file works, the data contracts, the math, the promotion ladder, and every known limitation. You should be able to rebuild or extend the bot from this file + `config/settings.yaml` + `README.md` alone.

---

## 0. TL;DR

**NIAN 🐉** (named after user's "break the Nian market" — Indian F&O) is a **brand-new autonomous Indian F&O trading bot** built from scratch in Sep 2026. It trades ** Index F&O only** (NIFTY/BANKNIFTY/SENSEX) via ** one proven engine: overnight drift VIX≥17 + 63-day health gate**. Everything else (gap, VIX-reversion, ORB, equities) was tested over 12 years and **killed after costs** — the bot sits out rather than trade losers. That's the "profit-only" design.

* Capital: ₹5L (configurable)
* Costs: Full NSE stack in `src/core/costs.py` — brokerage ₹20/order, STT 0.05% fut sell, exchange 0.00173%, SEBI, stamp, GST 18%, slippage 1.5 pts/side, stop-first fills
* Broker: Groww + Dhan via private token service `tokens.example.invalid` (`src/core/tokens.py`, same as Nemesis, `TOKEN_API_KEY` in `.env`)
* Mode: `paper` by default → 4-6 weeks tracking error <30% → `groww`/`dhan` live 1 lot → scale only on proven tracking
* Backtest: 12y Yahoo dailies, walk-forward OOS, **COMBINED ₹13.87L gross / ₹4.62L split Sharpe 1.37 OOS 1.23** after costs

**No magic. 93% of retail F&O loses (SEBI). We win by process: test everything, kill most, promote slowly, monitor forever.**

---

## 1. Does it trade every day?

**No — only ~26% of trading days (~65 trades/year).**

| Symbol | Trades 12y | Per year | % days traded | When it trades |
|--------|-----------|----------|---------------|----------------|
| NIFTY | 786 | 65.5 | 26.6% | VIX≥17 **AND** trailing 63d overnight sum >0 |
| BANKNIFTY | 740 | 61.7 | 25.0% | same |
| SENSEX | 856 | 71.3 | 29.0% | same |

**Session:** Entry `15:22` (last 8 min before close → buy futures), Exit `09:20` (next open). Square-off forced `15:18`. If VIX <17 (calm) or health ≤0 (overnight premium dead, as in 2025-26 decay), **bot does nothing that day**. 2026: BANKNIFTY/SENSEX traded 0 days (gate blocked loss), NIFTY traded but lost -₹37k (gate limited to -₹37k vs -₹12L ungated).

**Intra-day:** `orchestrator.py:run_once()` polled every 20s, checks kill switches → exit window (09:20±5m) → entry window (15:22±5m, health+VIX) → square-off.

---

## 2. Conviction Score — how profitable is it really?

Stolen from Prometheus' `src/research/conviction.py` — **threshold 0.60 to promote** (same as `TRINITY`).

```
components (weights): Sharpe .28 · Drawdown .16 · ProfitFactor .14 · Quarterly .12 · Plateau .12 · Coverage .18
each 0-1; Sharpe t = tanh(Sharpe/2); DD = 1 - |DD|/50; PF = (PF-1)/1.5; Coverage = min(1, trades/(12*60))
reliability = sqrt(n/30) capped at 1 (n≥200 → 1.0)
conviction = (weighted sum) * reliability
```

| Engine | Sharpe | PF | MaxDD | Q-hit | Plateau | Coverage | **Conviction** | Verdict |
|--------|--------|----|-------|-------|---------|----------|----------------|---------|
| SENSEX overnight gated63 | 1.77 | 1.42 | -21.3% | 0.57 | 0.85 | 1.0 | **0.68** | ✅ Pass (promoted) |
| NIFTY overnight gated63 | 1.27 | 1.28 | -22.4% | 0.47 | 0.85 | 1.0 | **0.61** | ✅ Barely pass |
| BANKNIFTY overnight gated63 | 0.97 | 1.20 | -25.1% | 0.40 | 0.85 | 1.0 | **0.55** | ❌ Parked (watch) |
| Gap continuation / VIX-rev / ORB / Equities | -1.5 to -3 | 0.6-0.75 | -45% | 0.2 | 0.1 | 0.3 | **0.05-0.25** | ☠️ Dead |
| **COMBINED (3 idx)** | **1.37** | — | **-31.7%** | — | — | — | **~0.64** | ✅ Portfolio |

**Interpretation:** 0.68 = modest edge, not a cash machine — 5.6% CAGR split on ₹5L, 61% win rate, -21% DD per symbol, -32% gross. OOS Sharpe 1.23 means edge survived walk-forward, but 2026 shows decay — gate saved capital. **Don't loosen kills to "give it room".**

---

## 3. Repo Layout

```
config/settings.yaml      ALL knobs (capital, costs, risk, universe, strategies, execution)
src/core/config.py        load_settings() + load_dotenv() (.env gitignored)
src/core/costs.py         CostModel — fut_cost(), opt_cost(), fut_pnl() (full stack)
src/core/risk.py          RiskManager — lots_for_risk(), kill switches
src/core/tokens.py        Token service — get_token("dhan"/"groww"), token_status(), probe() — reads TOKEN_API_KEY from .env / ~/.broker_tokens.json cache (copied from Nemesis)
src/data/loader.py        Yahoo fetch + parquet cache (data/raw/*.parquet), atr(), rsi()
src/strategies/base.py    Signal dataclass
src/strategies/index_strategies.py  overnight_drift_signals(vix_gate, health_lookback) + gap/orb/vix stubs
src/strategies/equity_strategies.py momentum/rsi2/breakout (killed, kept for reference)
src/backtest/engine.py    run_signals(), perf_stats() (Sharpe/MaxDD/PF/Win/CAGR)
src/backtest/walkforward.py walk_forward(train 3y / test 6m anchored)
src/execution/broker_base.py abstract
src/execution/paper_broker.py SQLite fills (logs/paper.db)
src/execution/groww_broker.py Groww REST (Bearer token from get_token)
src/execution/orchestrator.py IST session loop + _health_ok() + _vix_ok()
src/dashboard.py          Streamlit 🐉 dragon theme — paper/real toggle, live metrics
scripts/download_data.py  Yahoo refresh (indexes + 10 F&O stocks)
scripts/run_backtest.py   Profit-only portfolio runner → results/backtest_report.json
scripts/run_paper.py      --once / --loop poller
results/backtest_report.json  Honest numbers (per-symbol + COMBINED + WF windows)
data/raw/*.parquet        NIFTY/BANKNIFTY/SENSEX/INDIAVIX + equities (gitignored)
logs/paper.db             Fills journal (gitignored)
NIAN-MODEL.md             This file — for LLMs
```

---

## 4. Data & Costs (never understate)

**Data:** Yahoo `^NSEI/^NSEBANK/^BSESN/^INDIAVIX` via `yfinance` → `data/raw/*.parquet` (~2950 bars, 2014→today). Index values are spots, traded as futures proxy (lot 75/30/20). No intraday option premiums — 0DTE research needs Dhan `rollingoption` minute bars (not in repo). Every `df.index` is normalized midnight IST; joins use `.normalize()`.

**Costs `src/core/costs.py:18`:**
```python
brokerage=20/order, exch_opt 0.03503%, exch_fut 0.00173%, sebi 0.0001%, stamp 0.003% buy, STT 0.05% fut sell / 0.15% opt sell, gst 18% on (exch+sebi), ipft 0.002%, slippage 0.2% opt min 0.75 / 1.5 pts fut *2 sides
```
`fut_cost(entry,exit,lots,lot_size)` charges on both legs; `fut_pnl()` returns `(gross, cost, net)` rounded to ₹0.01 so journal ties out.

---

## 5. Execution

**Orchestrator `src/execution/orchestrator.py:18`:**
```
ist_now() pinned to Asia/Kolkata
run_once(now):
  1. risk.check_kill() → flat if daily -2% / weekly -4%
  2. exit window 09:20±5m → place SELL for all pos
  3. entry window 15:22±5m → _vix_ok() (>=17) → _health_ok(per symbol, 63d sum>0) → lots_for_risk(1.5% stop) → BUY
  4. square 15:18 → flat
```
`_health_ok`: `overnight = open[i]/close[i-1]-1`, `health = sum(last 63)`. ` _vix_ok`: `^INDIAVIX close`. Both read from `cached_fetch` parquets.

**Brokers:** `PaperBroker` SQLite; `GrowwBroker` uses `get_token("groww")` Bearer. Dhan data via `Token API → get_token("dhan")` → `access-token: <JWT>` + `client-id: YOUR_DHAN_CLIENT_ID`. Order path is **fenced** in `tokens.py:EXECUTION_PATH_NAMESPACES` — `oms/execution` cannot auto-fetch (SPEC 7.5 human gate).

---

## 6. How to Run (AI: follow exactly)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt  # yfinance, pandas, pyarrow, pyyaml, requests, streamlit
cp .env.example .env  # fill TOKEN_API_KEY (from Nemesis/.env) — aliased via NEMESIS_ENV fallback
PYTHONPATH=nian-bot nian-bot/.venv/bin/python nian-bot/scripts/download_data.py  # 12y Yahoo
PYTHONPATH=nian-bot nian-bot/.venv/bin/python nian-bot/scripts/run_backtest.py   # → results/backtest_report.json
PYTHONPATH=nian-bot nian-bot/.venv/bin/python nian-bot/scripts/run_paper.py --once
PYTHONPATH=nian-bot nian-bot/.venv/bin/streamlit run nian-bot/src/dashboard.py --server.port 8507
```

**Live:** Set `config/settings.yaml: execution.broker: groww`, ensure `TOKEN_API_KEY` live, `DHAN_CLIENT_ID` set, run `run_paper.py` as systemd/launchd. No Algo-ID needed for paper; live needs broker Algo-ID + static IP.

---

## 7. Known Limitations (honest)

1. **Overnight premium died in 2026** — gated cut loss but 2026 NIFTY still -₹37k; edge may be decaying structurally.
2. **Only daily bars** — intraday slippage assumed 1.5 pts, stop-first ordering. Real expiry vol spikes not modeled.
3. **No real option premiums** — iron-fly etc. killed after real Dhan minute replay (Sharpe -0.55). Don't re-add without `dhan_backfill.py`.
4. **Equities F&O = no edge daily** — all 4 families negative after costs; don't enable `equities` without minute research.
5. **Capital scaling** — `max_lots_per_10l:3` caps leverage; daily kill resets on restart (persist before VPS).
6. **Token service is SPOF** — `tokens.example.invalid` down → `TokenAPIUnreachable`, not a broker expiry. `probe()` checks this.

---

## 8. For the Next LLM

* Don't add a signal builder without a `results/` entry proving it was killed or promoted — the graveyard is the memory.
* Don't hand-tune a spec into `paper_queue` — run `scripts/run_backtest.py` and honor `conviction ≥0.60`.
* Don't reduce `health_lookback` to chase 2026 — 63d is the worst working case, 21d is best but fragile.
* Don't trade equities daily — you will lose 3x faster than indexes (Sharpe -15). Use minute panel `src/data/intraday.py` pattern.

---

*This bot is **NIAN** — powered by **Muse Spark 1.3** — built Sep 2026 from scratch for the "break the Nian market" brief. Profit-only, evidence over opinion.*
