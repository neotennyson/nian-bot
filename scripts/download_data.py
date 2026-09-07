#!/usr/bin/env python3
from src.core.config import load_settings
from src.data.loader import cached_fetch

def main():
    cfg=load_settings()
    years=int(cfg.get("data",{}).get("lookback_years",12))
    for uni in cfg.get("universe",{}).get("indexes",[]):
        sym=uni["yf"]; name=uni["symbol"].lower()+"_daily"
        print(f"fetch {uni['symbol']} {sym} ...")
        df=cached_fetch(sym, name, years, refresh=True)
        print(f"  -> {len(df)} rows {df.index.min().date()} to {df.index.max().date()}")
    # also India VIX
    print("fetch INDIAVIX ^INDIAVIX ...")
    df=cached_fetch("^INDIAVIX","indiavix_daily", years, refresh=True)
    print(f"  -> {len(df)} rows")
    # equities
    for sym in cfg.get("universe",{}).get("equities",[]):
        yf=f"{sym}.NS"
        print(f"fetch {sym} {yf} ...")
        try:
            df=cached_fetch(yf, f"{sym.lower()}_daily", years, refresh=True)
            print(f"  -> {len(df)} rows")
        except Exception as e:
            print(f"  !! {e}")

if __name__=="__main__":
    main()
