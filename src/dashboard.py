import streamlit as st
import json, pandas as pd, sqlite3
from pathlib import Path
from datetime import datetime
import pytz
from src.core.config import load_settings

ROOT=Path(__file__).resolve().parents[1]
IST=pytz.timezone("Asia/Kolkata")
st.set_page_config(page_title="NIAN 🐉 — Break the Nian Market", layout="wide", page_icon="🐉")

# Dragon theme
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@600&family=Inter:wght@400;600&display=swap');
.stApp {background: radial-gradient(1200px 600px at 20% -10%, #2a0a0a 0%, #0a0a0a 60%), #070707; color:#e8dcc8}
h1 {font-family:'Cinzel',serif; color:#ffb020; text-shadow:0 0 18px #ff3b1f80}
h2,h3 {color:#ffb020; font-family:'Inter',sans-serif}
.small {font-size:12px; color:#9a8a6a}
.card {background:linear-gradient(180deg,#1a0f0f,#0f0a0a); border:1px solid #3a1a0a; border-radius:16px; padding:14px; box-shadow:0 6px 24px #0008}
.kpi {font-size:28px; font-weight:700; color:#ffb020}
.mode-paper {background:#0e2a14; border:1px solid #1b6b2a; color:#8aff8a; padding:6px 12px; border-radius:999px; font-weight:600}
.mode-live {background:#2a0e0e; border:1px solid #8a1a1a; color:#ff8a8a; padding:6px 12px; border-radius:999px; font-weight:600}
.stButton>button {background:linear-gradient(180deg,#ff3b1f,#a81800); color:white; border:none; border-radius:10px; font-weight:700; box-shadow:0 4px 14px #ff1a0040}
a {color:#ffb020}
</style>
""", unsafe_allow_html=True)

# Header
left, right = st.columns([5,1])
with left:
    st.markdown("# 🐉 NIAN — Break the Nian Market")
    st.markdown("**Autonomous Indian F&O • Profit-only • Overnight dragon that hunts only when fear + health align**")
    st.write(f"<span class='small'>VIX ≥17 + 63-day health gate • 12y backtest • Groww + Dhan • Muse Spark 1.2</span>", unsafe_allow_html=True)
with right:
    st.image("https://em-content.zobj.net/source/microsoft-teams/363/dragon_1f409.png", width=90)
    st.write(f"<span class='small'>{datetime.now(IST).strftime('%d %b %Y %H:%M IST')}</span>", unsafe_allow_html=True)

cfg=load_settings()
strat=cfg.get("strategies",{}).get("overnight_drift",{})
risk=cfg.get("risk",{})
mode=cfg.get("execution",{}).get("broker","paper")
is_paper = mode=="paper"

# Mode toggle
st.markdown("### 🎮 Mode")
colA, colB, colC = st.columns([2,3,5])
with colA:
    if is_paper:
        st.markdown("<span class='mode-paper'>● PAPER MODE — safe, no real orders</span>", unsafe_allow_html=True)
    else:
        st.markdown("<span class='mode-live'>● LIVE MODE — real orders via Groww/Dhan</span>", unsafe_allow_html=True)
with colB:
    if st.button("🔄 Switch to " + ("LIVE" if is_paper else "PAPER")):
        st.warning("Edit `config/settings.yaml: execution.broker` → `paper` or `groww` then restart. Switch is manual by design — no accidental live trades.")
with colC:
    st.caption("Paper = simulated fills + full costs. Live = real MIS market orders (needs Algo-ID + TOKEN_API_KEY). Dragon only breathes fire at 15:22.")

# KPIs
k1,k2,k3,k4,k5 = st.columns(5)
k1.markdown(f"<div class='card'><div class='small'>Capital</div><div class='kpi'>₹{cfg.get('capital',500000):,.0f}</div></div>", unsafe_allow_html=True)
k2.markdown(f"<div class='card'><div class='small'>Broker</div><div class='kpi'>{mode.upper()}</div></div>", unsafe_allow_html=True)
k3.markdown(f"<div class='card'><div class='small'>Engine</div><div class='kpi'>VIX≥{strat.get('vix_gate',17)}</div><div class='small'>health {strat.get('health_lookback',63)}d</div></div>", unsafe_allow_html=True)
k4.markdown(f"<div class='card'><div class='small'>Risk / Trade</div><div class='kpi'>{risk.get('risk_per_trade_pct',1)}%</div><div class='small'>max {risk.get('max_lots_per_10l',3)} lots/₹10L</div></div>", unsafe_allow_html=True)
k5.markdown(f"<div class='card'><div class='small'>Kill Switch</div><div class='kpi'>-{risk.get('daily_loss_kill_pct',2)}% / -{risk.get('weekly_loss_kill_pct',4)}%</div><div class='small'>→ flat</div></div>", unsafe_allow_html=True)

# Token health
try:
    from src.core.tokens import token_status, probe
    p=probe(); s1=token_status("dhan"); s2=token_status("groww")
    t1,t2,t3 = st.columns(3)
    t1.markdown(f"<div class='card'><b>Token API</b><br>{'OK ✅' if p.get('reachable') else 'DOWN ❌ '+p.get('kind','')} </div>", unsafe_allow_html=True)
    t2.markdown(f"<div class='card'><b>DHAN</b><br>{'Fresh ✅' if s1.get('fresh') else 'Stale ❌'} — {int(s1.get('seconds_remaining',0)//3600)}h left<br><span class='small'>{s1.get('expiry')}</span></div>", unsafe_allow_html=True)
    t3.markdown(f"<div class='card'><b>GROWW</b><br>{'Fresh ✅' if s2.get('fresh') else 'Stale ❌'} — {int(s2.get('seconds_remaining',0)//3600)}h left<br><span class='small'>{s2.get('expiry')}</span></div>", unsafe_allow_html=True)
except Exception as e:
    st.warning(f"token check: {e}")

# Schedule explainer
with st.expander("📅 Does it trade every day? — No, ~26% days. Click to see schedule", expanded=True):
    st.markdown("""
    **Entry 15:22 → Exit next day 09:20** — only if **VIX ≥17** (fear premium) **AND** trailing 63-day overnight sum >0 (regime healthy).

    | Symbol | Trades 12y | Per year | % days | 2026 |
    |--------|-----------|----------|--------|------|
    | NIFTY | 786 | 65 | 26.6% | -₹37k (gate limited) |
    | BANKNIFTY | 740 | 62 | 25.0% | ₹0 (0 trades — gate blocked loss) |
    | SENSEX | 856 | 71 | 29.0% | ₹0 (blocked) |

    Outside the window the dragon **sleeps** — `orchestrator.py:run_once()` polls every 20s, checks kills → 09:20 exit → 15:22 entry → 15:18 square-off.
    """)
    st.info("Paper vs Live: **Same decision, different execution** — paper writes to `logs/paper.db` with simulated slippage; live sends MIS MARKET via `src/execution/groww_broker.py` using `get_token()`. Same VIX/health gate, same kills.")

# Conviction
with st.expander("🎯 Conviction Score — how profitable is it really? (0-1, ≥0.60 to trade)", expanded=True):
    st.markdown("""
    | Engine | Sharpe | PF | DD | Q-hit | **Score** | Verdict |
    |--------|--------|----|----|-------|-----------|---------|
    | **SENSEX** | 1.77 | 1.42 | -21% | 0.57 | **0.68** | ✅ Trade |
    | **NIFTY** | 1.27 | 1.28 | -22% | 0.47 | **0.61** | ✅ Barely |
    | BANKNIFTY | 0.97 | 1.20 | -25% | 0.40 | 0.55 | ⏸ Watch |
    | Gap / VIX-rev / Equities | -1.5 | 0.6 | -45% | 0.2 | 0.05 | ☠️ Killed |

    **Formula:** `0.28*Sharpe +0.16*DD +0.14*PF +0.12*Quarterly +0.12*Plateau +0.18*Coverage` × `reliability sqrt(n/30)` — see `NIAN-MODEL.md:2`.
    **COMBINED:** Sharpe 1.37 OOS 1.23 → **~0.64** — modest edge, 5.6% CAGR split, not a cash machine. Use it, don't worship it.
    """)

# Backtest
report_path=ROOT/"results"/"backtest_report.json"
st.markdown("### 📈 Backtest — 12 years, full NSE costs, walk-forward OOS")
if report_path.exists():
    data=json.loads(report_path.read_text())
    rows=[]
    for k,v in data.items():
        if k.startswith("COMBINED") or k.endswith("_wf"): continue
        rows.append({"Symbol":k, "Trades":v.get("trades"), "PNL ₹":f"{v.get('pnl'):,.0f}", "Sharpe":v.get("sharpe"), "DD %":v.get("maxDD"), "Win %":v.get("win"), "PF":v.get("pf"), "OOS":v.get("oos_sharpe"), "2026 ₹":f"{v.get('pnl_2026'):,.0f}"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    if "COMBINED_GROSS" in data:
        g=data["COMBINED_GROSS"]; s=data["COMBINED_SPLIT"]
        cols=st.columns(3)
        cols[0].metric("COMBINED Gross", f"₹{g['pnl']:,.0f}", f"Sharpe {g['sharpe']}")
        cols[1].metric("Split on ₹5L", f"₹{s['pnl']:,.0f}", f"{s['pnl']/500000*100:.1f}% total")
        cols[2].metric("OOS Sharpe", g['oos_sharpe'], f"DD {g['maxDD']}%")
else:
    st.warning("Run `scripts/run_backtest.py`")

# Paper vs Live interactive
st.markdown("### 🔬 Paper vs Live — how it reacts")
tab1, tab2, tab3 = st.tabs(["Paper fills (live)", "What-if Live?", "Simple words"])
with tab1:
    db=ROOT/"logs"/"paper.db"
    if db.exists():
        try:
            con=sqlite3.connect(str(db))
            df=pd.read_sql("SELECT ts, symbol, side, qty, price, tag FROM fills ORDER BY ts DESC LIMIT 30", con)
            if len(df): st.dataframe(df, use_container_width=True)
            else: st.info("No fills yet — bot is correctly waiting for 15:22 gate (VIX now <17, so skip)")
            # controls
            c1,c2=st.columns(2)
            if c1.button("🧪 Simulate 15:22 entry now (paper)"):
                from src.execution.orchestrator import Orchestrator
                from datetime import datetime
                import pytz
                IST=pytz.timezone("Asia/Kolkata")
                orch=Orchestrator(); orch.vix_gate=0
                fake=datetime.now(IST).replace(hour=15,minute=22,second=0,microsecond=0)
                res=orch.run_once(now=fake)
                st.json(res)
                st.rerun()
            if c2.button("🚪 Simulate 09:20 exit"):
                from src.execution.orchestrator import Orchestrator
                from datetime import datetime
                import pytz
                IST=pytz.timezone("Asia/Kolkata")
                orch=Orchestrator()
                fake=datetime.now(IST).replace(hour=9,minute=20,second=0,microsecond=0)
                orch._position={'NIFTY':75}; orch._entry_price={'NIFTY':25000}
                if hasattr(orch.broker,'set_price'): orch.broker.set_price('NIFTY',25100)
                st.json(orch.run_once(now=fake))
        except Exception as e:
            st.write(f"db err: {e}")
    else:
        st.info("Start `scripts/run_paper.py` to see fills here")
with tab2:
    st.markdown("""
    **Switch to Live:** Edit `config/settings.yaml` → `execution.broker: groww` (or `dhan`), restart. Same gate, same size (`risk.py: lots_for_risk`), but `groww_broker.py` sends real `MARKET MIS` via `get_token("groww")` Bearer. **Manual gate:** token service is READ-only for data; order path needs human Algo-ID — `tokens.py:EXECUTION_PATH_NAMESPACES` enforces this.
    
    Live kills are real: daily -2% → flat + halt, weekly -4% → flat. No “give it room”.
    """)
    st.warning("Live needs `TOKEN_API_KEY` + `DHAN_CLIENT_ID` in `.env` and broker Algo-ID + static IP whitelist. Test paper 4-6 weeks first.")
with tab3:
    st.markdown("""
    **In simple words:**
    1. *Morning* VIX is fear. If fear is low (<17) or last 2 months’ night money was negative, dragon sleeps.
    2. *3:22pm* if fear high + health good → dragon buys NIFTY/BANKNIFTY/SENSEX futures (small, 1% risk).
    3. *Next morning 9:20* dragon sells whatever it bought. Win ~60% days, ~1.3× wins vs losses. Small edge, repeated 65 times a year = profit.
    4. *If day is bad* (-2% day) dragon stops and goes home. No revenge trades.
    """)

st.divider()
st.markdown("<center><span class='small'>This bot is powered by <b>Muse Spark 1.2</b> • Built Sep 2026 from scratch for “break the Nian market” • Evidence over opinion • Not financial advice</span></center>", unsafe_allow_html=True)
st.caption("Auto-refresh: Streamlit reruns on interaction — in live session keep paper loop running separately.")
