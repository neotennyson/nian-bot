"""Night batch: 5 new daily families x SENSEX/NIFTY, full costs, conviction + OOS. Kills or promotes."""
import pandas as pd, pathlib, itertools, json, math
import numpy as np
from src.core.costs import CostModel
from src.strategies.base import Signal
from src.data.loader import atr, rsi
from src.backtest.engine import run_signals, perf_stats
from src.backtest.walkforward import walk_forward
root=pathlib.Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0, str(root))
costs=CostModel({'brokerage_per_order':20,'fut_stt_sell':0.0005,'exch_fut_nse':0.0000173,'sebi_turnover':0.000001,'stamp_fut_buy':0.00002,'gst_on_charges':0.18,'slippage_fut_pts':1.5})

def conv(s,q):
    sh=float(np.tanh(s['sharpe']/2.0)); dd=max(0,1-abs(s['maxDD'])/50)
    pf=min(1,(s['pf']-1)/1.5) if s['pf']>1 else 0
    cov=min(1,s['trades']/(12*60))
    base=sh*0.28+dd*0.16+pf*0.14+q*0.12+0.85*0.12+cov*0.18
    rel=1.0 if s['trades']>=200 else math.sqrt(max(1,s['trades'])/30)
    return round(base*min(1,rel),3)

def fam_signals(df, fam, p):
    sigs=[]
    a=atr(df,14)
    if fam=='donchian':
        n=p
        for i in range(n, len(df)-1):
            hh=float(df.iloc[i-n:i]['high'].max()); ll=float(df.iloc[i-n:i]['low'].min())
            c=float(df.iloc[i]['close'])
            if c>=hh*0.999: d=1
            elif c<=ll*1.001: d=-1
            else: continue
            e=float(df.iloc[i+1]['open']); av=float(a.iloc[i])
            if pd.isna(av): continue
            av=float(av)
            sigs.append(Signal(date=df.index[i+1], direction=d, entry=e, stop=e-d*av, target=e+d*av*2, meta={}))
    elif fam=='rsi2':
        r=rsi(df['close'],2)
        for i in range(len(df)-1):
            rv=float(r.iloc[i]) if not pd.isna(r.iloc[i]) else 50
            if rv<=p: d=1
            elif rv>=100-p: d=-1
            else: continue
            e=float(df.iloc[i+1]['open']); av=float(a.iloc[i])
            if pd.isna(av): continue
            av=float(av)
            sigs.append(Signal(date=df.index[i+1], direction=d, entry=e, stop=e-d*av, target=e+d*av*1.2, meta={}))
    elif fam=='tom':
        for i in range(len(df)-1):
            d=df.index[i+1]
            # turn-of-month: long last 3 sessions + first 2 of month
            is_tom=(d.day>=25) or (d.day<=2)
            if not is_tom: continue
            e=float(df.iloc[i+1]['open']); av=float(a.iloc[i])
            if pd.isna(av): continue
            av=float(av)
            sigs.append(Signal(date=df.index[i+1], direction=1, entry=e, stop=e-av, target=e+av*1.5, meta={}))
    elif fam=='streak':
        for i in range(p, len(df)-1):
            chg=(df.iloc[i-p+1:i+1]['close'].values > df.iloc[i-p:i]['close'].values)
            if chg.all(): d=-1  # fade p-up streaks
            elif (~chg).all(): d=1  # buy p-down streaks
            else: continue
            e=float(df.iloc[i+1]['open']); av=float(a.iloc[i])
            if pd.isna(av): continue
            av=float(av)
            sigs.append(Signal(date=df.index[i+1], direction=d, entry=e, stop=e-d*av, target=e+d*av*1.5, meta={}))
    elif fam=='orb_daily':
        for i in range(len(df)-1):
            body=float(df.iloc[i]['close']-df.iloc[i]['open']); av=float(a.iloc[i])
            if pd.isna(av): continue
            av=float(av)
            if abs(body)<p*av: continue
            d=1 if body>0 else -1
            e=float(df.iloc[i+1]['open'])
            sigs.append(Signal(date=df.index[i+1], direction=d, entry=e, stop=e-d*av, target=e+d*av*2, meta={}))
    return sigs

out=[]
for sym,lot,parq in [('SENSEX',20,'sensex_daily'),('NIFTY',75,'nifty_daily')]:
    df=pd.read_parquet(root/f'data/raw/{parq}.parquet'); df.index=pd.to_datetime(df.index).normalize()
    for fam,plist in [('donchian',[20,55]),('rsi2',[5,10]),('tom',[0]),('streak',[3,5]),('orb_daily',[0.35,0.5])]:
        for p in plist:
            sigs=fam_signals(df,fam,p)
            tr=run_signals(df,sigs,lot,500000,costs,symbol=sym)
            st=perf_stats(tr,500000)
            d=st['daily']; q=float((d.groupby(pd.Grouper(freq='QE')).sum()>0).mean()) if len(d) else 0
            wf=walk_forward(d) if len(d)>30 else {'oos_sharpe':0}
            out.append({'key':f'{sym} {fam} p={p}','trades':st['trades'],'pnl':st['pnl'],'sharpe':st['sharpe'],'maxDD':st['maxDD'],'oos':wf['oos_sharpe'],'conviction':conv(st,q)})
out=sorted(out,key=lambda x:x['conviction'],reverse=True)
for r in out:
    print(r['conviction'], r['key'], round(r['pnl']), r['sharpe'], r['maxDD'], r['oos'], r['trades'])
pathlib.Path(root/'results/family_sweep.json').write_text(json.dumps(out, indent=1))
print('saved results/family_sweep.json')
