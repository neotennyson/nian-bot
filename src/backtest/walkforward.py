from __future__ import annotations
import pandas as pd
import numpy as np

def walk_forward(daily_pnl: pd.Series, train_years: int=3, test_months: int=6) -> dict:
    # Anchored walk-forward: train on prior 3y, test next 6m, step 6m
    if daily_pnl.empty:
        return {"windows":[], "oos_sharpe":0}
    daily_pnl=daily_pnl.sort_index()
    start=daily_pnl.index.min()
    end=daily_pnl.index.max()
    windows=[]
    cur=start + pd.DateOffset(years=train_years)
    while cur < end:
        train=daily_pnl[(daily_pnl.index >= cur - pd.DateOffset(years=train_years)) & (daily_pnl.index < cur)]
        test_end=cur + pd.DateOffset(months=test_months)
        test=daily_pnl[(daily_pnl.index >= cur) & (daily_pnl.index < test_end)]
        if len(test)==0:
            break
        tr_ret=train.mean() if len(train) else 0
        te_ret=test.mean()
        te_sharpe=float(test.mean()/test.std()*np.sqrt(252)) if test.std()!=0 and len(test)>5 else 0
        windows.append({"train_start": str(cur - pd.DateOffset(years=train_years))[:10], "test_start": str(cur)[:10], "test_end": str(test_end)[:10], "test_pnl": float(test.sum()), "test_sharpe": round(te_sharpe,2), "test_days": len(test)})
        cur=test_end
    oos=pd.concat([daily_pnl[(daily_pnl.index>=pd.to_datetime(w["test_start"])) & (daily_pnl.index<pd.to_datetime(w["test_end"]))] for w in windows]) if windows else pd.Series(dtype=float)
    oos_sharpe=float(oos.mean()/oos.std()*np.sqrt(252)) if len(oos)>10 and oos.std()!=0 else 0
    return {"windows": windows, "oos_sharpe": round(oos_sharpe,2), "oos_pnl": float(oos.sum()) if len(oos) else 0}
