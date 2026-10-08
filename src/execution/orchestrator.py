from __future__ import annotations
from pathlib import Path
from datetime import datetime, time as dtime
import pandas as pd
import pytz
from src.core.config import load_settings
from src.core.costs import CostModel
from src.core.risk import RiskManager
from src.execution.paper_broker import PaperBroker
from src.data.loader import cached_fetch

IST=pytz.timezone("Asia/Kolkata")
ROOT=Path(__file__).resolve().parents[2]

def ist_now():
    return datetime.now(IST)

class Orchestrator:
    def __init__(self, settings: dict | None=None):
        self.cfg=settings or load_settings()
        self.capital=float(self.cfg.get("capital",500000))
        self.costs=CostModel(self.cfg.get("costs",{}))
        self.risk=RiskManager(self.capital, self.cfg.get("risk",{}))
        broker_name=self.cfg.get("execution",{}).get("broker","paper")
        if broker_name=="groww":
            from src.execution.groww_broker import GrowwBroker
            self.broker=GrowwBroker(base_url=self.cfg.get("execution",{}).get("groww",{}).get("base_url","https://api.groww.in/v1"))
        else:
            self.broker=PaperBroker()
        self.open=dtime.fromisoformat(self.cfg.get("session",{}).get("open","09:15"))
        self.close=dtime.fromisoformat(self.cfg.get("session",{}).get("close","15:30"))
        self.square=dtime.fromisoformat(self.cfg.get("session",{}).get("square_off","15:18"))
        strat=self.cfg.get("strategies",{}).get("overnight_drift",{})
        self.vix_gate=float(strat.get("vix_gate",17.0))
        self.health_lb=int(strat.get("health_lookback",63))
        self.engines=strat.get("engines") or [{"symbol": strat.get("universe_filter","SENSEX"), "vix_gate": self.vix_gate, "health_lookback": self.health_lb}]
        self.entry_t=dtime.fromisoformat(strat.get("entry_time","15:22"))
        self.exit_t=dtime.fromisoformat(strat.get("exit_time","09:20"))
        self._position: dict[str,int] = {}  # symbol -> qty (lots*lot_size)
        self._entry_price: dict[str,float]={}
        # intraday ORB engines (paper-only by design — never live)
        self.intraday_engines=[]
        for key in ("orb_short","orb_banknifty_long"):
            icfg=self.cfg.get("strategies",{}).get(key,{})
            if icfg.get("enabled"):
                self.intraday_engines.append({"key": key, **icfg})
        self._intraday_open: dict[str,dict]={}  # symbol -> {qty, entry, stop, target, dir, tag}

    def in_session(self, now=None) -> bool:
        n=now or ist_now()
        t=n.time()
        return self.open <= t <= self.close

    def should_square(self, now=None) -> bool:
        n=now or ist_now()
        return n.time() >= self.square

    def _health_ok(self, symbol: str, yf: str, lookback: int | None=None) -> bool:
        lb=int(lookback or self.health_lb)
        # fetch last 200 days to compute trailing overnight sum
        try:
            df=cached_fetch(yf, symbol.lower()+"_daily", 2, refresh=False)
            df.index=pd.to_datetime(df.index).normalize()
            if len(df) < lb + 5:
                return False
            overnight=pd.Series(index=df.index, dtype=float)
            for i in range(1,len(df)):
                overnight.iloc[i]=float(df.iloc[i]["open"]/df.iloc[i-1]["close"]-1)
            h=float(overnight.tail(lb).sum())
            return h > 0
        except Exception:
            return False

    def _vix_ok(self, gate: float | None=None) -> bool:
        try:
            vix=cached_fetch("^INDIAVIX","indiavix_daily",2,False)["close"]
            v=float(vix.iloc[-1])
            return v >= float(gate if gate is not None else self.vix_gate)
        except Exception:
            return False

    def _guardian(self) -> dict:
        # cached 15 min — RSS polling every 20s would hammer sources and stall the loop
        import time as _time, json as _json
        try:
            st=_json.loads((ROOT/"logs"/"guardian.json").read_text())
            ts=datetime.fromisoformat(st.get("ts","2000-01-01"))
            if (ist_now()-ts).total_seconds() < 15*60:
                return st
        except Exception:
            pass
        try:
            from src.guardian import assess
            return assess()
        except Exception as e:
            return {"level":1,"block_entries":False,"force_flat":False,"reason":f"guardian fail-open: {e}","hits":[]}

    def run_once(self, now=None):
        n=now or ist_now()
        t=n.time()
        # kill switch
        killed, reason=self.risk.check_kill()
        if killed:
            if self._position:
                self._flatten(reason)
            return {"action":"kill","reason":reason}
        # event gate: L3 force-flat, L2 pause entries
        g=self._guardian()
        if g.get("force_flat") and (self._position or self._intraday_open):
            self._flatten(f"guardian_L3:{g.get('reason','')[:80]}")
            return {"action":"flat_guardian","reason":g.get("reason","")[:160]}

        # 09:20 overnight exit
        if self.entry_t > self.exit_t:
            # overnight holds across midnight: exit window is morning
            is_exit_window = self.open <= t <= self.exit_t or (t >= self.exit_t and t < dtime(9,30))
        else:
            is_exit_window = t >= self.exit_t and t <= dtime(9,30)
        # simplified: if we have position and time is 09:20 ±5m, exit
        if self._position and (self.exit_t.hour==t.hour and abs(t.minute - self.exit_t.minute) <= 5):
            pnl_total=0.0
            for sym, qty in list(self._position.items()):
                ltp=self.broker.ltp(sym) or self._entry_price.get(sym,0)
                pnl_total+=self._book_pnl(sym, qty, ltp)
                self.broker.place_order(sym, abs(qty), "SELL" if qty>0 else "BUY", tag="overnight_exit")
            self._position.clear()
            self._entry_price.clear()
            return {"action":"exit_overnight","time":str(t),"realized":round(pnl_total,2)}

        # 15:22 entry — per-engine gates (two-engine portfolio)
        is_entry_window = self.entry_t.hour==t.hour and abs(t.minute - self.entry_t.minute) <= 5
        if is_entry_window and not self._position:
            if g.get("block_entries"):
                return {"action":"skip","reason":f"guardian L{g.get('level')}: {g.get('reason','')[:120]}"}
            uni_by_sym={u["symbol"]: u for u in self.cfg.get("universe",{}).get("indexes",[])}
            skips=[]
            for eng in self.engines:
                sym=eng.get("symbol"); gate=float(eng.get("vix_gate", self.vix_gate)); lb=int(eng.get("health_lookback", self.health_lb))
                uni=uni_by_sym.get(sym)
                if not uni:
                    skips.append(f"{sym}: unknown symbol"); continue
                yf=uni["yf"]; lot=int(uni["lot"])
                if not self._vix_ok(gate):
                    skips.append(f"{sym}: VIX < {gate}"); continue
                if not self._health_ok(sym, yf, lb):
                    skips.append(f"{sym}: health{lb} <= 0"); continue
                # size: 1% risk, stop 1.5% => ~1-2 lots
                price=self.broker.ltp(sym)
                if price==0:
                    # live panel only — never fill at a stale cached close
                    live=self._today_minute(sym, yf)
                    if live is None or len(live)==0:
                        skips.append(f"{sym}: no live price — skipped, not filled stale")
                        continue
                    price=float(live["close"].iloc[-1])
                    self.broker.set_price(sym, price) if hasattr(self.broker,"set_price") else None
                stop_pts=price*0.015
                lots=self.risk.lots_for_risk(stop_pts, lot)
                qty=lots*lot
                res=self.broker.place_order(sym, qty, "BUY", tag="overnight_entry")
                if "blocked" not in res:
                    self._position[sym]=qty
                    self._entry_price[sym]=price
            if self._position:
                return {"action":"enter_overnight","positions":dict(self._position)}
            return {"action":"skip","reason":"; ".join(skips) if skips else "all engines blocked"}

        # intraday ORB engine — paper broker only, 09:30-14:30 window
        if isinstance(self.broker, PaperBroker) and self.intraday_engines:
            if dtime(9,30) <= t <= dtime(14,30):
                if g.get("block_entries"):
                    return {"action":"skip","reason":f"guardian L{g.get('level')} pause intraday"}
                res=self._intraday_tick(n)
                if res and res.get("action")!="hold":
                    return res

        # square-off 15:18 forced flat
        if self.should_square(n) and (self._position or self._intraday_open):
            self._flatten("square_off")
            return {"action":"squared"}

        return {"action":"hold","time":str(t), "pos": dict(self._position)}

    def _today_minute(self, symbol: str, yf: str) -> pd.DataFrame | None:
        # live 1-min via token service; cached 60s to respect Dhan rate limits
        import time
        cache=getattr(self, "_min_cache", {})
        hit=cache.get(symbol)
        if hit and time.time()-hit[0] < 60 and len(hit[1]):
            return hit[1]
        try:
            from src.core.tokens import get_token
            import json, urllib.request
            tok=get_token("dhan")
            import os
            cid=os.environ.get("DHAN_CLIENT_ID","YOUR_DHAN_CLIENT_ID")
            sid={"NIFTY":"13","SENSEX":"51","BANKNIFTY":"12"}.get(symbol)
            if not sid:
                return None
            today=ist_now().strftime("%Y-%m-%d")
            payload=json.dumps({"securityId":sid,"exchangeSegment":"IDX_I","instrument":"INDEX","interval":"1","oi":False,"fromDate":today,"toDate":today}).encode()
            req=urllib.request.Request("https://api.dhan.co/v2/charts/intraday", data=payload, headers={"access-token":tok,"client-id":cid,"Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                j=json.loads(r.read().decode())
            ts=j.get("timestamp",[])
            if not ts:
                return None
            df=pd.DataFrame({k:j.get(k,[]) for k in ["open","high","low","close","volume"]})
            df.index=pd.to_datetime([datetime.fromtimestamp(x) for x in ts])
            df=df.between_time("09:15","15:30")
            self._min_cache={**cache, symbol: (time.time(), df)}
            return df
        except Exception:
            return None

    def _intraday_tick(self, n) -> dict:
        from src.strategies.intraday_orb import orb_signal
        uni_by_sym={u["symbol"]: u for u in self.cfg.get("universe",{}).get("indexes",[])}
        for eng in self.intraday_engines:
            sym=eng.get("symbol") or ("SENSEX" if eng["key"]=="orb_short" else None)
            if not sym or sym in self._intraday_open or sym in self._position:
                continue
            uni=uni_by_sym.get(sym)
            if not uni:
                continue
            df=self._today_minute(sym, uni["yf"])
            if df is None or len(df) < 40:
                continue
            sig=orb_signal(df, orb_minutes=int(eng.get("orb_minutes",30)),
                           direction=str(eng.get("direction","short") if eng["key"]!="orb_short" else "short"),
                           stop_pct=float(eng.get("stop_pct",0.003)),
                           target_pct=float(eng.get("target_pct",0.005)))
            if not sig:
                continue
            lot=int(uni["lot"])
            price=self.broker.ltp(sym) or sig["entry"]
            if price==0:
                price=sig["entry"]
            if hasattr(self.broker,"set_price"):
                self.broker.set_price(sym, price)
            stop_pts=abs(price - sig["stop"])
            lots=self.risk.lots_for_risk(stop_pts, lot)
            qty=lots*lot
            side="SELL" if sig["direction"]==-1 else "BUY"
            res=self.broker.place_order(sym, qty, side, tag=f"intraday_{eng['key']}")
            if "blocked" not in res:
                self._intraday_open[sym]={"qty": qty if sig["direction"]==1 else -qty, "entry": price,
                                          "stop": sig["stop"], "target": sig["target"], "dir": sig["direction"], "tag": eng["key"]}
                return {"action":"enter_intraday","engine":eng["key"],"symbol":sym,"qty":qty,"side":side,"price":price}
        return {"action":"hold"}

    def _lot_of(self, sym: str) -> int:
        for u in self.cfg.get("universe",{}).get("indexes",[]):
            if u["symbol"]==sym:
                return int(u["lot"])
        return 1

    def _book_pnl(self, sym: str, qty: int, exit_px: float) -> float:
        entry=self._entry_price.get(sym, exit_px)
        lots=abs(qty)//max(1,self._lot_of(sym)) or 1
        direction=1 if qty>0 else -1
        try:
            _, _, net=self.costs.fut_pnl(entry, exit_px, lots, self._lot_of(sym), direction)
        except Exception:
            net=0.0
        self.risk.on_fill_pnl(net)
        return net

    def _flatten(self, reason=""):
        for sym, qty in list(self._position.items()):
            ltp=self.broker.ltp(sym) or self._entry_price.get(sym,0)
            self._book_pnl(sym, qty, ltp)
            self.broker.place_order(sym, abs(qty), "SELL" if qty>0 else "BUY", tag=f"flat_{reason}")
        for sym, info in list(self._intraday_open.items()):
            q=info["qty"]
            ltp=self.broker.ltp(sym) or info.get("entry",0)
            self._entry_price[sym]=info.get("entry",ltp)
            self._book_pnl(sym, q, ltp)
            self._entry_price.pop(sym, None)
            self.broker.place_order(sym, abs(q), "SELL" if q>0 else "BUY", tag=f"flat_intraday_{reason}")
        self._position.clear()
        self._entry_price.clear()
        self._intraday_open.clear()
