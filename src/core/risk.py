from __future__ import annotations
import math

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

    def lots_for_risk(self, stop_pts: float, lot_size: int) -> int:
        if stop_pts<=0:
            return 1
        risk_budget=self.capital*self.risk_pct
        per_lot_risk=stop_pts*lot_size
        lots=max(1, int(risk_budget // per_lot_risk))
        cap=int(self.capital/1_000_000*10 * self.max_lots_per_10l) if self.capital>=500000 else self.max_lots_per_10l
        cap=max(1,cap)
        return min(lots, cap)

    def check_kill(self) -> tuple[bool,str]:
        if self.realized_today <= -self.daily_kill*self.day_start:
            return True, f"daily kill {-self.daily_kill*100:.1f}%"
        if self.realized_week <= -self.weekly_kill*self.week_start:
            return True, f"weekly kill {-self.weekly_kill*100:.1f}%"
        return False,""

    def on_fill_pnl(self, pnl: float):
        self.realized_today+=pnl
        self.realized_week+=pnl

    def new_day(self, equity: float):
        self.day_start=equity
        self.realized_today=0.0
