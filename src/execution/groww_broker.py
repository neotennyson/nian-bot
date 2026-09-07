from __future__ import annotations
import os, time, hmac, hashlib, base64, requests, pyotp
from .broker_base import BrokerBase

class GrowwBroker(BrokerBase):
    """
    Groww Trade API adapter.
    Auth: API key + TOTP (pyotp). Token refresh handled here.
    Docs: https://groww.in/trade-api/docs
    Endpoints are illustrative — mapped to Groww's actual REST once creds provided.
    Replace base_url + paths after verifying with your Groww dashboard.
    """
    def __init__(self, api_key: str | None=None, api_secret: str | None=None, totp_secret: str | None=None, base_url: str="https://api.groww.in/v1"):
        self.api_key=api_key or os.environ.get("GROWW_API_KEY","")
        self.api_secret=api_secret or os.environ.get("GROWW_API_SECRET","")
        self.totp_secret=totp_secret or os.environ.get("GROWW_TOTP_SECRET","")
        self.base_url=base_url.rstrip("/")
        self.token=""
        self.token_exp=0

    def _totp(self) -> str:
        if not self.totp_secret:
            return ""
        return pyotp.TOTP(self.totp_secret).now()

    def _auth(self):
        if self.token and time.time() < self.token_exp - 60:
            return
        if not self.api_key:
            raise RuntimeError("GROWW_API_KEY not set — add to .env")
        # Groww login flow: POST /token with api_key + totp
        # This is the correct pattern; adjust field names per your Groww API version
        url=f"{self.base_url}/token"
        body={"api_key": self.api_key, "totp": self._totp()}
        if self.api_secret:
            body["api_secret"]=self.api_secret
        r=requests.post(url, json=body, timeout=10)
        if r.status_code!=200:
            raise RuntimeError(f"Groww auth failed {r.status_code}: {r.text[:300]}")
        j=r.json()
        self.token=j.get("token") or j.get("access_token") or ""
        # tokens typically 24h
        self.token_exp=time.time()+ 23*3600

    def _headers(self):
        self._auth()
        return {"Authorization": f"Bearer {self.token}", "Content-Type":"application/json"}

    def ltp(self, symbol: str) -> float:
        self._auth()
        # Example: GET /quote?symbol=NSE:NIFTY
        r=requests.get(f"{self.base_url}/quote", params={"symbol": symbol}, headers=self._headers(), timeout=10)
        if r.status_code!=200:
            return 0.0
        j=r.json()
        return float(j.get("ltp") or j.get("last_price") or 0)

    def place_order(self, symbol: str, qty: int, side: str, tag: str="") -> dict:
        self._auth()
        body={
            "symbol": symbol,
            "quantity": int(qty),
            "side": side.upper(),
            "order_type": "MARKET",
            "product": "MIS",
            "tag": tag
        }
        r=requests.post(f"{self.base_url}/order", json=body, headers=self._headers(), timeout=10)
        if r.status_code not in (200,201):
            return {"status":"rejected","reason": r.text[:500]}
        return r.json()

    def positions(self) -> dict:
        self._auth()
        r=requests.get(f"{self.base_url}/positions", headers=self._headers(), timeout=10)
        if r.status_code!=200:
            return {}
        return r.json()
