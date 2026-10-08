import pandas as pd, pathlib, itertools
from src.core.costs import CostModel
root=pathlib.Path(__file__).resolve().parents[1]
costs=CostModel({'brokerage_per_order':20,'fut_stt_sell':0.0005,'exch_fut_nse':0.0000173,'sebi_turnover':0.000001,'stamp_fut_buy':0.00002,'gst_on_charges':0.18,'slippage_fut_pts':1.5})

def day_range(df):
    d=df.copy(); d['date']=d.index.date
    return d.groupby('date').apply(lambda x: float(x['high'].max()-x['low'].min()), include_groups=False)

def orb_trades(df, orb_min, sp, tp, lot, range_filter=None, range_med=None):
    tr=[]
    d=df.copy(); d['date']=d.index.date
    for date, day in d.groupby('date'):
        day=day.between_time('09:15','15:30')
        if len(day)<orb_min+10: continue
        if range_filter=='expand':
            # morning range (09:15-11:00) vs median morning range
            morn=day.between_time('09:15','11:00')
            mr=float(morn['high'].max()-morn['low'].min())
            if mr < range_med: continue
        oe=day.index[0]+pd.Timedelta(minutes=orb_min)
        ob=day[day.index<=oe]; rest=day[day.index>oe]
        hi=ob['high'].max()
        entry=None
        for idx,row in rest.iterrows():
            if row['close']>hi: entry=row['close']; et=idx; break
        if entry is None: continue
        stop=entry*(1+sp); tgt=entry*(1-tp)
        ex=None
        for idx,row in rest[rest.index>et].iterrows():
            if idx.time()>=pd.to_datetime('15:18').time(): ex=row['close']; break
            if row['high']>=stop: ex=stop; break
            if row['low']<=tgt: ex=tgt; break
        if ex is None: ex=rest.iloc[-1]['close']
        pts=entry-ex; gross=pts*lot; cost=costs.fut_cost(entry,ex,1,lot)
        tr.append({'date':str(date),'net':gross-cost})
    return tr

for sym,lot,parq in [('SENSEX',20,'sensex_1min'),('BANKNIFTY',30,'banknifty_1min')]:
    df=pd.read_parquet(root/f'data/raw/{parq}.parquet'); df.index=pd.to_datetime(df.index); df=df.sort_index()
    # median morning range over full panel
    dd=df.copy(); dd['date']=dd.index.date
    morning_ranges=dd.groupby('date').apply(lambda x: float(x.between_time('09:15','11:00')['high'].max()-x.between_time('09:15','11:00')['low'].min()), include_groups=False)
    med=float(morning_ranges.median())
    print(f'=== {sym} median morning range {med:.1f} ===')
    for orb_min,sp,tp in [(30,0.003,0.005),(30,0.003,0.01)]:
        base=orb_trades(df,orb_min,sp,tp,lot)
        filt=orb_trades(df,orb_min,sp,tp,lot,'expand',med)
        pb=sum(x['net'] for x in base); pf=sum(x['net'] for x in filt)
        print(f' orb{orb_min} s{sp} t{tp}: no-filter ₹{pb:,.0f} ({len(base)}) vs expand-only ₹{pf:,.0f} ({len(filt)})')

# calm-only inverse test
if __name__ == '__main__2__':
    pass
