#!/usr/bin/env python3
import json, time, argparse
from pathlib import Path
from src.execution.orchestrator import ist_now

HEARTBEAT=Path(__file__).resolve().parents[1]/"logs"/"heartbeat.json"

def beat(action: str):
    try:
        HEARTBEAT.write_text(json.dumps({"ts": ist_now().isoformat(), "action": action}))
    except OSError:
        pass

def main():
    from src.execution.orchestrator import Orchestrator
    ap=argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    args=ap.parse_args()
    orch=Orchestrator()
    print(f"NIAN paper broker ready. capital={orch.capital} broker={orch.broker.__class__.__name__} session {orch.open}-{orch.close} square {orch.square}")
    if args.once:
        res=orch.run_once()
        print(res)
        beat(f"once:{res.get('action')}")
        return
    while True:
        res=orch.run_once()
        beat(res.get("action","hold"))
        if res["action"]!="hold":
            print(res)
        if not orch.in_session():
            print("outside session, sleep 60s")
            time.sleep(60)
            continue
        time.sleep(orch.cfg.get("execution",{}).get("poll_secs",20))

if __name__=="__main__":
    main()
