from __future__ import annotations
import sqlite3
from pathlib import Path
import pandas as pd
from src.core.costs import CostModel

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/"logs"/"paper.db"

def load_fills(db: Path | None=None, include_verify: bool=False) -> pd.DataFrame:
    db=db or DB
    con=sqlite3.connect(str(db))
    try:
        df=pd.read_sql("SELECT ts, symbol, side, qty, price, tag FROM fills ORDER BY ts", con)
    finally:
        con.close()
    if not include_verify:
        df=df[~df["tag"].str.endswith("_verify", na=False)]
    df["ts"]=pd.to_datetime(df["ts"])
    return df.reset_index(drop=True)

def engine_of(tag: str, symbol: str) -> str:
    t=(tag or "").replace("_verify","")
    if t.startswith("intraday_orb_banknifty_long"):
        return "BANKNIFTY long ORB30"
    if t.startswith("intraday_orb_short") or t.startswith("intraday_orb"):
        return "SENSEX short ORB30"
    if "overnight" in t:
        return f"{symbol} overnight"
    if t.startswith("paper_24min"):
        return f"{symbol} intraday"
    return f"{symbol} other"

def round_trips(df: pd.DataFrame, lot_of: dict[str,int], costs: CostModel) -> pd.DataFrame:
    """FIFO pair fills per symbol into round-trip trades with net P&L after full costs."""
    trades=[]
    open_lots: dict[str, list] = {}
    for _, r in df.iterrows():
        sym=r["symbol"]; side=r["side"].upper(); qty=int(r["qty"]); px=float(r["price"])
        book=open_lots.setdefault(sym, [])
        # net direction of open book
        net=sum(q if s=="BUY" else -q for q,_,s,_,_ in book)
        closing = (net > 0 and side=="SELL") or (net < 0 and side=="BUY")
        if not closing:
            book.append([qty, px, side, r["ts"], r["tag"]])
            continue
        remain=qty
        while remain > 0 and book:
            oq, opx, oside, ots, otag=book[0]
            # only match opposite side
            if (oside=="BUY") == (side=="BUY"):
                break
            m=min(oq, remain)
            lot=lot_of.get(sym, 1)
            lots=max(1, m // lot)
            if oside=="BUY":
                entry, exit_=opx, px
                direction=1
            else:
                entry, exit_=px, opx
                direction=-1
            gross, cost, net_=costs.fut_pnl(entry, exit_, lots, lot, direction)
            trades.append({
                "symbol": sym, "engine": engine_of(f"{otag}|{r['tag']}", sym),
                "side": "LONG" if direction==1 else "SHORT",
                "entry_time": ots, "exit_time": r["ts"],
                "entry": entry, "exit": exit_, "qty": m,
                "gross": gross, "cost": cost, "net": net_,
            })
            oq-=m; remain-=m
            if oq<=0:
                book.pop(0)
            else:
                book[0][0]=oq
        if remain > 0:
            book.append([remain, px, side, r["ts"], r["tag"]])
    t=pd.DataFrame(trades)
    if len(t):
        t=t.sort_values("exit_time").reset_index(drop=True)
    return t

def summary(t: pd.DataFrame) -> dict:
    if t is None or len(t)==0:
        return {"trades":0,"net":0.0,"win_rate":0.0,"best":0.0,"worst":0.0,"avg":0.0,"wins":0,"losses":0}
    return {
        "trades": int(len(t)),
        "net": round(float(t["net"].sum()),2),
        "win_rate": round(float((t["net"]>0).mean()*100),1),
        "best": round(float(t["net"].max()),2),
        "worst": round(float(t["net"].min()),2),
        "avg": round(float(t["net"].mean()),2),
        "wins": int((t["net"]>0).sum()),
        "losses": int((t["net"]<=0).sum()),
    }

def open_positions(df: pd.DataFrame) -> pd.DataFrame:
    """Net open qty per symbol from unpaired fills."""
    if len(df)==0:
        return pd.DataFrame(columns=["symbol","qty","avg"])
    rows=[]
    for sym,g in df.groupby("symbol"):
        q=sum(r["qty"] if r["side"]=="BUY" else -r["qty"] for _,r in g.iterrows())
        if q==0:
            continue
        same=g[((g["side"]=="BUY")==(q>0))]
        avg=(same["qty"]*same["price"]).sum()/same["qty"].sum() if len(same) else 0
        rows.append({"symbol":sym,"qty":int(q),"avg":round(float(avg),2),
                     "last_ts": str(g["ts"].max()), "last_tag": g.iloc[-1]["tag"]})
    return pd.DataFrame(rows)
