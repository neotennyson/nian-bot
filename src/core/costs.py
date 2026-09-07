from __future__ import annotations
import math

class CostModel:
    def __init__(self, cfg: dict):
        c=cfg
        self.brokerage=c.get("brokerage_per_order",20.0)
        self.opt_stt_sell=c.get("opt_stt_sell",0.0015)
        self.fut_stt_sell=c.get("fut_stt_sell",0.0005)
        self.exch_opt=c.get("exch_opt_nse",0.0003503)
        self.exch_fut=c.get("exch_fut_nse",0.0000173)
        self.sebi=c.get("sebi_turnover",0.000001)
        self.stamp_opt=c.get("stamp_opt_buy",0.00003)
        self.stamp_opt_buy=self.stamp_opt
        self.stamp_fut=c.get("stamp_fut_buy",0.00002)
        self.stamp_fut_buy=self.stamp_fut
        self.gst=c.get("gst_on_charges",0.18)
        self.ipft=c.get("ipft_opt",0.00002)
        self.slip_opt_pct=c.get("slippage_opt_pct",0.002)
        self.slip_fut_pts=c.get("slippage_fut_pts",1.5)
        self.min_slip=c.get("min_slippage_per_leg",0.75)

    def fut_cost(self, entry: float, exit: float, lots: int, lot_size: int, is_long: bool=True) -> float:
        qty=lots*lot_size
        notional_entry=entry*qty
        notional_exit=exit*qty
        turnover=notional_entry+notional_exit
        brokerage=2*self.brokerage
        exch=(self.exch_fut*turnover)
        sebi=self.sebi*turnover
        stt=self.fut_stt_sell*notional_exit if True else 0
        stamp=self.stamp_fut_buy*notional_entry
        ipft=0
        before_gst=exch+sebi
        gst=self.gst*before_gst
        slippage=self.slip_fut_pts*qty*2
        total=brokerage+exch+sebi+stt+stamp+gst+slippage
        return round(total,2)

    def fut_pnl(self, entry: float, exit: float, lots: int, lot_size: int, direction: int) -> tuple[float,float,float]:
        qty=lots*lot_size
        pts=(exit-entry)*direction
        gross=pts*qty
        cost=self.fut_cost(entry,exit,lots,lot_size, direction==1)
        net=round(gross-cost,2)
        return round(gross,2), cost, net

    def opt_cost(self, premium_buy: float, premium_sell: float, lots: int, lot_size: int) -> float:
        qty=lots*lot_size
        turnover_buy=premium_buy*qty
        turnover_sell=premium_sell*qty
        turnover=turnover_buy+turnover_sell
        brokerage=2*self.brokerage
        exch=self.exch_opt*turnover
        sebi=self.sebi*turnover
        stt=self.opt_stt_sell*turnover_sell
        stamp=self.stamp_opt*turnover_buy
        ipft=self.ipft*turnover
        before_gst=exch+sebi
        gst=self.gst*before_gst
        slip_per_leg=max(self.min_slip, self.slip_opt_pct*premium_sell)*qty + max(self.min_slip, self.slip_opt_pct*premium_buy)*qty
        total=brokerage+exch+sebi+stt+stamp+ipft+gst+slip_per_leg
        return round(total,2)
