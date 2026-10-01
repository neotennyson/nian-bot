from __future__ import annotations
import pandas as pd

def orb_levels(day: pd.DataFrame, orb_minutes: int=30) -> tuple[float, float, pd.Timestamp] | None:
    day=day.between_time("09:15","15:30")
    if len(day) < orb_minutes + 5:
        return None
    end=day.index[0] + pd.Timedelta(minutes=orb_minutes)
    ob=day[day.index <= end]
    if len(ob)==0:
        return None
    return float(ob["high"].max()), float(ob["low"].min()), end

def orb_signal(day: pd.DataFrame, orb_minutes: int=30, direction: str="short",
               stop_pct: float=0.003, target_pct: float=0.005) -> dict | None:
    """Pure ORB signal on a day's 1-min panel. Returns entry plan or None.
    direction: short (fade up-break), long (fade down-break), both."""
    lv=orb_levels(day, orb_minutes)
    if not lv:
        return None
    hi, lo, end=lv
    rest=day[day.index > end]
    for idx, row in rest.iterrows():
        if idx.time() >= pd.to_datetime("14:30").time():
            return None
        c=float(row["close"])
        d=None
        if direction=="short" and c > hi:
            d=-1
        elif direction=="long" and c < lo:
            d=1
        elif direction=="both":
            if c > hi: d=-1
            elif c < lo: d=1
        if d is None:
            continue
        stop=c*(1+stop_pct) if d==-1 else c*(1-stop_pct)
        target=c*(1-target_pct) if d==-1 else c*(1+target_pct)
        return {"direction": d, "entry": c, "stop": stop, "target": target,
                "time": idx, "orb_high": hi, "orb_low": lo}
    return None

def orb_exit(day: pd.DataFrame, entry_time: pd.Timestamp, direction: int,
             stop: float, target: float) -> tuple[float, str]:
    rest=day[day.index > entry_time]
    for idx, row in rest.iterrows():
        if idx.time() >= pd.to_datetime("15:18").time():
            return float(row["close"]), "square"
        if direction==-1:
            if float(row["high"]) >= stop: return stop, "stop"
            if float(row["low"]) <= target: return target, "target"
        else:
            if float(row["low"]) <= stop: return stop, "stop"
            if float(row["high"]) >= target: return target, "target"
    return float(rest.iloc[-1]["close"]), "eod"
