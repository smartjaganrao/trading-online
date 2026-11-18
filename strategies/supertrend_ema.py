"""
SuperTrend + Dual EMA + RSI Systematic Strategy.
Combines trend direction (SuperTrend 10,3), momentum bias (EMA 9/21 cross), and exhaustion filter (RSI 14).
"""
import pandas as pd
import numpy as np
from typing import Dict, Any
from strategies.base import BaseStrategy
from config.settings import settings


class SuperTrendEMAStrategy(BaseStrategy):
    def __init__(
        self,
        ema_fast: int = 9,
        ema_slow: int = 21,
        atr_period: int = 10,
        atr_multiplier: float = 3.0,
        rsi_period: int = 14,
        adx_threshold: float = None,
        chop_threshold: float = None,
    ):
        super().__init__(name="SuperTrend_EMA_Confluence")
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.rsi_period = rsi_period
        self.adx_threshold = adx_threshold if adx_threshold is not None else settings.adx_threshold
        self.chop_threshold = chop_threshold if chop_threshold is not None else settings.chop_threshold

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # 1. EMAs
        df["ema_fast"] = df["close"].ewm(span=self.ema_fast, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.ema_slow, adjust=False).mean()

        # 2. RSI
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / (loss + 1e-9)
        df["rsi"] = 100 - (100 / (1 + rs))

        # 3. ATR & SuperTrend
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.rolling(window=self.atr_period).mean()

        # 4. ADX (Average Directional Index - Period 14)
        up_move = df["high"] - df["high"].shift(1)
        down_move = df["low"].shift(1) - df["low"]
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        tr_smooth = tr.ewm(alpha=1 / 14, adjust=False).mean()
        plus_di = 100 * (pd.Series(plus_dm, index=df.index).ewm(alpha=1 / 14, adjust=False).mean() / (tr_smooth + 1e-9))
        minus_di = 100 * (pd.Series(minus_dm, index=df.index).ewm(alpha=1 / 14, adjust=False).mean() / (tr_smooth + 1e-9))
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
        df["adx"] = dx.ewm(alpha=1 / 14, adjust=False).mean()

        # 5. Choppiness Index (CHOP 14)
        sum_tr = tr.rolling(window=14).sum()
        max_high = df["high"].rolling(window=14).max()
        min_low = df["low"].rolling(window=14).min()
        price_range = max_high - min_low
        chop = 100 * np.log10((sum_tr + 1e-9) / (price_range + 1e-9)) / np.log10(14)
        df["chop"] = chop.fillna(50.0)

        hl2 = (df["high"] + df["low"]) / 2
        df["basic_upper"] = hl2 + (self.atr_multiplier * df["atr"])
        df["basic_lower"] = hl2 - (self.atr_multiplier * df["atr"])

        # SuperTrend calculation
        supertrend = [True] * len(df)  # True = Bullish, False = Bearish
        final_upper = [0.0] * len(df)
        final_lower = [0.0] * len(df)

        for i in range(1, len(df)):
            curr_upper = df["basic_upper"].iloc[i]
            curr_lower = df["basic_lower"].iloc[i]
            prev_upper = final_upper[i - 1]
            prev_lower = final_lower[i - 1]
            prev_close = df["close"].iloc[i - 1]

            if curr_upper < prev_upper or prev_close > prev_upper:
                final_upper[i] = curr_upper
            else:
                final_upper[i] = prev_upper

            if curr_lower > prev_lower or prev_close < prev_lower:
                final_lower[i] = curr_lower
            else:
                final_lower[i] = prev_lower

            # Direction
            if supertrend[i - 1] and df["close"].iloc[i] < final_lower[i]:
                supertrend[i] = False
            elif not supertrend[i - 1] and df["close"].iloc[i] > final_upper[i]:
                supertrend[i] = True
            else:
                supertrend[i] = supertrend[i - 1]

        df["supertrend_bullish"] = supertrend
        df["supertrend_line"] = [final_lower[i] if supertrend[i] else final_upper[i] for i in range(len(df))]

        return df

    def generate_signal(self, df: pd.DataFrame) -> Dict[str, Any]:
        if len(df) < max(self.ema_slow, self.atr_period, self.rsi_period, 14) + 2:
            return {"action": "HOLD", "reason": "Insufficient candle history.", "metrics": {}}

        df_calc = self.calculate_indicators(df)
        last_row = df_calc.iloc[-1]
        prev_row = df_calc.iloc[-2]

        close = last_row["close"]
        ema_f = last_row["ema_fast"]
        ema_s = last_row["ema_slow"]
        rsi = last_row["rsi"]
        adx = float(last_row["adx"])
        chop = float(last_row["chop"])
        bullish = last_row["supertrend_bullish"]

        is_trending = (adx >= self.adx_threshold) and (chop < self.chop_threshold)
        regime = "TRENDING" if is_trending else "CHOPPY / CONSOLIDATING"

        metrics = {
            "close": round(close, 2),
            "ema_fast": round(ema_f, 2),
            "ema_slow": round(ema_s, 2),
            "rsi": round(rsi, 2),
            "adx": round(adx, 1),
            "chop": round(chop, 1),
            "regime": regime,
            "supertrend": "BULLISH" if bullish else "BEARISH",
        }

        # 1. Institutional Regime Filter: Block trend entries when market is choppy/consolidating
        if not is_trending:
            return {
                "action": "HOLD",
                "reason": f"Regime Filter: Market is {regime} (ADX {adx:.1f} < {self.adx_threshold} or CHOP {chop:.1f} >= {self.chop_threshold}). Trend entries blocked.",
                "metrics": metrics,
            }

        # Confluence Buy Signal
        if bullish and (ema_f > ema_s) and (rsi > 52) and (rsi < 75):
            # Check fresh crossover or strong continuation
            if prev_row["ema_fast"] <= prev_row["ema_slow"] or not prev_row["supertrend_bullish"]:
                return {"action": "BUY", "reason": "Fresh Bullish Crossover (EMA + SuperTrend flip)", "metrics": metrics}
            return {"action": "BUY", "reason": "Bullish Trend Confluence aligned", "metrics": metrics}

        # Confluence Sell / Short Signal
        if not bullish and (ema_f < ema_s) and (rsi < 48) and (rsi > 25):
            if prev_row["ema_fast"] >= prev_row["ema_slow"] or prev_row["supertrend_bullish"]:
                return {"action": "SELL", "reason": "Fresh Bearish Crossover (EMA + SuperTrend breakdown)", "metrics": metrics}
            return {"action": "SELL", "reason": "Bearish Trend Confluence aligned", "metrics": metrics}

        return {"action": "HOLD", "reason": "No strong directional confluence.", "metrics": metrics}
