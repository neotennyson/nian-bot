from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
import pytz

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"logs"/"guardian.json"
IST=pytz.timezone("Asia/Kolkata")

# arm=True: real newsrooms can trigger blocks. arm=False: query mirrors are
# informational only — their headlines contain trigger words by construction
# (e.g. every item in a "missile" query mentions missiles), so they may never arm.
FEEDS=[
    ("https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", True),
    ("https://www.moneycontrol.com/rss/latestnews.xml", True),
    ("https://www.business-standard.com/rss/markets-106.rss", True),
    ("https://www.livemint.com/rss/markets", True),
    ("http://feeds.bbci.co.uk/news/business/rss.xml", True),
    ("https://news.google.com/rss/search?q=RBI+repo+rate+monetary+policy&hl=en-IN&gl=IN&ceid=IN:en", False),
    ("https://news.google.com/rss/search?q=Nifty+Sensex+crash+OR+surge+OR+circuit&hl=en-IN&gl=IN&ceid=IN:en", False),
    ("https://news.google.com/rss/search?q=India+war+OR+missile+OR+airstrike&hl=en-IN&gl=IN&ceid=IN:en", False),
]

L3=("declares war","military action","air strike","airstrike","missile","emergency imposed",
    "circuit breaker","trading halt","nuclear","invasion")
L2=("repo rate","rbi policy","monetary policy","sebi ban","union budget","election result","exit poll",
    "imposes tariff","tariff on india","rating cut","downgrade","sanctions","rate hike","rate cut")

import re as _re
STRONG_VERBS=("announces","announce","declares","decides","outcome","scheduled","live updates","policy meet","holds","cuts","hikes")
SPECULATION=("may ","could ","bets","likely","expected","eyes","see more","guide","explained","what it means","right time to")

def _has_verb(t: str) -> bool:
    return any(_re.search(r"\b"+_re.escape(v)+r"\b", t) for v in STRONG_VERBS)

def classify(text: str) -> tuple[int,str]:
    t=text.lower()
    for k in L3:
        if k in t:
            return 3, k
    for k in L2:
        if k in t:
            # speculation ("may need hikes", "hike bets") and explainers ("EMI guide")
            # must never pause trading — require a real event verb, whole-word matched
            if _has_verb(t) and not any(s in t for s in SPECULATION):
                return 2, k
            return 1, ""
    return 1, ""

def assess(max_items: int=25, timeout: int=8) -> dict:
    """Poll feeds, return {level, block_entries, force_flat, reason, hits, ts}.
    Fail-open: any outage returns level 1 with reason (VIX/health gates still apply)."""
    try:
        import feedparser
    except ImportError:
        return {"level":1,"block_entries":False,"force_flat":False,"reason":"feedparser missing","hits":[],"ts":datetime.now(IST).isoformat()}
    import time as _time
    cutoff=_time.time() - 48*3600  # only news from the last 48h can arm — kills evergreen explainers
    hits=[]
    try:
        for url, arm in FEEDS:
            try:
                fp=feedparser.parse(url, request_headers={"User-Agent":"Mozilla/5.0"})
                for e in (fp.entries or [])[:max_items]:
                    title=str(getattr(e,"title",""))
                    lvl,kw=classify(title)
                    if lvl<2:
                        continue
                    try:
                        pub=_time.mktime(e.published_parsed) if getattr(e,"published_parsed",None) else _time.time()
                    except Exception:
                        pub=cutoff
                    hits.append({"feed":url[:60],"title":title[:160],"level":lvl if (arm and pub>=cutoff) else 1,
                                 "keyword":kw,"armed":bool(arm and pub>=cutoff)})
            except Exception:
                continue
    except Exception as e:
        return {"level":1,"block_entries":False,"force_flat":False,"reason":f"poll fail: {e}","hits":[],"ts":datetime.now(IST).isoformat()}
    # macro tripwire: VIX day-change >20% elevates to L2
    try:
        import pandas as pd
        vix=pd.read_parquet(ROOT/"data/raw/indiavix_daily.parquet")["close"]
        chg=float(vix.iloc[-1]/vix.iloc[-2]-1)
        if chg > 0.20:
            hits.append({"feed":"INDIAVIX","title":f"VIX spike {chg*100:.1f}% day-over-day","level":2,"keyword":"vix spike"})
    except Exception:
        pass
    level=max([h["level"] for h in hits], default=1)
    top=next((h for h in hits if h["level"]==level), {})
    out={"level":level,"block_entries":level>=2,"force_flat":level>=3,
         "reason":f"L{level} {top.get('keyword','')}: {top.get('title','calm')[:120]}" if hits else "calm — no trigger keywords",
         "hits":hits[:10],"ts":datetime.now(IST).isoformat()}
    try:
        STATE.write_text(json.dumps(out, indent=1))
    except OSError:
        pass
    return out

def status() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {"level":1,"block_entries":False,"force_flat":False,"reason":"no assessment yet","hits":[]}
