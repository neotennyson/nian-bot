import streamlit as st
import json, sqlite3
from pathlib import Path
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
import pytz
from src.core.config import load_settings
from src.core.costs import CostModel
from src.paper_trades import load_fills, round_trips, summary

ROOT=Path(__file__).resolve().parents[1]
IST=pytz.timezone("Asia/Kolkata")
st.set_page_config(page_title="NIAN — paper", layout="wide")

st.markdown("""
<style>
.stApp {background:#0b0e14; color:#d1d4dc}
h1,h2,h3 {color:#e8ebf0 !important; font-weight:600 !important}
.small {font-size:11px; color:#787b86}
.num {font-variant-numeric:tabular-nums}
.hero {font-size:52px; font-weight:700; font-variant-numeric:tabular-nums; line-height:1.1}
.banner {background:#132018; border:1px solid #26a69a; border-radius:8px; padding:8px 14px; font-size:13px; font-weight:600; color:#26a69a}
.botcard {background:#11151d; border:1px solid #232a38; border-radius:10px; padding:12px 14px}
.statgrid {display:flex; gap:26px; flex-wrap:wrap; margin:6px 0}
.statgrid div b {font-size:17px; font-variant-numeric:tabular-nums}
section[data-testid="stSidebar"] {background:#11151d}
hr {border-color:#232a38}
div[data-testid="stMetric"] label {color:#787b86 !important; font-size:11px !important; text-transform:uppercase; letter-spacing:.05em}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {font-variant-numeric:tabular-nums}
</style>
""", unsafe_allow_html=True)

cfg=load_settings()
BRAND=cfg.get("branding",{})
BOT=BRAND.get("bot_name", cfg.get("bot_name","NIAN"))
MODEL=BRAND.get("model","Muse Spark 1.3")
mode=cfg.get("execution",{}).get("broker","paper")
capital=float(cfg.get("capital",500000))
now=datetime.now(IST)
lots={u["symbol"]:u["lot"] for u in cfg["universe"]["indexes"]}
costs=CostModel(cfg["costs"])
strat=cfg.get("strategies",{}).get("overnight_drift",{})

# ---------- paper state ----------
fills=load_fills()
trades=round_trips(fills, lots, costs)
s=summary(trades)
today=str(now.date())
tday=trades[pd.to_datetime(trades["exit_time"]).dt.date.astype(str)==today] if len(trades) else trades
today_net=round(float(tday["net"].sum()),2) if len(tday) else 0.0

# heartbeat
alive_txt="loop not seen yet"
try:
    hb=json.loads((ROOT/"logs"/"heartbeat.json").read_text())
    dt=(now - datetime.fromisoformat(hb["ts"])).total_seconds()
    alive_txt=f"bot alive {int(dt)}s ago · last: {hb.get('action')}" if dt<300 else f"bot quiet {int(dt//60)}m (last: {hb.get('action')})"
except Exception:
    pass

# ---------- banner + hero ----------
st.markdown(f"<div class='banner'>🛡 PAPER MODE — all trading is simulated, no real funds at risk · {alive_txt} · {now.strftime('%d %b %H:%M IST')}</div>", unsafe_allow_html=True)
st.markdown(f"### {BOT} — paper P&L")
net_color="#26a69a" if s["net"]>=0 else "#ef5350"
st.markdown(f"<div class='hero' style='color:{net_color}'>₹{s['net']:+,.0f}</div>", unsafe_allow_html=True)
st.markdown(f"<span class='small num'>realised, after all NSE costs · today ₹{today_net:+,.0f} · {s['trades']} closed trades · journal reset 06 Oct (prior archive kept)</span>", unsafe_allow_html=True)
st.markdown(f"""<div class='statgrid'>
<div><span class='small'>TRADES</span><br><b>{s['trades']}</b></div>
<div><span class='small'>WIN RATE</span><br><b>{s['win_rate']}%</b> <span class='small'>{s['wins']}W · {s['losses']}L</span></div>
<div><span class='small'>AVG / TRADE</span><br><b>₹{s['avg']:+,.0f}</b></div>
<div><span class='small'>BEST</span><br><b style='color:#26a69a'>₹{s['best']:+,.0f}</b></div>
<div><span class='small'>WORST</span><br><b style='color:#ef5350'>₹{s['worst']:+,.0f}</b></div>
</div>""", unsafe_allow_html=True)

# ---------- bot cards ----------
def gate(symbol, vg, lb):
    try:
        vix=pd.read_parquet(ROOT/"data/raw/indiavix_daily.parquet")["close"]
        v=float(vix.iloc[-1])
        if v < vg: return False, f"VIX {v:.1f} < {vg:g}"
        df=pd.read_parquet(ROOT/f"data/raw/{symbol.lower()}_daily.parquet")
        df.index=pd.to_datetime(df.index).normalize()
        h=float((df["open"]/df["close"].shift(1)-1).tail(lb).sum())
        return (h>0), (f"armed · VIX {v:.1f}" if h>0 else f"health{lb} {h:+.3f}")
    except Exception as e:
        return False, "no data"

st.markdown("### Bots")
eng_defs=[
    ("SENSEX overnight", "SENSEX · 15:22→09:20", "overnight", ("SENSEX",19.0,21)),
    ("NIFTY overnight", "NIFTY · 15:22→09:20", "overnight", ("NIFTY",19.0,63)),
    ("SENSEX short ORB30", "SENSEX · intraday 09:30–14:30", "intraday", None),
    ("BANKNIFTY long ORB30", "BANKNIFTY · experiment", "intraday", None),
]
cols=st.columns(4)
by_eng=trades.groupby("engine")["net"].agg(["sum","count"]) if len(trades) else None
for col,(name,sub,kind,gate_args) in zip(cols,eng_defs):
    if kind=="overnight":
        ok,reason=gate(*gate_args)
    else:
        ok,reason=(True,"armed in session") if ("09:30" <= now.strftime("%H:%M") <= "14:30") else (False,"outside 09:30–14:30")
    dot="#26a69a" if ok else "#f5a623"
    stat="RUNNING" if ok else "WAITING"
    tnet=tcount="—"
    if by_eng is not None:
        match=[i for i in by_eng.index if name.split()[0] in i and (("overnight" in i)==(kind=="overnight"))]
        if match:
            tnet=f"₹{by_eng.loc[match,'sum'].sum():+,.0f}"; tcount=int(by_eng.loc[match,'count'].sum())
    col.markdown(f"""<div class='botcard'>
<b>{name}</b> <span class='small'>{sub}</span><br>
<span style='color:{dot}'>● {stat}</span> <span class='small'>{reason}</span><br>
<span class='num'><b>{tnet}</b> <span class='small'>{tcount} trades</span></span>
</div>""", unsafe_allow_html=True)

# ---------- paper equity + trade history ----------
st.markdown("### Paper equity")
if len(trades):
    t2=trades.copy(); t2["exit_time"]=pd.to_datetime(t2["exit_time"])
    curve=t2.set_index("exit_time")["net"].cumsum()
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=curve.index, y=curve.values, fill="tozeroy", fillcolor="rgba(38,166,154,.25)",
        line=dict(color="#26a69a", width=1.5), name="Paper P&L", hovertemplate="%{x|%Y-%m-%d}<br>₹%{y:,.0f}"))
    fig.update_layout(height=240, margin=dict(l=8,r=8,t=8,b=8), paper_bgcolor="#0b0e14", plot_bgcolor="#0b0e14",
        font=dict(color="#787b86", size=11), showlegend=False, hovermode="x unified",
        xaxis=dict(gridcolor="#1a2030"), yaxis=dict(gridcolor="#1a2030", tickformat=",.0f"))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.markdown("<span class='small'>No closed paper trades yet since the 06 Oct journal reset — the curve starts with the first closed trade. Bot is waiting for the 15:22 gate.</span>", unsafe_allow_html=True)

st.markdown("### Trade history")
if len(trades):
    h=trades[["exit_time","engine","side","symbol","entry","exit","qty","gross","cost","net"]].copy()
    h.columns=["Time","Bot","Side","Symbol","Entry","Exit","Qty","Gross ₹","Cost ₹","Net ₹"]
    h["Net ₹"]=h["Net ₹"].round(0)
    st.dataframe(h.iloc[::-1].head(50), use_container_width=True, hide_index=True)
else:
    st.markdown("<span class='small'>No completed trades yet. Open paper positions (if any) are below.</span>", unsafe_allow_html=True)

# ---------- sidebar: watchlist + backtest ----------
with st.sidebar:
    st.markdown("**Watchlist**")
    for sym,parq in [("SENSEX","sensex_daily"),("NIFTY","nifty_daily"),("BANKNIFTY","banknifty_daily")]:
        try:
            df=pd.read_parquet(ROOT/f"data/raw/{parq}.parquet")
            c=float(df["close"].iloc[-1]); p=float(df["close"].iloc[-2]); ch=(c-p)/p*100
            st.markdown(f"<span class='num'><b>{sym}</b> {c:,.1f} <span style='color:{'#26a69a' if ch>=0 else '#ef5350'}'>{ch:+.2f}%</span><br><span class='small'>as of {pd.to_datetime(df.index[-1]).date()}</span></span>", unsafe_allow_html=True)
        except Exception:
            pass
    try:
        vix=pd.read_parquet(ROOT/"data/raw/indiavix_daily.parquet")["close"]
        st.markdown(f"<span class='num'><b>VIX</b> {float(vix.iloc[-1]):.2f}</span>", unsafe_allow_html=True)
    except Exception:
        pass
    st.divider()
    st.markdown("**Backtest (12y, costs in)**")
    try:
        pf=json.loads((ROOT/"results/portfolio_2engine.json").read_text())
        st.markdown(f"<span class='num small'>2-engine: ₹{pf['pnl']:,.0f} · Sharpe {pf['sharpe']} · DD {pf['maxDD']}% · OOS {pf['oos']}</span>", unsafe_allow_html=True)
        eq=pd.read_csv(ROOT/"results/portfolio_daily.csv", parse_dates=["date"])
        st.line_chart(eq.set_index("date")["equity"], height=140)
    except Exception as e:
        st.markdown(f"<span class='small'>{e}</span>", unsafe_allow_html=True)

st.divider()
st.markdown(f"<span class='small'>This bot is <b>{BOT}</b> — powered by <b>{MODEL}</b> · paper trading only · past performance ≠ future returns · not financial advice</span>", unsafe_allow_html=True)
