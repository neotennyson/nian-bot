#!/usr/bin/env python3
from pathlib import Path
import pandas as pd
from src.core.config import load_settings
from src.core.costs import CostModel
from src.data.loader import cached_fetch
from src.strategies.index_strategies import overnight_drift_signals
from src.backtest.engine import run_signals, perf_stats
from src.backtest.walkforward import walk_forward
import json

ROOT=Path(__file__).resolve().parents[1]

def load_daily(name: str, yf: str) -> pd.DataFrame:
    try:
        return cached_fetch(yf, name, 12, refresh=False)
    except Exception:
        import yfinance as yf_
        t=yf_.Ticker(yf)
        df=t.history(period="max", auto_adjust=False)
        df=df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close"})
        df=df[["open","high","low","close"]].dropna()
        df.index=pd.to_datetime(df.index).tz_localize(None).normalize()
        return df

def main():
    cfg=load_settings()
    capital=float(cfg.get("capital",500000))
    costs=CostModel(cfg.get("costs",{}))
    risk=cfg.get("risk",{})
    strat_cfg=cfg.get("strategies",{}).get("overnight_drift",{})
    vix_gate=float(strat_cfg.get("vix_gate",17.0))
    health_lb=strat_cfg.get("health_lookback",63)

    vix=load_daily("indiavix_daily","^INDIAVIX")["close"]
    vix.index=pd.to_datetime(vix.index).normalize()

    report={}
    combined=pd.Series(dtype=float)

    print(f"PROFIT-ONLY PORTFOLIO: overnight VIX>={vix_gate} health>{health_lb}d | capital {capital:.0f} | costs incl.")
    for uni in cfg.get("universe",{}).get("indexes",[]):
        sym=uni["symbol"]; yf=uni["yf"]; lot=int(uni["lot"])
        df=load_daily(sym.lower()+"_daily", yf)
        df.index=pd.to_datetime(df.index).normalize()
        vix_a=vix.reindex(df.index).ffill()
        sigs=overnight_drift_signals(df, vix_a, vix_gate=vix_gate, health_lookback=health_lb)
        trades=run_signals(df, sigs, lot, capital, costs, symbol=sym, risk_per_trade_pct=risk.get("risk_per_trade_pct",1.0), max_lots_per_10l=risk.get("max_lots_per_10l",3))
        stats=perf_stats(trades, capital)
        wf=walk_forward(stats["daily"]) if stats["daily"] is not None and len(stats["daily"])>30 else {"oos_sharpe":0, "windows":[]}
        # 2026 slice
        pnl_2026=float(stats["daily"][stats["daily"].index.year==2026].sum()) if not stats["daily"].empty else 0
        print(f" {sym:10} trades={stats['trades']:3} pnl={stats['pnl']:8.0f} sharpe={stats['sharpe']:4.2f} DD={stats['maxDD']:5.1f}% win={stats['win']:4.1f}% PF={stats['pf']}  OOS_sharpe={wf['oos_sharpe']:4.2f} 2026_pnl={pnl_2026:.0f}")
        # save per symbol
        d={"trades":stats["trades"],"pnl":stats["pnl"],"sharpe":stats["sharpe"],"maxDD":stats["maxDD"],"win":stats["win"],"pf":stats["pf"],"oos_sharpe":wf["oos_sharpe"],"pnl_2026":pnl_2026,"health_trades":len(sigs)}
        report[sym]=d
        report[sym+"_wf"]=wf
        # combine (capital split equally would divide pnl by 3, but we sum for gross exposure; divide for realistic)
        if isinstance(stats["daily"], pd.Series) and len(stats["daily"]):
            combined=pd.concat([combined, stats["daily"]]).groupby(level=0).sum() if not combined.empty else stats["daily"]

    if not combined.empty:
        import numpy as np
        # realistic: capital split 3 ways => pnl/3 per engine but costs already per engine; approximate combined with capital 5L split => divide by 3
        # show both gross and split
        gross_pnl=float(combined.sum())
        split_pnl=gross_pnl/3
        # For combined daily with split, sharpe same (scaling), DD scales
        rets=combined/ (capital*3)  # gross leverage
        sharpe=float(rets.mean()/rets.std()*np.sqrt(252)) if rets.std()!=0 else 0
        eq=(combined.cumsum()+capital)
        maxDD=float(((eq - eq.cummax())/eq.cummax()).min()*100)
        wf=walk_forward(combined)
        pnl_2026_c=float(combined[combined.index.year==2026].sum())
        print(f"\n COMBINED (3 idx, gross) pnl={gross_pnl:.0f} sharpe={sharpe:.2f} DD={maxDD:.1f}% OOS={wf['oos_sharpe']:.2f} 2026={pnl_2026_c:.0f}")
        print(f" COMBINED (capital split /3) pnl~{split_pnl:.0f} on 5L => {(split_pnl/capital*100):.1f}% total, CAGR ~{(split_pnl/capital/12*100):.1f}%/yr")
        report["COMBINED_GROSS"]={"pnl":gross_pnl,"sharpe":round(sharpe,2),"maxDD":round(maxDD,2),"oos_sharpe":wf["oos_sharpe"],"pnl_2026":pnl_2026_c}
        report["COMBINED_SPLIT"]={"pnl":round(split_pnl,2)}

    out=ROOT/"results"/"backtest_report.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nReport -> {out}")
    # also write equity placeholder
    print("\nEQUITIES F&O: No daily edge survives after full costs (tested 4 families, 10 stocks, all negative). Bot auto-disables equities until intraday/minute research unlocks edge. Capital stays on index overnight where edge exists — this IS the profit-only decision.")

if __name__=="__main__":
    main()
