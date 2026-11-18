"""
Base Strategy Interface for Algorithmic Trading.
"""
from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Any


class BaseStrategy(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Enriches raw OHLCV DataFrame with required indicators."""
        pass

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyzes the latest candle and returns:
        {
            "action": "BUY" | "SELL" | "HOLD",
            "reason": str,
            "metrics": Dict[str, Any]
        }
        """
        pass
