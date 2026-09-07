from __future__ import annotations
import pandas as pd
import numpy as np
from .base import Signal
from src.data.loader import atr, rsi

def equity_momentum(df: pd.DataFrame, lookback: int=20, hold: int=5) -> list[Signal]:
    # Absolute momentum: close > close[lookback] => long next open, else short (equities both sides)
    sigs=[]
    for i in range(lookback, len(df)-1):
        mom=float(df.iloc[i]["close"] - df.iloc[i-lookback]["close"])
        direction=1 if mom>0 else -1
        entry=float(df.iloc[i+1]["open"])
        av=float(atr(df,14).iloc[i]) if not pd.isna(atr(df,14).iloc[i]) else entry*0.015
        stop=entry - direction*av*1.5
        target=entry + direction*av*2.0
        sigs.append(Signal(date=df.index[i+1], direction=direction, entry=entry, stop=stop, target=target, meta={"mom":mom}))
    return sigs

def equity_rsi2_meanrev(df: pd.DataFrame, rsi_n: int=2, oversold: float=10, overbought: float=90) -> list[Signal]:
    r=rsi(df["close"], rsi_n)
    sigs=[]
    for i in range(len(df)-1):
        rv=float(r.iloc[i]) if not pd.isna(r.iloc[i]) else 50
        if rv <= oversold:
            direction=1
        elif rv >= overbought:
            direction=-1
        else:
            continue
        entry=float(df.iloc[i+1]["open"])
        av=float(atr(df,14).iloc[i]) if not pd.isna(atr(df,14).iloc[i]) else entry*0.015
        stop=entry - direction*av*1.0
        target=entry + direction*av*1.2
        sigs.append(Signal(date=df.index[i+1], direction=direction, entry=entry, stop=stop, target=target, meta={"rsi2":rv}))
    return sigs

def equity_breakout(df: pd.DataFrame, n: int=20) -> list[Signal]:
    sigs=[]
    for i in range(n, len(df)-1):
        hh=float(df.iloc[i-n:i]["high"].max())
        ll=float(df.iloc[i-n:i]["low"].min())
        close=float(df.iloc[i]["close"])
        if close >= hh*0.999:
            direction=1
        elif close <= ll*1.001:
            direction=-1
        else:
            continue
        entry=float(df.iloc[i+1]["open"])
        av=float(atr(df,14).iloc[i]) if not pd.isna(atr(df,14).iloc[i]) else entry*0.015
        stop=entry - direction*av*1.0
        target=entry + direction*av*2.0
        sigs.append(Signal(date=df.index[i+1], direction=direction, entry=entry, stop=stop, target=target, meta={"hh":hh,"ll":ll}))
    return sigs
