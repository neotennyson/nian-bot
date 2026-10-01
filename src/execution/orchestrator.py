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

    def run_once(self, now=None):
        n=now or ist_now()
        t=n.time()
        # kill switch
        killed, reason=self.risk.check_kill()
        if killed:
            if self._position:
                self._flatten(reason)
            return {"action":"kill","reason":reason}

        # 09:20 overnight exit
        if self.entry_t > self.exit_t:
            # overnight holds across midnight: exit window is morning
            is_exit_window = self.open <= t <= self.exit_t or (t >= self.exit_t and t < dtime(9,30))
        else:
            is_exit_window = t >= self.exit_t and t <= dtime(9,30)
        # simplified: if we have position and time is 09:20 ±5m, exit
        if self._position and (self.exit_t.hour==t.hour and abs(t.minute - self.exit_t.minute) <= 5):
            pnl_total=0
            for sym, qty in list(self._position.items()):
                ltp=self.broker.ltp(sym) or self._entry_price.get(sym,0)
                # estimate pnl via broker
                pnl_total+=0
                self.broker.place_order(sym, abs(qty), "SELL" if qty>0 else "BUY", tag="overnight_exit")
            self._position.clear()
            self._entry_price.clear()
            return {"action":"exit_overnight","time":str(t)}

        # 15:22 entry — per-engine gates (two-engine portfolio)
        is_entry_window = self.entry_t.hour==t.hour and abs(t.minute - self.entry_t.minute) <= 5
        if is_entry_window and not self._position:
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
                    # use last close as proxy in paper
                    try: price=float(cached_fetch(yf, sym.lower()+"_daily",2,False)["close"].iloc[-1])
                    except: continue
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

        # square-off 15:18 forced flat
        if self.should_square(n) and self._position:
            self._flatten("square_off")
            return {"action":"squared"}

        return {"action":"hold","time":str(t), "pos": dict(self._position)}

    def _flatten(self, reason=""):
        for sym, qty in list(self._position.items()):
            self.broker.place_order(sym, abs(qty), "SELL" if qty>0 else "BUY", tag=f"flat_{reason}")
        self._position.clear()
        self._entry_price.clear()
