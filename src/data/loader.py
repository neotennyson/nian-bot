from __future__ import annotations
from pathlib import Path
import pandas as pd
import yfinance as yf

ROOT=Path(__file__).resolve().parents[2]

def fetch_yf(symbol: str, years: int=12) -> pd.DataFrame:
    period=f"{years}y" if years<=10 else "max"
    # yfinance period max is not exact; just use max and slice
    t=yf.Ticker(symbol)
    df=t.history(period="max", auto_adjust=False)
    if df.empty:
        raise RuntimeError(f"empty yf for {symbol}")
    df=df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
    df=df[["open","high","low","close","volume"]]
    df.index=pd.to_datetime(df.index).tz_localize(None).normalize()
    if years<20:
        cutoff=pd.Timestamp.now().normalize() - pd.DateOffset(years=years)
        df=df[df.index>=cutoff]
    return df

def cached_fetch(symbol: str, name: str, years: int=12, refresh: bool=False) -> pd.DataFrame:
    raw_dir=ROOT/"data"/"raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path=raw_dir/f"{name}.parquet"
    if path.exists() and not refresh:
        try:
            return pd.read_parquet(path)
        except Exception:
            pass
    df=fetch_yf(symbol, years)
    df.to_parquet(path)
    return df

def load_or_fetch(name: str, symbol: str, years: int=12) -> pd.DataFrame:
    return cached_fetch(symbol, name, years)

def atr(df: pd.DataFrame, n: int=14) -> pd.Series:
    h,l,c=df["high"],df["low"],df["close"]
    prev_c=c.shift(1)
    tr=pd.concat([(h-l).abs(), (h-prev_c).abs(), (l-prev_c).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def rsi(close: pd.Series, n: int=14) -> pd.Series:
    delta=close.diff()
    gain=delta.clip(lower=0).rolling(n).mean()
    loss=(-delta.clip(upper=0)).rolling(n).mean()
    rs=gain/loss
    return 100 - (100/(1+rs))

def vix_regime(vix_close: pd.Series) -> pd.Series:
    return vix_close
