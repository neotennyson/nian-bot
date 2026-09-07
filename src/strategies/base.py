from __future__ import annotations
from dataclasses import dataclass
import pandas as pd

@dataclass
class Signal:
    date: pd.Timestamp
    direction: int  # 1 long, -1 short, 0 flat
    entry: float
    stop: float
    target: float
    meta: dict

def entry_next_open(df: pd.DataFrame, idx: int) -> float:
    if idx+1 < len(df):
        return float(df.iloc[idx+1]["open"])
    return float(df.iloc[idx]["close"])
