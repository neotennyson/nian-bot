#!/usr/bin/env python3
import time, argparse
from src.execution.orchestrator import Orchestrator

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    args=ap.parse_args()
    orch=Orchestrator()
    print(f"NIAN paper broker ready. capital={orch.capital} broker={orch.broker.__class__.__name__} session {orch.open}-{orch.close} square {orch.square}")
    if args.once:
        print(orch.run_once())
        return
    while True:
        res=orch.run_once()
        if res["action"]!="hold":
            print(res)
        if not orch.in_session():
            print("outside session, sleep 60s")
            time.sleep(60)
            continue
        time.sleep(orch.cfg.get("execution",{}).get("poll_secs",20))

if __name__=="__main__":
    main()
