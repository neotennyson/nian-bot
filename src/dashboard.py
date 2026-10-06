import streamlit as st
import json, sqlite3
from pathlib import Path
from datetime import datetime
import pandas as pd
import pytz
from src.core.config import load_settings

ROOT=Path(__file__).resolve().parents[1]
IST=pytz.timezone("Asia/Kolkata")
st.set_page_config(page_title="NIAN — Terminal", layout="wide", page_icon="◈")

st.markdown("""
<style>
.stApp {background:#131722; color:#d1d4dc; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
h1,h2,h3 {color:#e8ebf0 !important; font-weight:600 !important; font-size:13px !important; letter-spacing:.06em; text-transform:uppercase}
.small {font-size:11px; color:#787b86}
.num {font-variant-numeric:tabular-nums}
.pos {color:#26a69a} .neg {color:#ef5350} .warn {color:#f5a623}
div[data-testid="stMetric"] {background:transparent; border:none; padding:0}
div[data-testid="stMetric"] label {color:#787b86 !important; font-size:11px !important; text-transform:uppercase; letter-spacing:.05em}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {font-size:22px !important; font-variant-numeric:tabular-nums; color:#e8ebf0 !important}
.badge {display:inline-block; padding:3px 12px; border-radius:4px; font-size:12px; font-weight:600}
.badge-paper {border:1px solid #26a69a; color:#26a69a}
.badge-live {border:1px solid #ef5350; color:#ef5350}
.dot {display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px}
.dot-g {background:#26a69a} .dot-r {background:#ef5350} .dot-y {background:#f5a623}
section[data-testid="stSidebar"] {background:#1c2230}
hr {border-color:#2a2e39; margin:14px 0}
a {color:#2962ff}
</style>
""", unsafe_allow_html=True)

cfg=load_settings()
BRAND=cfg.get("branding",{})
BOT=BRAND.get("bot_name", cfg.get("bot_name","NIAN"))
MODEL=BRAND.get("model","Muse Spark 1.3")
mode=cfg.get("execution",{}).get("broker","paper")
now=datetime.now(IST)
pf=json.loads((ROOT/"results/portfolio_2engine.json").read_text())

# ---------- sidebar: watchlist ----------
with st.sidebar:
    st.markdown(f"## ◈ {BOT}")
    st.markdown(f"<span class='badge {'badge-paper' if mode=='paper' else 'badge-live'}>{'● PAPER' if mode=='paper' else '● LIVE'}</span>", unsafe_allow_html=True)
    st.markdown("### Watchlist")
    try:
        for sym, parq in [("SENSEX","sensex_daily"),("NIFTY","nifty_daily"),("BANKNIFTY","banknifty_daily")]:
            df=pd.read_parquet(ROOT/f"data/raw/{parq}.parquet")
            c=float(df["close"].iloc[-1]); p=float(df["close"].iloc[-2])
            ch=(c-p)/p*100
            cls="pos" if ch>=0 else "neg"
            st.markdown(f"<span class='num'><b>{sym}</b> {c:,.1f} <span class='{cls}'>{ch:+.2f}%</span><br><span class='small'>as of {pd.to_datetime(df.index[-1]).date()}</span></span>", unsafe_allow_html=True)
        vix=pd.read_parquet(ROOT/"data/raw/indiavix_daily.parquet")["close"]
        st.markdown(f"<span class='num'><b>VIX</b> {float(vix.iloc[-1]):.2f} <span class='small'>{pd.to_datetime(vix.index[-1]).date()}</span></span>", unsafe_allow_html=True)
    except Exception as e:
        st.markdown(f"<span class='small'>quotes unavailable: {e}</span>", unsafe_allow_html=True)
    st.markdown("### Session")
    st.markdown(f"<span class='num small'>IST {now.strftime('%d %b %H:%M')}<br>09:15–15:30 · square 15:18<br>kill −2% day / −4% week</span>", unsafe_allow_html=True)

# ---------- header KPIs ----------
k1,k2,k3,k4,k5,k6=st.columns(6)
k1.metric("Total P&L", f"₹{pf['pnl']:,.0f}")
k2.metric("Sharpe", f"{pf['sharpe']:.2f}")
k3.metric("Max DD", f"{pf['maxDD']:.1f}%")
y2026=float(pf.get("yearly",{}).get("2026",0))
k4.metric("2026", f"₹{y2026:+,.0f}")
try:
    rs=json.loads((ROOT/"logs"/"risk_state.json").read_text())
    rt=float(rs.get("realized_today",0.0))
except Exception:
    rt=0.0
k5.metric("Today (paper)", f"₹{rt:+,.0f}")
k6.metric("Capital", f"₹{cfg.get('capital',500000):,.0f}")

# ---------- equity chart ----------
st.markdown("### Equity curve — 2-engine portfolio")
try:
    eq=pd.read_csv(ROOT/"results/portfolio_daily.csv", parse_dates=["date"])
    st.area_chart(eq.set_index("date")["equity"], height=300)
    st.markdown(f"<span class='small num'>530 trade-days · {eq.iloc[0]['date'].date()} → {eq.iloc[-1]['date'].date()} · net of all NSE costs</span>", unsafe_allow_html=True)
except Exception as e:
    st.markdown(f"<span class='small'>chart unavailable: {e}</span>", unsafe_allow_html=True)

# ---------- engines ----------
st.markdown("### Engines")
def gate_state(symbol, vix_gate, lb):
    try:
        vix=pd.read_parquet(ROOT/"data/raw/indiavix_daily.parquet")["close"]
        v=float(vix.iloc[-1])
        if v < vix_gate:
            return False, f"VIX {v:.1f} < {vix_gate}"
        df=pd.read_parquet(ROOT/f"data/raw/{symbol.lower()}_daily.parquet")
        df.index=pd.to_datetime(df.index).normalize()
        ov=(df["open"]/df["close"].shift(1)-1).tail(lb).sum()
        if ov <= 0:
            return False, f"health{lb} {ov:+.3f} ≤ 0"
        return True, f"VIX {v:.1f} · health{lb} {ov:+.3f}"
    except Exception as e:
        return False, f"data: {e}"

e1,e2,e3,e4=st.columns(4)
for col, name, desc, stt in [
    (e1, "SENSEX overnight", "VIX≥19 · H21 · 15:22→09:20", gate_state("SENSEX",19,21)),
    (e2, "NIFTY overnight", "VIX≥19 · H63 · 15:22→09:20", gate_state("NIFTY",19,63)),
    (e3, "SENSEX short ORB30", "intraday 09:30–14:30", (True, "always armed in session")),
    (e4, "BANKNIFTY long ORB30", "experiment · unpromoted", (True, "paper-tracked only")),
]:
    ok, reason=stt
    col.markdown(f"<span class='dot dot-{'g' if ok else 'r'}'></span><b>{name}</b><br><span class='small'>{desc}<br>{reason}</span>", unsafe_allow_html=True)

# ---------- tabs for detail ----------
tab1, tab2 = st.tabs(["Positions & fills", "Backtest"])
with tab1:
    db=ROOT/"logs"/"paper.db"
    try:
        con=sqlite3.connect(str(db))
        df=pd.read_sql("SELECT ts, symbol, side, qty, price, tag FROM fills ORDER BY ts DESC LIMIT 25", con)
        if len(df): st.dataframe(df, use_container_width=True, hide_index=True)
        else: st.markdown("<span class='small'>no fills yet</span>", unsafe_allow_html=True)
    except Exception as e:
        st.markdown(f"<span class='small'>db read failed: {e}</span>", unsafe_allow_html=True)
with tab2:
    rp=ROOT/"results"/"backtest_report.json"
    data=json.loads(rp.read_text())
    rows=[{"symbol":k,"trades":v.get("trades"),"pnl":v.get("pnl"),"sharpe":v.get("sharpe"),"dd%":v.get("maxDD"),"win%":v.get("win"),"oos":v.get("oos_sharpe"),"2026":v.get("pnl_2026")}
          for k,v in data.items() if not k.startswith("COMBINED") and not k.endswith("_wf")]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.divider()
st.markdown(f"""
<div style="text-align:center; padding:12px 8px; border:1px solid #2a2e39; border-radius:6px;">
  <div style="font-size:14px; font-weight:600; color:#e8ebf0;">◈ {BOT}</div>
  <div style="font-size:12px; color:#d1d4dc; margin-top:4px;">This bot is <b>{BOT}</b> — powered by <b>{MODEL}</b></div>
  <div class="small" style="margin-top:6px;">Paper trading only · past performance ≠ future returns · SEBI: 93% of retail F&O traders lose money · Not financial advice</div>
</div>
""", unsafe_allow_html=True)
