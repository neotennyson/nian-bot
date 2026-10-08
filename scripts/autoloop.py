#!/usr/bin/env python3
"""NIAN autoloop — automated strategy search until a profitable strategy is found.
Paper/research only: NEVER places orders, only writes results/*.json and stages
paper-track candidates in config. Stops when a candidate clears the promotion bar
AND 30 days of paper fills confirm it (checked from logs/paper.db).

Promotion bar (all must hold, full NSE costs):
  - conviction >= 0.60
  - walk-forward OOS Sharpe > 1.0 with >= 20 OOS trades
  - last-30d net > 0
"""
import sys, time, json, pathlib, itertools, math, traceback
from datetime import datetime
import pandas as pd, numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.core.costs import CostModel
from src.data.loader import cached_fetch
from src.strategies.base import Signal
from src.strategies.index_strategies import overnight_drift_signals
from src.backtest.engine import run_signals, perf_stats
from src.backtest.walkforward import walk_forward

BAR={"conviction":0.60,"oos_sharpe":1.0,"oos_trades":20}
SLEEP_SECS=4*3600
MAX_ITERS=200
LOG=ROOT/"logs"/"autoloop.log"

def log(msg):
    line=f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    try:
        with open(LOG,"a") as f: f.write(line+"\n")
    except OSError:
        pass

def conviction(s, q):
    sh=float(np.tanh(s['sharpe']/2.0)); dd=max(0,1-abs(s['maxDD'])/50)
    pf=min(1,(s['pf']-1)/1.5) if s['pf']>1 else 0
    cov=min(1,s['trades']/(12*60))
    base=sh*0.28+dd*0.16+pf*0.14+q*0.12+0.85*0.12+cov*0.18
    rel=1.0 if s['trades']>=200 else math.sqrt(max(1,s['trades'])/30)
    return round(base*min(1,rel),3)

def one_cycle(costs):
    out=[]
    vix=cached_fetch('^INDIAVIX','indiavix_daily',12,False)['close']
    vix.index=pd.to_datetime(vix.index).normalize()
    uni={'SENSEX':(20,'sensex_daily','^BSESN'),'NIFTY':(75,'nifty_daily','^NSEI'),'BANKNIFTY':(30,'banknifty_daily','^NSEBANK')}
    for sym,(lot,parq,yf) in uni.items():
        df=cached_fetch(yf,parq,12,False); df.index=pd.to_datetime(df.index).normalize()
        va=vix.reindex(df.index).ffill()
        for gate,lb in itertools.product([15,17,19,21],[21,63,126]):
            sigs=overnight_drift_signals(df, va, gate, lb)
            tr=run_signals(df, sigs, lot, 500000, costs, symbol=sym)
            st=perf_stats(tr,500000)
            d=st['daily']
            q=float((d.groupby(pd.Grouper(freq='QE')).sum()>0).mean()) if len(d) else 0
            wf=walk_forward(d) if len(d)>30 else {'oos_sharpe':0,'windows':[]}
            oos_trades=sum(w.get('test_days',0) for w in wf.get('windows',[]))
            last30=float(d.tail(30).sum()) if len(d)>=30 else float(d.sum())
            out.append({'key':f'{sym} overnight VIX{gate} H{lb}','trades':st['trades'],'pnl':st['pnl'],
                        'sharpe':st['sharpe'],'maxDD':st['maxDD'],'oos':wf['oos_sharpe'],'oos_trades':oos_trades,
                        'last30':round(last30),'conviction':conviction(st,q)})
    return sorted(out, key=lambda x:(x['conviction'],x['sharpe']), reverse=True)

def paper_confirmed() -> dict:
    try:
        from src.paper_trades import load_fills, round_trips, summary
        from src.core.config import load_settings
        cfg=load_settings()
        lots={u['symbol']:u['lot'] for u in cfg['universe']['indexes']}
        t=round_trips(load_fills(), lots, CostModel(cfg['costs']))
        s=summary(t)
        return {"paper_trades":s["trades"],"paper_net":s["net"]}
    except Exception as e:
        return {"paper_trades":0,"paper_net":0.0,"err":str(e)}

def main():
    it=0
    # cost model refreshed from settings each cycle
    while it < MAX_ITERS:
        it+=1
        try:
            from src.core.config import load_settings
            costs=CostModel(load_settings()['costs'])
            ranked=one_cycle(costs)
            top=ranked[0]
            board={"iter":it,"ts":datetime.now().isoformat(),"bar":BAR,"top":ranked[:10],
                   "paper":paper_confirmed(),"promoted":None}
            for r in ranked:
                if r['conviction']>=BAR['conviction'] and r['oos']>BAR['oos_sharpe'] and r['oos_trades']>=BAR['oos_trades'] and r['last30']>0:
                    board["promoted"]=r
                    break
            (ROOT/'results'/'leaderboard.json').write_text(json.dumps(board, indent=1))
            p=board["promoted"]
            if p:
                pc=paper_confirmed()
                log(f"iter {it}: promoter {p['key']} conv {p['conviction']} oos {p['oos']} last30 ₹{p['last30']:,.0f} | paper {pc['paper_trades']} trades ₹{pc['paper_net']:,.0f}")
                if pc['paper_trades']>=20 and pc['paper_net']>0:
                    log(f"GOAL REACHED: {p['key']} clears backtest bar AND paper confirms (₹{pc['paper_net']:,.0f} over {pc['paper_trades']} fills). Stopping.")
                    break
            else:
                log(f"iter {it}: no promoter. best {top['key']} conv {top['conviction']} oos {top['oos']} last30 ₹{top['last30']:,.0f}")
        except Exception:
            log(f"iter {it} ERROR:\n{traceback.format_exc()}")
        time.sleep(SLEEP_SECS)
    log(f"autoloop ended after {it} iters")

if __name__=="__main__":
    main()
