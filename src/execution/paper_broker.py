from __future__ import annotations
import sqlite3
from pathlib import Path
from .broker_base import BrokerBase

ROOT=Path(__file__).resolve().parents[2]
DB=ROOT/"logs"/"paper.db"
SLIP_PTS=1.5  # mirror backtest slippage so paper tracks the model, not a fantasy

class PaperBroker(BrokerBase):
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.con=sqlite3.connect(str(DB))
        self.con.execute("CREATE TABLE IF NOT EXISTS fills (ts TEXT, symbol TEXT, side TEXT, qty INT, price REAL, tag TEXT)")
        self.con.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)")
        self.con.commit()
        self._prices: dict[str,float]={}
        self._pos: dict[str,int]={}
        for k, v in self.con.execute("SELECT k, v FROM kv WHERE k LIKE 'pos:%'"):
            try:
                self._pos[k[4:]]=int(v)
            except ValueError:
                pass

    def set_price(self, symbol: str, price: float):
        self._prices[symbol]=price

    def ltp(self, symbol: str) -> float:
        return float(self._prices.get(symbol, 0))

    def place_order(self, symbol: str, qty: int, side: str, tag: str="") -> dict:
        px=self.ltp(symbol)
        if px <= 0:
            return {"status":"rejected","reason":f"no LTP for {symbol} — refusing zero-price fill","blocked": True}
        slip=SLIP_PTS if side.upper()=="BUY" else -SLIP_PTS
        price=round(px + slip, 2)
        self._pos[symbol]=self._pos.get(symbol,0) + (qty if side.upper()=="BUY" else -qty)
        self.con.execute("INSERT INTO fills VALUES (datetime('now'),?,?,?,?,?)", (symbol, side, qty, price, tag))
        self.con.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (f"pos:{symbol}", str(self._pos[symbol])))
        self.con.commit()
        return {"status":"filled","price":price,"qty":qty}

    def positions(self) -> dict:
        return {k: v for k, v in self._pos.items() if v != 0}
