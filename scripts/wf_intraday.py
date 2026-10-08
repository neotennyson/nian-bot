import pandas as pd, pathlib, itertools, json
from src.core.costs import CostModel
root=pathlib.Path(__file__).resolve().parents[1]
costs=CostModel({'brokerage_per_order':20,'fut_stt_sell':0.0005,'exch_fut_nse':0.0000173,'sebi_turnover':0.000001,'stamp_fut_buy':0.00002,'gst_on_charges':0.18,'slippage_fut_pts':1.5})

def orb_trades(df, orb_min, direction, sp, tp, lot):
    tr=[]
    d=df.copy(); d['date']=d.index.date
    for date, day in d.groupby('date'):
        day=day.between_time('09:15','15:30')
        if len(day)<orb_min+10: continue
        oe=day.index[0]+pd.Timedelta(minutes=orb_min)
        ob=day[day.index<=oe]; rest=day[day.index>oe]
        hi=ob['high'].max(); lo=ob['low'].min()
        entry=None
        for idx,row in rest.iterrows():
            c=row['close']
            dd=None
            if direction in ('short','both') and c>hi: dd=-1
            elif direction in ('long','both') and c<lo: dd=1
            if dd is None: continue
            entry=c; et=idx; break
        if entry is None: continue
        stop=entry*(1+sp) if dd==-1 else entry*(1-sp)
        tgt=entry*(1-tp) if dd==-1 else entry*(1+tp)
        ex=None
        for idx,row in rest[rest.index>et].iterrows():
            if idx.time()>=pd.to_datetime('15:18').time(): ex=row['close']; break
            if dd==-1:
                if row['high']>=stop: ex=stop; break
                if row['low']<=tgt: ex=tgt; break
            else:
                if row['low']<=stop: ex=stop; break
                if row['high']>=tgt: ex=tgt; break
        if ex is None: ex=rest.iloc[-1]['close']
        pts=(ex-entry)*dd; gross=pts*lot; cost=costs.fut_cost(entry,ex,1,lot)
        tr.append({'date':str(date),'net':gross-cost})
    return tr

out={}
for sym,lot,parq in [('SENSEX',20,'sensex_1min'),('NIFTY',75,'nifty_1min'),('BANKNIFTY',30,'banknifty_1min')]:
    df=pd.read_parquet(root/f'data/raw/{parq}.parquet'); df.index=pd.to_datetime(df.index); df=df.sort_index()
    days=sorted(set(df.index.date))
    cut=days[int(len(days)*2/3)]
    print(f'=== {sym}: train->{cut} ({len([d for d in days if d<=cut])}d) test {cut}-> ({len([d for d in days if d>cut])}d) ===', flush=True)
    rows=[]
    for direction,orb_min,sp,tp in itertools.product(['short','long','both'],[15,30],[0.003,0.005,0.008],[0.005,0.01,0.015]):
        tr=orb_trades(df,orb_min,direction,sp,tp,lot)
        pn_tr=sum(x['net'] for x in tr if x['date']<=str(cut))
        pn_te=sum(x['net'] for x in tr if x['date']>str(cut))
        n1=sum(1 for x in tr if x['date']<=str(cut)); n2=sum(1 for x in tr if x['date']>str(cut))
        rows.append({'dir':direction,'orb':orb_min,'sp':sp,'tp':tp,'train':round(pn_tr),'test':round(pn_te),'n1':n1,'n2':n2})
    rows=sorted(rows,key=lambda x:x['train'],reverse=True)
    print(' top-3 train -> test:', flush=True)
    for r in rows[:3]:
        print(f"  {r['dir']:5} orb{r['orb']} s{r['sp']} t{r['tp']} train ₹{r['train']:,} ({r['n1']}) -> TEST ₹{r['test']:,} ({r['n2']})", flush=True)
    best_test=sorted(rows,key=lambda x:x['test'],reverse=True)[:2]
    print(' best test:', flush=True)
    for r in best_test:
        print(f"  {r['dir']:5} orb{r['orb']} s{r['sp']} t{r['tp']} train ₹{r['train']:,} -> test ₹{r['test']:,}", flush=True)
    out[sym]=rows
pathlib.Path(root/'results/wf_intraday.json').write_text(json.dumps(out, indent=1))
print('saved results/wf_intraday.json')
