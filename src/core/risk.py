from __future__ import annotations
import json
import math
from datetime import date
from pathlib import Path

STATE_FILE = Path(__file__).resolve().parents[2] / "logs" / "risk_state.json"

class RiskManager:
    def __init__(self, capital: float, cfg: dict):
        self.capital=capital
        self.risk_pct=cfg.get("risk_per_trade_pct",1.0)/100
        self.max_lots_per_10l=cfg.get("max_lots_per_10l",3)
        self.daily_kill=cfg.get("daily_loss_kill_pct",2.0)/100
        self.weekly_kill=cfg.get("weekly_loss_kill_pct",4.0)/100
        self.day_start=capital
        self.week_start=capital
        self.realized_today=0.0
        self.realized_week=0.0
        self._day=str(date.today())
        self._load()

    def lots_for_risk(self, stop_pts: float, lot_size: int) -> int:
        if stop_pts<=0:
            return 1
        risk_budget=self.capital*self.risk_pct
        per_lot_risk=stop_pts*lot_size
        lots=max(1, int(risk_budget // per_lot_risk))
        cap=max(1, int(self.capital/1_000_000 * self.max_lots_per_10l))
        return min(lots, cap)

    def _roll_day(self):
        today=str(date.today())
        if today != self._day:
            self._day=today
            self.day_start=self.capital + self.realized_week
            self.realized_today=0.0
            self._save()

    def check_kill(self) -> tuple[bool,str]:
        self._roll_day()
        if self.realized_today <= -self.daily_kill*self.day_start:
            return True, f"daily kill {-self.daily_kill*100:.1f}%"
        if self.realized_week <= -self.weekly_kill*self.week_start:
            return True, f"weekly kill {-self.weekly_kill*100:.1f}%"
        return False,""

    def on_fill_pnl(self, pnl: float):
        self._roll_day()
        self.realized_today+=pnl
        self.realized_week+=pnl
        self._save()

    def new_day(self, equity: float):
        self.day_start=equity
        self.realized_today=0.0
        self._day=str(date.today())
        self._save()

    def _save(self):
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps({
                "day": self._day, "day_start": self.day_start,
                "week_start": self.week_start, "realized_today": self.realized_today,
                "realized_week": self.realized_week}))
        except OSError:
            pass

    def _load(self):
        try:
            s=json.loads(STATE_FILE.read_text())
            if s.get("day")==str(date.today()):
                self.realized_today=float(s.get("realized_today",0.0))
                self.day_start=float(s.get("day_start",self.capital))
            self.realized_week=float(s.get("realized_week",0.0))
            self.week_start=float(s.get("week_start",self.capital))
            self._day=str(date.today())
        except (OSError, ValueError, KeyError):
            pass
