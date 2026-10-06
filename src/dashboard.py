import streamlit as st
import json, sqlite3
from pathlib import Path
from datetime import datetime, time as dtime
import pandas as pd
import plotly.graph_objects as go
import pytz
from src.core.config import load_settings

ROOT=Path(__file__).resolve().parents[1]
IST=pytz.timezone("Asia/Kolkata")
st.set_page_config(page_title="NIAN", layout="wide")

st.markdown("""
<style>
.stApp {background:#131722; color:#d1d4dc}
h1,h2,h3 {color:#e8ebf0 !important; font-weight:600 !important}
.small {font-size:11px; color:#787b86}
.num {font-variant-numeric:tabular-nums}
div[data-testid="stMetric"] label {color:#787b86 !important; font-size:11px !important; text-transform:uppercase; letter-spacing:.05em}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {font-variant-numeric:tabular-nums}
section[data-testid="stSidebar"] {background:#1c2230}
hr {border-color:#2a2e39}
</style>
""", unsafe_allow_html=True)

cfg=load_settings()
BRAND=cfg.get("branding",{})
BOT=BRAND.get("bot_name", cfg.get("bot_name","NIAN"))
MODEL=BRAND.get("model","Muse Spark 1.3")
mode=cfg.get("execution",{}).get("broker","paper")
risk=cfg.get("risk",{})
strat=cfg.get("strategies",{}).get("overnight_drift",{})
capital=float(cfg.get("capital",500000))
now=datetime.now(IST)

# ---------- data ----------
pf=json.loads((ROOT/"results/portfolio_2engine.json").read_text())
eq=pd.read_csv(ROOT/"results/portfolio_daily.csv", parse_dates=["date"])
vix=pd.read_parquet(ROOT/"data/raw/indiavix_daily.parquet")["close"]
vix_last=float(vix.iloc[-1]); vix_date=pd.to_datetime(vix.index[-1]).date()
rs={"realized_today":0.0,"realized_week":0.0}
try:
    rs=json.loads((ROOT/"logs"/"risk_state.json").read_text())
except Exception:
    pass

def health(symbol, lb):
    try:
        df=pd.read_parquet(ROOT/f"data/raw/{symbol.lower()}_daily.parquet")
        df.index=pd.to_datetime(df.index).normalize()
        return float((df["open"]/df["close"].shift(1)-1).tail(lb).sum())
    except Exception:
        return float("nan")

# ---------- status line ----------
eng_states=[]
for eng in strat.get("engines",[]):
    s=eng["symbol"]; g=float(eng["vix_gate"]); lb=int(eng["health_lookback"])
    h=health(s, lb)
    if vix_last < g:
        eng_states.append((s, False, f"VIX {vix_last:.1f}<{g:g}"))
    elif not (h > 0):
        eng_states.append((s, False, f"health{lb} {h:+.3f}"))
    else:
        eng_states.append((s, True, f"armed VIX {vix_last:.1f} health {h:+.3f}"))
blocked=[f"{s} ({r})" for s,ok,r in eng_states if not ok]
armed=[s for s,ok,_ in eng_states if ok]
in_session=dtime(9,15) <= now.time() <= dtime(15,30)
if armed and in_session:
    status=f"ARMED — {', '.join(armed)} can enter at 15:22"
elif not in_session:
    status="MARKET CLOSED — next decision tomorrow 15:22"
else:
    status="FLAT — " + "; ".join(blocked)
st.markdown(f"**{BOT}** · {'PAPER' if mode=='paper' else 'LIVE'} · {status} · {now.strftime('%d %b %H:%M IST')}", unsafe_allow_html=True)
st.divider()

# ---------- overview: 4 key stats, TV strategy-tester style ----------
total=pf["pnl"]
c1,c2,c3,c4=st.columns(4)
c1.metric("Total P&L", f"₹{total:+,.0f}", f"{total/capital*100:+.1f}% of capital")
c2.metric("Max drawdown", f"{pf['maxDD']:.1f}%")
c3.metric("Profitable (trade-days)", f"{(eq['daily_pnl']>0).mean()*100:.1f}%", f"{(eq['daily_pnl']>0).sum()}/{len(eq)} days")
c4.metric("Today (paper)", f"₹{float(rs.get('realized_today',0.0)):+,.0f}", f"week ₹{float(rs.get('realized_week',0.0)):+,.0f}")

# ---------- equity + drawdown ----------
roll=eq["equity"].cummax()
dd=(eq["equity"]-roll)/roll*100
fig=go.Figure()
fig.add_trace(go.Scatter(x=eq["date"], y=eq["equity"], fill="tozeroy", fillcolor="rgba(38,166,154,.25)",
                         line=dict(color="#26a69a", width=1.5), name="Equity", hovertemplate="%{x|%Y-%m-%d}<br>₹%{y:,.0f}"))
fig.update_layout(height=300, margin=dict(l=8,r=8,t=8,b=8), paper_bgcolor="#131722", plot_bgcolor="#131722",
                  font=dict(color="#787b86", size=11), showlegend=False, hovermode="x unified",
                  xaxis=dict(gridcolor="#1c2230", showgrid=True), yaxis=dict(gridcolor="#1c2230", tickformat=",.0f"))
st.plotly_chart(fig, use_container_width=True)
fig2=go.Figure()
fig2.add_trace(go.Scatter(x=eq["date"], y=dd, fill="tozeroy", fillcolor="rgba(239,83,80,.3)",
                          line=dict(color="#ef5350", width=1), name="Drawdown %", hovertemplate="%{x|%Y-%m-%d}<br>%{y:.1f}%"))
fig2.update_layout(height=110, margin=dict(l=8,r=8,t=8,b=8), paper_bgcolor="#131722", plot_bgcolor="#131722",
                   font=dict(color="#787b86", size=11), showlegend=False, hovermode="x unified",
                   xaxis=dict(gridcolor="#1c2230"), yaxis=dict(gridcolor="#1c2230", ticksuffix="%"))
st.plotly_chart(fig2, use_container_width=True)

# ---------- monthly returns ----------
eq["ym"]=eq["date"].dt.to_period("M").astype(str)
m=eq.groupby("ym")["daily_pnl"].sum().tail(12)
st.markdown("Monthly net (₹) — last 12 trade-months")
mcols=st.columns(6)
for i,(ym,v) in enumerate(m.items()):
    with mcols[i % 6]:
        color="#26a69a" if v>=0 else "#ef5350"
        st.markdown(f"<span class='small'>{ym}</span><br><span class='num' style='color:{color}; font-size:15px'>₹{v:+,.0f}</span>", unsafe_allow_html=True)

st.divider()
# ---------- positions (Kite-style) + fills ----------
t1,t2=st.tabs(["Positions & fills", "Engines & backtest"])
with t1:
    try:
        con=sqlite3.connect(str(ROOT/"logs"/"paper.db"))
        fills=pd.read_sql("SELECT ts, symbol, side, qty, price, tag FROM fills ORDER BY ts", con)
    except Exception as e:
        fills=pd.DataFrame()
        st.markdown(f"<span class='small'>journal unavailable: {e}</span>", unsafe_allow_html=True)
    if len(fills):
        pos=[]
        for sym,g in fills.groupby("symbol"):
            q=sum(r["qty"] if r["side"]=="BUY" else -r["qty"] for _,r in g.iterrows())
            if q==0: continue
            buys=g[g["side"]=="BUY"]; avg=(buys["qty"]*buys["price"]).sum()/buys["qty"].sum() if len(buys) else 0
            try:
                ltp=float(pd.read_parquet(ROOT/f"data/raw/{sym.lower()}_daily.parquet")["close"].iloc[-1])
            except Exception:
                ltp=avg
            lot=next((u["lot"] for u in cfg["universe"]["indexes"] if u["symbol"]==sym), 1)
            upnl=(ltp-avg)*(1 if q>0 else -1)*abs(q)
            pos.append({"symbol":sym,"qty":q,"avg":round(avg,1),"ltp":round(ltp,1),"unreal":round(upnl)})
        if pos:
            st.markdown("**Open positions (paper)** <span class='small'>· LTP = last daily close, indicative only</span>", unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(pos), use_container_width=True, hide_index=True)
        else:
            st.markdown("FLAT — no open paper positions. <span class='small'>Correct when gates block.</span>", unsafe_allow_html=True)
        st.markdown("**Journal (latest)**")
        st.dataframe(fills.tail(15).iloc[::-1], use_container_width=True, hide_index=True)
    else:
        st.markdown("<span class='small'>no fills yet</span>", unsafe_allow_html=True)
with t2:
    rows=[]
    for eng in strat.get("engines",[]):
        s=eng["symbol"]
        ok,reason=next(((o,r) for x,o,r in eng_states if x==s), (False,""))
        rows.append({"engine":f"{s} overnight","gate":f"VIX≥{eng['vix_gate']} H{eng['health_lookback']}","state":"ARMED" if ok else "BLOCKED","why":reason})
    rows.append({"engine":"SENSEX short ORB30","gate":"intraday 09:30–14:30","state":"ARMED","why":"paper-tracked"})
    rows.append({"engine":"BANKNIFTY long ORB30","gate":"experiment","state":"WATCH","why":"16 trades — unpromoted"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    rp=ROOT/"results"/"backtest_report.json"
    if rp.exists():
        data=json.loads(rp.read_text())
        r2=[{"symbol":k,"trades":v.get("trades"),"pnl":v.get("pnl"),"sharpe":v.get("sharpe"),"dd%":v.get("maxDD"),"oos":v.get("oos_sharpe")}
            for k,v in data.items() if not k.startswith("COMBINED") and not k.endswith("_wf")]
        st.dataframe(pd.DataFrame(r2), use_container_width=True, hide_index=True)

# ---------- sidebar ----------
with st.sidebar:
    st.markdown("**Watchlist**")
    for sym,parq in [("SENSEX","sensex_daily"),("NIFTY","nifty_daily"),("BANKNIFTY","banknifty_daily")]:
        try:
            df=pd.read_parquet(ROOT/f"data/raw/{parq}.parquet")
            c=float(df["close"].iloc[-1]); p=float(df["close"].iloc[-2]); ch=(c-p)/p*100
            st.markdown(f"<span class='num'><b>{sym}</b> {c:,.1f} <span style='color:{'#26a69a' if ch>=0 else '#ef5350'}'>{ch:+.2f}%</span><br><span class='small'>as of {pd.to_datetime(df.index[-1]).date()}</span></span>", unsafe_allow_html=True)
        except Exception:
            pass
    st.markdown(f"<span class='num'><b>VIX</b> {vix_last:.2f} <span class='small'>{vix_date}</span></span>", unsafe_allow_html=True)
    st.divider()
    st.markdown(f"<span class='small'>risk/trade {risk.get('risk_per_trade_pct',1)}% · kill −{risk.get('daily_loss_kill_pct',2)}%/−{risk.get('weekly_loss_kill_pct',4)}%<br>costs: ₹20/order + STT + exch + GST + 1.5pt slip</span>", unsafe_allow_html=True)

st.divider()
st.markdown(f"<span class='small'>This bot is <b>{BOT}</b> — powered by <b>{MODEL}</b> · paper trading only · past performance ≠ future returns · not financial advice</span>", unsafe_allow_html=True)
