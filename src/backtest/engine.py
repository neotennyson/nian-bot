from __future__ import annotations
import pandas as pd
import numpy as np
from dataclasses import dataclass
from src.core.costs import CostModel

@dataclass
class Trade:
    date: str
    symbol: str
    dir: int
    entry: float
    exit: float
    pts: float
    lots: int
    cost: float
    pnl: float
    reason: str

def run_signals(df: pd.DataFrame, signals: list, lot_size: int, capital: float, cost_model: CostModel, symbol: str="NIFTY", risk_per_trade_pct: float=1.0, max_lots_per_10l: int=3) -> list[Trade]:
    trades=[]
    # map date -> signal (one per day max)
    sig_by_date={s.date.normalize(): s for s in signals}
    # position handling: each signal is independent 1-day or hold-until-exit; we simulate EOD exit unless stop/target hit intraday (conservative: stop first)
    for i, (idx, row) in enumerate(df.iterrows()):
        d=idx.normalize()
        if d not in sig_by_date:
            continue
        s=sig_by_date[d]
        # entry is at s.entry (already next open logic inside signal builder, but we re-validate)
        entry=s.entry
        # determine exit: check high/low for stop/target, else close
        # need to look ahead 1..hold days; for simple 1-day strategies, exit = close of same day or open next day for overnight
        # We infer: if signal meta has "exit" (overnight), use it
        if "exit" in s.meta and s.meta["exit"] is not None:
            exit_px=float(s.meta["exit"])
            reason="time"
        else:
            # intraday bar: high/low of entry day
            day_high=float(row["high"])
            day_low=float(row["low"])
            day_close=float(row["close"])
            hit_stop = (s.direction==1 and day_low <= s.stop) or (s.direction==-1 and day_high >= s.stop)
            hit_target = (s.direction==1 and day_high >= s.target) or (s.direction==-1 and day_low <= s.target)
            if hit_stop and hit_target:
                exit_px=s.stop
                reason="stop"
            elif hit_stop:
                exit_px=s.stop
                reason="stop"
            elif hit_target:
                exit_px=s.target
                reason="target"
            else:
                exit_px=day_close
                reason="eod"
        pts=(exit_px - entry)*s.direction
        # sizing
        stop_dist=abs(entry - s.stop)
        if stop_dist==0:
            stop_dist=abs(entry*0.01)
        risk_budget=capital * (risk_per_trade_pct/100)
        per_lot_risk=stop_dist*lot_size
        lots=max(1, int(risk_budget // per_lot_risk))
        cap_lots=max(1, int(capital/1_000_000 * max_lots_per_10l))
        lots=min(lots, cap_lots)
        gross=cost_model.fut_pnl(entry, exit_px, lots, lot_size, s.direction)[0]
        cost=cost_model.fut_cost(entry, exit_px, lots, lot_size)
        # enforce cost calc consistency
        _, c, net = cost_model.fut_pnl(entry, exit_px, lots, lot_size, s.direction)
        trades.append(Trade(date=str(d.date()), symbol=symbol, dir=s.direction, entry=round(entry,2), exit=round(exit_px,2), pts=round(pts,2), lots=lots, cost=c, pnl=net, reason=reason))
    return trades

def perf_stats(trades: list[Trade], capital: float) -> dict:
    if not trades:
        return {"trades":0,"pnl":0,"sharpe":0,"maxDD":0,"win":0,"pf":0,"cagr":0}
    pnl_series=pd.Series([t.pnl for t in trades])
    dates=pd.to_datetime([t.date for t in trades])
    # daily aggregation
    df=pd.DataFrame({"date":dates, "pnl":pnl_series})
    df=df.groupby("date")["pnl"].sum().sort_index()
    # build equity
    eq=(df.cumsum() + capital)
    rets=df/capital
    sharpe=float(rets.mean()/rets.std()*np.sqrt(252)) if rets.std()!=0 else 0
    # max DD
    roll_max=eq.cummax()
    dd=(eq-roll_max)/roll_max
    maxDD=float(dd.min()*100)
    wins=int((df>0).sum())
    win_rate=wins/len(df) if len(df) else 0
    pos=df[df>0].sum()
    neg=-df[df<0].sum()
    pf=float(pos/neg) if neg>0 else (float('inf') if pos>0 else 0)
    total_pnl=float(df.sum())
    years=len(df)/252
    try:
        cagr=float(( (capital+total_pnl)/capital )**(1/years)-1)*100 if years>0 and (capital+total_pnl)>0 else -100.0
    except Exception:
        cagr=-100.0
    return {"trades":len(trades),"days":len(df),"pnl":round(total_pnl,2),"sharpe":round(sharpe,2),"maxDD":round(maxDD,2),"win":round(win_rate*100,1),"pf": round(pf,2) if pf!=float('inf') else 999,"cagr":round(cagr,2),"equity":eq,"daily":df}
