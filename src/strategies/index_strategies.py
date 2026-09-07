from __future__ import annotations
import pandas as pd
import numpy as np
from .base import Signal
from src.data.loader import atr

def gap_continuation_signals(df: pd.DataFrame, vix: pd.Series | None, atr_p: int=14, entry_atr: float=0.70) -> list[Signal]:
    a=atr(df, atr_p)
    sigs=[]
    for i in range(1, len(df)-1):
        prev_close=df.iloc[i-1]["close"]
        today_open=df.iloc[i]["open"]
        gap=today_open - prev_close
        av=float(a.iloc[i-1]) if not pd.isna(a.iloc[i-1]) else 0
        if av==0:
            continue
        gap_atr=abs(gap)/av
        if gap_atr < entry_atr:
            continue
        direction=1 if gap>0 else -1
        if vix is not None:
            try:
                v=float(vix.loc[df.index[i-1]])
                if v < 13:
                    continue
            except Exception:
                pass
        entry=float(df.iloc[i]["open"])
        stop=entry - direction*av*1.0
        target=entry + direction*av*1.8
        sigs.append(Signal(date=df.index[i], direction=direction, entry=entry, stop=stop, target=target, meta={"gap_atr":gap_atr}))
    return sigs

def overnight_drift_signals(df: pd.DataFrame, vix: pd.Series | None, vix_gate: float=17.0, health_lookback: int | None=None) -> list[Signal]:
    sigs=[]
    # health gate series if requested
    health=None
    if health_lookback:
        overnight=pd.Series(index=df.index, dtype=float)
        for i in range(1,len(df)):
            overnight.iloc[i]=float(df.iloc[i]["open"]/df.iloc[i-1]["close"]-1)
        health=overnight.rolling(health_lookback).sum()
    for i in range(len(df)-1):
        if vix is not None:
            try:
                v=float(vix.loc[df.index[i]])
                if v < vix_gate:
                    continue
            except Exception:
                continue
        if health is not None:
            try:
                h=float(health.loc[df.index[i]])
                if h <= 0:
                    continue
            except Exception:
                continue
        entry=float(df.iloc[i]["close"])
        exit_=float(df.iloc[i+1]["open"])
        sigs.append(Signal(date=df.index[i], direction=1, entry=entry, stop=entry*0.985, target=entry*1.03, meta={"vix": float(v) if vix is not None else None, "exit": exit_}))
    return sigs

def orb_signals(df: pd.DataFrame, orb_minutes: int=30, atr_p: int=14) -> list[Signal]:
    a=atr(df, atr_p)
    sigs=[]
    for i in range(len(df)-1):
        av=float(a.iloc[i]) if not pd.isna(a.iloc[i]) else 0
        if av==0:
            continue
        body=float(df.iloc[i]["close"]-df.iloc[i]["open"])
        if abs(body) < 0.35*av:
            continue
        direction=1 if body>0 else -1
        entry=float(df.iloc[i+1]["open"])
        stop=entry - direction*av*1.0
        target=entry + direction*av*2.0
        sigs.append(Signal(date=df.index[i+1], direction=direction, entry=entry, stop=stop, target=target, meta={"body_atr": body/av}))
    return sigs

def vix_mean_reversion_signals(df: pd.DataFrame, vix: pd.Series, high: float=20.0, low: float=13.0) -> list[Signal]:
    sigs=[]
    for i in range(len(df)-1):
        try:
            v=float(vix.loc[df.index[i]])
        except Exception:
            continue
        if v >= high:
            direction=1
        elif v <= low:
            direction=-1
        else:
            continue
        entry=float(df.iloc[i+1]["open"])
        av=float(atr(df,14).iloc[i]) if not pd.isna(atr(df,14).iloc[i]) else float(df.iloc[i]["close"]*0.01)
        stop=entry - direction*av*1.2
        target=entry + direction*av*1.5
        sigs.append(Signal(date=df.index[i+1], direction=direction, entry=entry, stop=stop, target=target, meta={"vix":v}))
    return sigs
