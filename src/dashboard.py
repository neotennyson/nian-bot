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

# TradingView/Kite-dark inspired: flat surfaces, tabular numbers, two signal colors
st.markdown("""
<style>
.stApp {background:#131722; color:#d1d4dc; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
h1,h2,h3 {color:#e8ebf0 !important; font-weight:600 !important; font-size:15px !important; letter-spacing:.04em; text-transform:uppercase; margin:0}
.small {font-size:11px; color:#787b86}
.num {font-variant-numeric:tabular-nums; font-feature-settings:"tnum"}
.pos {color:#26a69a} .neg {color:#ef5350} .warn {color:#f5a623}
div[data-testid="stMetric"] {background:#1c2230; border:1px solid #2a2e39; border-radius:6px; padding:8px 12px}
div[data-testid="stMetric"] label {color:#787b86 !important; font-size:11px !important; text-transform:uppercase; letter-spacing:.05em}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {font-size:19px !important; font-variant-numeric:tabular-nums}
.badge-paper {background:#1c2230; border:1px solid #26a69a; color:#26a69a; padding:3px 12px; border-radius:4px; font-size:12px; font-weight:600}
.badge-live {background:#1c2230; border:1px solid #ef5350; color:#ef5350; padding:3px 12px; border-radius:4px; font-size:12px; font-weight:600}
.stTabs [data-baseweb="tab"] {color:#787b86} .stTabs [aria-selected="true"] {color:#e8ebf0 !important}
hr {border-color:#2a2e39}
a {color:#2962ff}
</style>
""", unsafe_allow_html=True)

cfg=load_settings()
BRAND=cfg.get("branding",{})
BOT=BRAND.get("bot_name", cfg.get("bot_name","NIAN"))
MODEL=BRAND.get("model","Muse Spark 1.3")
risk=cfg.get("risk",{})
strat=cfg.get("strategies",{}).get("overnight_drift",{})
mode=cfg.get("execution",{}).get("broker","paper")
now=datetime.now(IST)

# ---- top bar ----
t1,t2,t3,t4,t5=st.columns([2,2,2,2,3])
t1.markdown(f"## ◈ {BOT} <span class='small'>/ NSE F&O · paper</span>", unsafe_allow_html=True)
t2.markdown(f"<span class='{'badge-paper' if mode=='paper' else 'badge-live'}'>{'● PAPER' if mode=='paper' else '● LIVE — '+mode.upper()}</span> <span class='small'>no real orders in paper</span>", unsafe_allow_html=True)
t3.metric("Capital", f"₹{cfg.get('capital',500000):,.0f}")
# risk state
rs={"realized_today":0.0,"realized_week":0.0}
try:
    rs=json.loads((ROOT/"logs"/"risk_state.json").read_text())
except Exception:
    pass
rt=float(rs.get("realized_today",0.0)); rw=float(rs.get("realized_week",0.0))
t4.metric("Realized today", f"₹{rt:+,.0f}", delta=None)
t5.metric("IST", now.strftime("%d %b %H:%M"), f"week ₹{rw:+,.0f}")

st.divider()
# ---- gates + tokens ----
g1,g2,g3=st.columns(3)
with g1:
    st.markdown("### Gates")
    try:
        vix=pd.read_parquet(ROOT/"data/raw/indiavix_daily.parquet")["close"]
        st.markdown(f"<span class='num'>INDIA VIX <b>{float(vix.iloc[-1]):.2f}</b> <span class='small'>({pd.to_datetime(vix.index[-1]).date()})</span></span>", unsafe_allow_html=True)
    except Exception as e:
        st.markdown(f"<span class='warn'>VIX unavailable</span> <span class='small'>{e}</span>", unsafe_allow_html=True)
    for eng in strat.get("engines",[]):
        st.markdown(f"<span class='num'>{eng.get('symbol')}: VIX≥{eng.get('vix_gate')} · health{eng.get('health_lookback')}d</span>", unsafe_allow_html=True)
with g2:
    st.markdown("### Tokens")
    try:
        from src.core.tokens import token_status, probe
        p=probe()
        s1=token_status("dhan"); s2=token_status("groww")
        st.markdown(f"Issuer: <b class='{'pos' if p.get('reachable') else 'neg'}'>{'OK' if p.get('reachable') else 'DOWN '+p.get('kind','')}</b>", unsafe_allow_html=True)
        for s in (s1,s2):
            h=int((s.get('seconds_remaining') or 0)//3600)
            st.markdown(f"<span class='num'>{s['broker'].upper()}: <b class='{'pos' if s.get('fresh') else 'neg'}'>{'fresh' if s.get('fresh') else 'STALE'}</b> <span class='small'>{h}h left · exp {s.get('expiry')}</span></span>", unsafe_allow_html=True)
    except Exception as e:
        st.markdown(f"<span class='warn'>token check failed</span> <span class='small'>{e}</span>", unsafe_allow_html=True)
with g3:
    st.markdown("### Risk")
    st.markdown(f"<span class='num'>risk/trade {risk.get('risk_per_trade_pct',1)}% · max {risk.get('max_lots_per_10l',3)} lots/₹10L</span>", unsafe_allow_html=True)
    st.markdown(f"<span class='num'>kill day <b class='neg'>-{risk.get('daily_loss_kill_pct',2)}%</b> · week <b class='neg'>-{risk.get('weekly_loss_kill_pct',4)}%</b> → flat</span>", unsafe_allow_html=True)
    st.markdown(f"<span class='num'>square-off 15:18 IST · session 09:15–15:30</span>", unsafe_allow_html=True)

st.divider()
# ---- equity + performance ----
c1,c2=st.columns([3,2])
with c1:
    st.markdown("### Equity — 2-engine portfolio (SENSEX H21 + NIFTY H63)")
    try:
        eq=pd.read_csv(ROOT/"results/portfolio_daily.csv", parse_dates=["date"])
        st.line_chart(eq.set_index("date")["equity"], height=240)
        last=eq.iloc[-1]
        st.markdown(f"<span class='num small'>530 trade-days · last {last['date'].date()} · equity ₹{last['equity']:,.0f} · total <b class='pos'>+₹{last['equity']-500000:,.0f}</b> · costs incl.</span>", unsafe_allow_html=True)
    except Exception as e:
        st.markdown(f"<span class='warn'>equity curve unavailable</span> <span class='small'>{e}</span>", unsafe_allow_html=True)
with c2:
    st.markdown("### Conviction (≥0.60 trades)")
    try:
        mega=json.loads((ROOT/"results/mega_sweep.json").read_text())
        rows=[{"engine":r["key"],"conv":r["conviction"],"sharpe":r["sharpe"],"dd":r["maxDD"],"oos":r.get("oos",0)} for r in mega["top15"][:8]]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    except Exception as e:
        st.markdown(f"<span class='small'>run scripts/mega_sweep.py — {e}</span>", unsafe_allow_html=True)

# ---- backtest table ----
st.markdown("### Backtest — 12y, full NSE costs, walk-forward OOS")
rp=ROOT/"results"/"backtest_report.json"
if rp.exists():
    data=json.loads(rp.read_text())
    rows=[]
    for k,v in data.items():
        if k.startswith("COMBINED") or k.endswith("_wf"): continue
        rows.append({"symbol":k,"trades":v.get("trades"),"pnl":v.get("pnl"),"sharpe":v.get("sharpe"),"dd%":v.get("maxDD"),"win%":v.get("win"),"oos":v.get("oos_sharpe"),"2026":v.get("pnl_2026")})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if "COMBINED_GROSS" in data:
        g=data["COMBINED_GROSS"]; s=data["COMBINED_SPLIT"]
        st.markdown(f"<span class='num small'>COMBINED gross ₹{g['pnl']:,.0f} · sharpe {g['sharpe']} · DD {g['maxDD']}% · OOS {g['oos_sharpe']} → split on ₹5L ₹{s['pnl']:,.0f}</span>", unsafe_allow_html=True)

# ---- fills ----
st.markdown("### Fills — paper journal")
db=ROOT/"logs"/"paper.db"
if db.exists():
    try:
        con=sqlite3.connect(str(db))
        df=pd.read_sql("SELECT ts, symbol, side, qty, price, tag FROM fills ORDER BY ts DESC LIMIT 25", con)
        if len(df): st.dataframe(df, use_container_width=True, hide_index=True)
        else: st.markdown("<span class='small'>no fills yet</span>", unsafe_allow_html=True)
    except Exception as e:
        st.markdown(f"<span class='small'>db read failed: {e}</span>", unsafe_allow_html=True)

with st.expander("How it makes money — plain words"):
    st.markdown("""
- **Overnight (core):** buy futures 15:22, sell next open 09:20 — only when VIX≥19 and trailing health>0. ~65 trades/yr, wins ~65%.
- **Intraday (satellite, paper-tracked):** SENSEX short ORB30 and BANKNIFTY long ORB30 on 1-min bars, 09:30–14:30, square 15:18.
- **Costs on every trade:** ₹20/order + STT + exchange + SEBI + stamp + 18% GST + 1.5pt slippage. Targets must clear costs or the trade is a loss.
- **Protection:** 1% risk/trade, day −2% / week −4% → flat. Flat days are a feature, not a failure.
""")

st.divider()
st.markdown(f"""
<div style="text-align:center; padding:14px 8px; border:1px solid #2a2e39; border-radius:6px; background:#1c2230;">
  <div style="font-size:15px; font-weight:600; color:#e8ebf0;">◈ {BOT}</div>
  <div style="font-size:12px; color:#d1d4dc; margin-top:4px;">This bot is <b>{BOT}</b> — powered by <b>{MODEL}</b></div>
  <div class="small" style="margin-top:8px; line-height:1.8;">Indian F&O · 12y backtest · full NSE cost stack · paper trading only<br>
  Past performance ≠ future returns · SEBI: 93% of retail F&O traders lose money · Not financial advice</div>
</div>
""", unsafe_allow_html=True)
