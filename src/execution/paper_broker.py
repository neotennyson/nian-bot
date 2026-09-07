from __future__ import annotations
import sqlite3
from pathlib import Path
from .broker_base import BrokerBase

ROOT=Path(__file__).resolve().parents[2]
DB=ROOT/"logs"/"paper.db"

class PaperBroker(BrokerBase):
    def __init__(self):
        DB.parent.mkdir(parents=True, exist_ok=True)
        self.con=sqlite3.connect(str(DB))
        self.con.execute("CREATE TABLE IF NOT EXISTS fills (ts TEXT, symbol TEXT, side TEXT, qty INT, price REAL, tag TEXT)")
        self.con.commit()
        self._prices: dict[str,float]={}
        self._pos: dict[str,int]={}

    def set_price(self, symbol: str, price: float):
        self._prices[symbol]=price

    def ltp(self, symbol: str) -> float:
        return float(self._prices.get(symbol, 0))

    def place_order(self, symbol: str, qty: int, side: str, tag: str="") -> dict:
        price=self.ltp(symbol)
        # simulate: store
        self._pos[symbol]=self._pos.get(symbol,0) + (qty if side.upper()=="BUY" else -qty)
        self.con.execute("INSERT INTO fills VALUES (datetime('now'),?,?,?,?,?)", (symbol, side, qty, price, tag))
        self.con.commit()
        return {"status":"filled","price":price,"qty":qty}

    def positions(self) -> dict:
        return dict(self._pos)
