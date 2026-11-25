#!/usr/bin/env python3
"""Dhan 1-min backfill for intraday research (paper-only).
Uses live token from src.core.tokens.get_token("dhan")."""
import os, sys, time, pathlib, json, urllib.request, urllib.error
from datetime import datetime, timedelta
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.core.tokens import get_token
os.environ["DHAN_ACCESS_TOKEN"]=get_token("dhan")
os.environ["DHAN_CLIENT_ID"]=os.environ.get("DHAN_CLIENT_ID","YOUR_DHAN_CLIENT_ID")
import pandas as pd

BASE="https://api.dhan.co/v2"

def dhan_post(path, payload):
    tok=os.environ["DHAN_ACCESS_TOKEN"]
    cid=os.environ["DHAN_CLIENT_ID"]
    data=json.dumps(payload).encode()
    req=urllib.request.Request(BASE+path, data=data, headers={"access-token":tok,"client-id":cid,"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def fetch_day(sid, seg, inst, date_str):
    try:
        j=dhan_post("/charts/intraday", {"securityId":sid,"exchangeSegment":seg,"instrument":inst,"interval":"1","oi":False,"fromDate":date_str,"toDate":date_str})
        if not j or "close" not in j: return pd.DataFrame()
        ts=j.get("timestamp",[])
        df=pd.DataFrame({k:j.get(k,[]) for k in ["open","high","low","close","volume"]})
        if ts:
            df.index=pd.to_datetime([datetime.fromtimestamp(t) for t in ts])
        # filter to market hours 09:15-15:30
        if not df.empty:
            df=df.between_time("09:15","15:30")
        return df
    except urllib.error.HTTPError as e:
        body=e.read().decode()[:400] if e.fp else ""
        if e.code==429:
            print(f" 429 wait 10s {body[:100]}")
            time.sleep(10)
            raise
        else:
            print(f" HTTP {e.code} {body[:200]}")
            return pd.DataFrame()
    except Exception as e:
        print(f" fail {e}")
        return pd.DataFrame()

def backfill(symbol,sid,seg,inst,days=90):
    out=ROOT/"data"/"raw"/f"{symbol.lower()}_1min.parquet"
    if out.exists():
        old=pd.read_parquet(out)
        last=old.index.max().date()
        start=last+timedelta(days=1)
        print(f"{symbol} resume {start} had {len(old)} bars")
    else:
        old=pd.DataFrame()
        start=datetime.now().date()-timedelta(days=days)
        print(f"{symbol} fresh {start}")
    end=datetime.now().date()-timedelta(days=1)
    cur=start
    all_df=old
    while cur <= end:
        if cur.weekday()>=5:
            cur+=timedelta(days=1); continue
        ds=cur.strftime("%Y-%m-%d")
        try:
            df=fetch_day(sid,seg,inst,ds)
            if len(df):
                df["symbol"]=symbol
                all_df=pd.concat([all_df,df]) if not all_df.empty else df
                print(f" {ds} {len(df)} bars last {df['close'].iloc[-1]:.1f}")
            else:
                print(f" {ds} empty")
        except Exception as e:
            if "429" not in str(e):
                print(f" {ds} err {e}")
            # retry once after wait already done
            time.sleep(3.5)
            cur+=timedelta(days=1)
            continue
        time.sleep(3.5)
        cur+=timedelta(days=1)
        if len(all_df)>0 and (cur-start).days%10==0:
            all_df=all_df[~all_df.index.duplicated(keep="last")].sort_index()
            all_df.to_parquet(out)
            print(f" checkpoint {len(all_df)} -> {out}")
    if not all_df.empty:
        all_df=all_df[~all_df.index.duplicated(keep="last")].sort_index()
        all_df.to_parquet(out)
        print(f"done {symbol} {len(all_df)} bars {all_df.index.min()}->{all_df.index.max()} -> {out}")
    return out

if __name__=="__main__":
    for sym,sid,seg,inst in [("NIFTY","13","IDX_I","INDEX"),("SENSEX","51","IDX_I","INDEX"),("BANKNIFTY","12","IDX_I","INDEX")]:
        backfill(sym,sid,seg,inst,days=30)
