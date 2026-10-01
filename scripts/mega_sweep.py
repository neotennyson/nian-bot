#!/usr/bin/env python3
"""NIAN mega sweep — paper-only, no orders. Full NSE costs, walk-forward OOS.
Overnight 36 combos + gap 9 + equities 30 + intraday ORB 36. Ranks by conviction."""
import sys, pathlib, json, itertools, math
import pandas as pd, numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.core.costs import CostModel
from src.data.loader import atr
from src.strategies.base import Signal
from src.strategies.index_strategies import overnight_drift_signals
from src.strategies.equity_strategies import equity_momentum, equity_rsi2_meanrev, equity_breakout
from src.backtest.engine import run_signals, perf_stats
from src.backtest.walkforward import walk_forward

costs=CostModel({'brokerage_per_order':20,'fut_stt_sell':0.0005,'exch_fut_nse':0.0000173,'sebi_turnover':0.000001,'stamp_fut_buy':0.00002,'gst_on_charges':0.18,'slippage_fut_pts':1.5})
vix=pd.read_parquet(ROOT/'data/raw/indiavix_daily.parquet')['close']
vix.index=pd.to_datetime(vix.index).normalize()

def conviction(s, q_hit):
    sharpe_c=float(np.tanh(s['sharpe']/2.0))
    dd_c=max(0, 1-abs(s['maxDD'])/50)
    pf_c=min(1,(s['pf']-1)/1.5) if s['pf']>1 else 0
    cov=min(1, s['trades']/(12*60))
    base=sharpe_c*0.28+dd_c*0.16+pf_c*0.14+q_hit*0.12+0.85*0.12+cov*0.18
    rel=1.0 if s['trades']>=200 else math.sqrt(s['trades']/30)
    return round(base*min(1,rel),3)

def gap_sigs(df, atr_p, thr):
    a=atr(df,atr_p); sigs=[]
    for i in range(1,len(df)-1):
        av=float(a.iloc[i-1]) if not pd.isna(a.iloc[i-1]) else 0
        if av==0: continue
        gap=float(df.iloc[i]['open']-df.iloc[i-1]['close'])
        if abs(gap)/av < thr: continue
        d=1 if gap>0 else -1
        sigs.append(Signal(date=df.index[i], direction=d, entry=float(df.iloc[i]['open']), stop=float(df.iloc[i]['open']-d*av), target=float(df.iloc[i]['open']+d*av*1.8), meta={}))
    return sigs

results=[]
# 1. OVERNIGHT 36 combos
for sym,lot,parq in [('NIFTY',75,'nifty_daily'),('BANKNIFTY',30,'banknifty_daily'),('SENSEX',20,'sensex_daily')]:
    df=pd.read_parquet(ROOT/f'data/raw/{parq}.parquet'); df.index=pd.to_datetime(df.index).normalize()
    vix_a=vix.reindex(df.index).ffill()
    for gate,lb in itertools.product([15,17,19,21],[21,63,126]):
        sigs=overnight_drift_signals(df, vix_a, gate, lb)
        tr=run_signals(df, sigs, lot, 500000, costs, symbol=sym)
        st=perf_stats(tr,500000)
        daily=st['daily']; q=(daily.groupby(pd.Grouper(freq='QE')).sum()>0).mean() if len(daily) else 0
        wf=walk_forward(daily) if len(daily)>30 else {'oos_sharpe':0}
        last30=float(daily.tail(30).sum()) if len(daily)>=30 else float(daily.sum())
        r={'family':'overnight','key':f'{sym} VIX{gate} H{lb}','trades':st['trades'],'pnl':st['pnl'],'sharpe':st['sharpe'],'maxDD':st['maxDD'],'win':st['win'],'pf':st['pf'],'oos':wf['oos_sharpe'],'last30':round(last30),'q':round(float(q),2),'conviction':conviction(st,float(q))}
        results.append(r)
        print(f"overnight {r['key']:22} pnl ₹{r['pnl']:>9,.0f} sh {r['sharpe']:5.2f} DD {r['maxDD']:6.1f}% oos {r['oos']:5.2f} 30d ₹{r['last30']:>8,.0f} conv {r['conviction']:.3f}")

# 2. GAP 9 combos (SENSEX)
df=pd.read_parquet(ROOT/'data/raw/sensex_daily.parquet'); df.index=pd.to_datetime(df.index).normalize()
for p,thr in itertools.product([10,14,20],[0.5,0.7,1.0]):
    sigs=gap_sigs(df,p,thr)
    tr=run_signals(df, sigs, 20, 500000, costs, symbol='SENSEX')
    st=perf_stats(tr,500000)
    daily=st['daily']; q=(daily.groupby(pd.Grouper(freq='QE')).sum()>0).mean() if len(daily) else 0
    wf=walk_forward(daily) if len(daily)>30 else {'oos_sharpe':0}
    r={'family':'gap','key':f'SENSEX gap ATR{p} thr{thr}','trades':st['trades'],'pnl':st['pnl'],'sharpe':st['sharpe'],'maxDD':st['maxDD'],'win':st['win'],'pf':st['pf'],'oos':wf['oos_sharpe'],'q':round(float(q),2),'conviction':conviction(st,float(q))}
    results.append(r)
    print(f"gap {r['key']:25} pnl ₹{r['pnl']:>9,.0f} sh {r['sharpe']:5.2f} conv {r['conviction']:.3f}")

# 3. EQUITIES 30 combos (10 names x 3)
import pathlib as _pl
eq_names=[f.stem.replace('_daily','').upper() for f in (ROOT/'data'/'raw').glob('*_daily.parquet') if f.stem not in ('nifty_daily','banknifty_daily','sensex_daily','indiavix_daily')]
for sym in sorted(eq_names):
    df=pd.read_parquet(ROOT/f'data/raw/{sym.lower()}_daily.parquet'); df.index=pd.to_datetime(df.index).normalize()
    for fname,fn in [('mom',equity_momentum),('rsi2',equity_rsi2_meanrev),('brk',equity_breakout)]:
        sigs=fn(df)
        tr=run_signals(df, sigs, 1, 500000, costs, symbol=sym)
        st=perf_stats(tr,500000)
        r={'family':'equity','key':f'{sym} {fname}','trades':st['trades'],'pnl':st['pnl'],'sharpe':st['sharpe'],'maxDD':st['maxDD'],'win':st['win'],'pf':st['pf'],'conviction':conviction(st,0.3)}
        results.append(r)
print('equities done, best:', sorted([r for r in results if r['family']=='equity'], key=lambda x: x['sharpe'], reverse=True)[:3])

# rank
ranked=sorted(results, key=lambda x: (x['conviction'], x['sharpe']), reverse=True)
print('\n=== TOP 15 BY CONVICTION ===')
for r in ranked[:15]:
    print(f"{r['conviction']:.3f} {r['family']:9} {r['key']:28} pnl ₹{r['pnl']:>10,.0f} sh {r['sharpe']:5.2f} DD {r['maxDD']:6.1f}% oos {r.get('oos',0):5.2f} 30d ₹{r.get('last30',0):>8,.0f}")
(ROOT/'results'/'mega_sweep.json').write_text(json.dumps({'results':results,'top15':ranked[:15]}, indent=1))
print('\nSaved results/mega_sweep.json with', len(results), 'combos')
