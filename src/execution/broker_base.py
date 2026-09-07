from __future__ import annotations
from abc import ABC, abstractmethod

class BrokerBase(ABC):
    @abstractmethod
    def ltp(self, symbol: str) -> float: ...
    @abstractmethod
    def place_order(self, symbol: str, qty: int, side: str, tag: str="") -> dict: ...
    @abstractmethod
    def positions(self) -> dict: ...
