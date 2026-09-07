from __future__ import annotations
import os
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]

def load_dotenv(path: Path | None = None):
    p = path or ROOT / ".env"
    if not p.exists():
        return {}
    loaded = {}
    for line in p.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k,_,v=line.partition("=")
        k=k.strip(); v=v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k]=v
            loaded[k]=v
    return loaded

load_dotenv()

def load_settings(path: Path | None = None) -> dict:
    p = path or ROOT / "config" / "settings.yaml"
    with open(p) as f:
        return yaml.safe_load(f)
