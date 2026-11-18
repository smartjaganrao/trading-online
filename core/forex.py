"""
Institutional Forex & Currency Derivatives Engine (NSE CDS & Global Forex).
Provides currency contract specifications, pip value modeling, global session tracker,
and statutory charge configurations for INR currency futures and major FX pairs.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, time
import pytz


# Comprehensive Currency Specifications
CURRENCY_SPECS: Dict[str, Dict[str, Any]] = {
    # ─── NSE Currency Derivatives Segment (CDS) ──────────────────────────
    "CDS:USDINR": {
        "ticker": "USDINR=X",
        "name": "US Dollar / Indian Rupee",
        "segment": "NSE_CDS",
        "base_currency": "USD",
        "quote_currency": "INR",
        "lot_size": 1000,           # 1 contract = $1,000
        "tick_size": 0.0025,        # 1/4 of a paisa (₹0.0025)
        "pip_size": 0.0025,         # On NSE CDS, 1 pip = 0.0025 (₹2.50/lot)
        "pip_value_inr": 2.50,      # ₹0.0025 * 1000 = ₹2.50 per lot
        "decimals": 4,
        "margin_approx_inr": 2200.0,# ~2.5% intraday margin per lot
        "market_hours": "09:00 - 17:00 IST",
        "square_off_time": "16:45",
        "stt_exempt": True,         # STT is 0% on currency futures in India
        "description": "Highest liquidity currency derivative in India. RBI benchmark referenced."
    },
    "CDS:EURINR": {
        "ticker": "EURINR=X",
        "name": "Euro / Indian Rupee",
        "segment": "NSE_CDS",
        "base_currency": "EUR",
        "quote_currency": "INR",
        "lot_size": 1000,           # 1 contract = €1,000
        "tick_size": 0.0025,
        "pip_size": 0.0025,
        "pip_value_inr": 2.50,
        "decimals": 4,
        "margin_approx_inr": 2800.0,
        "market_hours": "09:00 - 17:00 IST",
        "square_off_time": "16:45",
        "stt_exempt": True,
        "description": "NSE CDS Euro contract. Highly responsive to ECB interest rate decisions."
    },
    "CDS:GBPINR": {
        "ticker": "GBPINR=X",
        "name": "British Pound / Indian Rupee",
        "segment": "NSE_CDS",
        "base_currency": "GBP",
        "quote_currency": "INR",
        "lot_size": 1000,           # 1 contract = £1,000
        "tick_size": 0.0025,
        "pip_size": 0.0025,
        "pip_value_inr": 2.50,
        "decimals": 4,
        "margin_approx_inr": 3400.0,
        "market_hours": "09:00 - 17:00 IST",
        "square_off_time": "16:45",
        "stt_exempt": True,
        "description": "High average true range (ATR) and volatility pair on NSE CDS."
    },
    "CDS:JPYINR": {
        "ticker": "JPYINR=X",
        "name": "Japanese Yen / Indian Rupee (per 100 JPY)",
        "segment": "NSE_CDS",
        "base_currency": "JPY",
        "quote_currency": "INR",
        "lot_size": 1000,           # Quoted per 100 JPY (100,000 JPY total)
        "tick_size": 0.0025,
        "pip_size": 0.0025,
        "pip_value_inr": 2.50,
        "decimals": 4,
        "margin_approx_inr": 2500.0,
        "market_hours": "09:00 - 17:00 IST",
        "square_off_time": "16:45",
        "stt_exempt": True,
        "description": "Bank of Japan carry trade barometer, quoted per 100 Yen."
    },

    # ─── Global Major Forex Pairs ─────────────────────────────────────────
    "EURUSD": {
        "ticker": "EURUSD=X",
        "name": "Euro / US Dollar",
        "segment": "GLOBAL_FX",
        "base_currency": "EUR",
        "quote_currency": "USD",
        "lot_size": 100000,         # Standard lot = 100,000 units
        "tick_size": 0.00001,       # 1/10th pip (pipette)
        "pip_size": 0.0001,         # 1 pip = 0.0001
        "pip_value_usd": 10.0,      # $10/pip per standard lot
        "decimals": 4,
        "market_hours": "24/5 Global (Mon 00:00 - Fri 23:59 GMT)",
        "description": "Most traded currency pair in the world, accounts for 24%+ of global FX volume."
    },
    "GBPUSD": {
        "ticker": "GBPUSD=X",
        "name": "British Pound / US Dollar (Cable)",
        "segment": "GLOBAL_FX",
        "base_currency": "GBP",
        "quote_currency": "USD",
        "lot_size": 100000,
        "tick_size": 0.00001,
        "pip_size": 0.0001,
        "pip_value_usd": 10.0,
        "decimals": 4,
        "market_hours": "24/5 Global",
        "description": "Known as 'The Cable'. Highly volatile during London and New York overlaps."
    },
    "USDJPY": {
        "ticker": "USDJPY=X",
        "name": "US Dollar / Japanese Yen",
        "segment": "GLOBAL_FX",
        "base_currency": "USD",
        "quote_currency": "JPY",
        "lot_size": 100000,
        "tick_size": 0.001,
        "pip_size": 0.01,           # JPY pairs have 2 decimal pip
        "pip_value_usd": 6.70,      # Depends on USDJPY exchange rate
        "decimals": 2,
        "market_hours": "24/5 Global",
        "description": "Primary safe-haven currency pair and Asian session anchor."
    },
    "AUDUSD": {
        "ticker": "AUDUSD=X",
        "name": "Australian Dollar / US Dollar (Aussie)",
        "segment": "GLOBAL_FX",
        "base_currency": "AUD",
        "quote_currency": "USD",
        "lot_size": 100000,
        "tick_size": 0.00001,
        "pip_size": 0.0001,
        "pip_value_usd": 10.0,
        "decimals": 4,
        "market_hours": "24/5 Global",
        "description": "Commodity-correlated currency pair linked to iron ore, coal, and China growth."
    },
    "USDCAD": {
        "ticker": "USDCAD=X",
        "name": "US Dollar / Canadian Dollar (Loonie)",
        "segment": "GLOBAL_FX",
        "base_currency": "USD",
        "quote_currency": "CAD",
        "lot_size": 100000,
        "tick_size": 0.00001,
        "pip_size": 0.0001,
        "pip_value_usd": 7.50,
        "decimals": 4,
        "market_hours": "24/5 Global",
        "description": "Crude oil correlated currency pair; reflects US-Canada trade flows."
    },
    "USDCHF": {
        "ticker": "USDCHF=X",
        "name": "US Dollar / Swiss Franc (Swissie)",
        "segment": "GLOBAL_FX",
        "base_currency": "USD",
        "quote_currency": "CHF",
        "lot_size": 100000,
        "tick_size": 0.00001,
        "pip_size": 0.0001,
        "pip_value_usd": 11.20,
        "decimals": 4,
        "market_hours": "24/5 Global",
        "description": "Traditional European safe haven pair during global geopolitical risk events."
    }
}


class ForexEngine:
    @staticmethod
    def is_forex(symbol: str) -> bool:
        """Determines if a symbol represents an Indian CDS or Global Forex pair."""
        cleaned = symbol.upper().replace(" ", "")
        if cleaned.startswith("CDS:") or "=X" in cleaned:
            return True
        for key in CURRENCY_SPECS:
            if key in cleaned or cleaned in key:
                return True
        return False

    @staticmethod
    def normalize_forex_symbol(symbol: str) -> str:
        """Normalizes user inputs like 'USDINR' or 'usdinr' to 'CDS:USDINR' or global key."""
        clean = symbol.upper().strip().replace(" ", "")
        if clean in CURRENCY_SPECS:
            return clean
        if f"CDS:{clean}" in CURRENCY_SPECS:
            return f"CDS:{clean}"
        if clean.endswith("=X"):
            raw = clean.replace("=X", "")
            if f"CDS:{raw}" in CURRENCY_SPECS:
                return f"CDS:{raw}"
            if raw in CURRENCY_SPECS:
                return raw
        return clean

    @staticmethod
    def get_specs(symbol: str) -> Optional[Dict[str, Any]]:
        norm = ForexEngine.normalize_forex_symbol(symbol)
        return CURRENCY_SPECS.get(norm)

    @staticmethod
    def format_price(symbol: str, price: float) -> str:
        specs = ForexEngine.get_specs(symbol)
        decimals = specs.get("decimals", 4) if specs else 4
        if "JPY" in symbol.upper():
            return f"{price:.2f}"
        return f"{price:.{decimals}f}"

    @staticmethod
    def calculate_pips(symbol: str, entry_price: float, exit_price: float, side: str) -> float:
        """Calculates net gain/loss in pips."""
        specs = ForexEngine.get_specs(symbol)
        pip_size = specs.get("pip_size", 0.0001) if specs else 0.0001
        
        diff = (exit_price - entry_price) if side.upper() == "BUY" else (entry_price - exit_price)
        return round(diff / pip_size, 1)

    @staticmethod
    def get_global_sessions() -> List[Dict[str, Any]]:
        """
        Determines current active global Forex trading sessions based on UTC / IST.
        Sessions:
        - Sydney:    22:00 - 07:00 UTC (03:30 - 12:30 IST)
        - Tokyo:     00:00 - 09:00 UTC (05:30 - 14:30 IST)
        - London:    08:00 - 16:30 UTC (13:30 - 22:00 IST)  [Highest volume]
        - New York:  13:00 - 21:00 UTC (18:30 - 02:30 IST)  [Peak overlap 18:30-22:00 IST]
        """
        now_utc = datetime.now(timezone.utc)
        utc_hour = now_utc.hour + now_utc.minute / 60.0

        def is_in_range(start: float, end: float, cur: float) -> bool:
            if start < end:
                return start <= cur < end
            else: # wraps around midnight
                return cur >= start or cur < end

        sessions = [
            {
                "name": "Sydney",
                "region": "Australasia",
                "hours_ist": "03:30 - 12:30 IST",
                "is_active": is_in_range(22.0, 7.0, utc_hour),
                "volatility": "Moderate",
                "key_pairs": "AUDUSD, NZDUSD, AUDJPY"
            },
            {
                "name": "Tokyo / Asian",
                "region": "Asia-Pacific",
                "hours_ist": "05:30 - 14:30 IST",
                "is_active": is_in_range(0.0, 9.0, utc_hour),
                "volatility": "Moderate",
                "key_pairs": "USDJPY, EURJPY, GBPJPY, AUDJPY"
            },
            {
                "name": "NSE CDS (India)",
                "region": "Domestic India",
                "hours_ist": "09:00 - 17:00 IST",
                "is_active": is_in_range(3.5, 11.5, utc_hour),
                "volatility": "Controlled / High Liquid",
                "key_pairs": "USDINR, EURINR, GBPINR, JPYINR"
            },
            {
                "name": "London / Europe",
                "region": "Europe",
                "hours_ist": "13:30 - 22:00 IST",
                "is_active": is_in_range(8.0, 16.5, utc_hour),
                "volatility": "High (Peak Global Volume)",
                "key_pairs": "EURUSD, GBPUSD, EURGBP, EURINR"
            },
            {
                "name": "New York / US",
                "region": "North America",
                "hours_ist": "18:30 - 02:30 IST",
                "is_active": is_in_range(13.0, 21.0, utc_hour),
                "volatility": "High (USD Major News/Fed)",
                "key_pairs": "EURUSD, USDJPY, GBPUSD, USDCAD"
            }
        ]
        return sessions
