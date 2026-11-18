"""
Institutional Commodities Derivatives Engine (MCX & Global Commodities).
Provides contract specifications, lot sizes, tick sizes, CTT (Commodity Transaction Tax) modeling,
high-impact US inventory calendar tracking (EIA Crude/NatGas), and session management for MCX.
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, time
import pytz


# Comprehensive MCX & Global Commodity Specifications
COMMODITY_SPECS: Dict[str, Dict[str, Any]] = {
    # ─── Energy ────────────────────────────────────────────────────────
    "MCX:CRUDEOIL": {
        "ticker": "CL=F",
        "name": "Crude Oil Futures (100 Barrels)",
        "exchange": "MCX",
        "segment": "MCX-FUT",
        "unit": "100 Barrels",
        "lot_size": 100,
        "tick_size": 1.0,           # ₹1 move = ₹100 P&L per lot
        "tick_value_inr": 100.0,
        "margin_approx_inr": 180000.0,
        "market_hours": "09:00 - 23:30 IST",
        "square_off_time": "23:15",
        "ctt_rate": 0.0005,         # 0.05% on Sell side
        "inventory_day": "Wednesday",
        "inventory_event": "US EIA Crude Oil Stocks (20:00 / 20:30 IST)",
        "description": "High liquidity global energy benchmark. Trades in sync with NYMEX WTI."
    },
    "MCX:CRUDEOILM": {
        "ticker": "CL=F",
        "name": "Crude Oil Mini Futures (10 Barrels)",
        "exchange": "MCX",
        "segment": "MCX-FUT",
        "unit": "10 Barrels",
        "lot_size": 10,
        "tick_size": 1.0,           # ₹1 move = ₹10 P&L per lot
        "tick_value_inr": 10.0,
        "margin_approx_inr": 19000.0,
        "market_hours": "09:00 - 23:30 IST",
        "square_off_time": "23:15",
        "ctt_rate": 0.0005,
        "inventory_day": "Wednesday",
        "inventory_event": "US EIA Crude Oil Stocks (20:00 / 20:30 IST)",
        "description": "Ideal retail contract for disciplined risk management and small lot sizing."
    },
    "MCX:NATURALGAS": {
        "ticker": "NG=F",
        "name": "Natural Gas Futures (1250 mmBtu)",
        "exchange": "MCX",
        "segment": "MCX-FUT",
        "unit": "1250 mmBtu",
        "lot_size": 1250,
        "tick_size": 0.10,          # ₹0.10 move = ₹125 P&L per lot
        "tick_value_inr": 125.0,
        "margin_approx_inr": 135000.0,
        "market_hours": "09:00 - 23:30 IST",
        "square_off_time": "23:15",
        "ctt_rate": 0.0005,
        "inventory_day": "Thursday",
        "inventory_event": "US EIA Natural Gas Storage (20:00 / 20:30 IST)",
        "description": "High volatility gas contract tracking Henry Hub futures."
    },
    "MCX:NATGASMINI": {
        "ticker": "NG=F",
        "name": "Natural Gas Mini Futures (250 mmBtu)",
        "exchange": "MCX",
        "segment": "MCX-FUT",
        "unit": "250 mmBtu",
        "lot_size": 250,
        "tick_size": 0.10,          # ₹0.10 move = ₹25 P&L per lot
        "tick_value_inr": 25.0,
        "margin_approx_inr": 27000.0,
        "market_hours": "09:00 - 23:30 IST",
        "square_off_time": "23:15",
        "ctt_rate": 0.0005,
        "inventory_day": "Thursday",
        "inventory_event": "US EIA Natural Gas Storage (20:00 / 20:30 IST)",
        "description": "Mini Natural Gas contract for controlled risk intraday setups."
    },

    # ─── Precious Metals ───────────────────────────────────────────────
    "MCX:GOLD": {
        "ticker": "GC=F",
        "name": "Gold Futures (1 Kg)",
        "exchange": "MCX",
        "segment": "MCX-FUT",
        "unit": "100 Grams quote",
        "lot_size": 100,
        "tick_size": 1.0,           # ₹1 move per 10g = ₹10 P&L per contract unit
        "tick_value_inr": 10.0,
        "margin_approx_inr": 750000.0,
        "market_hours": "09:00 - 23:30 IST",
        "square_off_time": "23:15",
        "ctt_rate": 0.0005,
        "description": "Standard institutional bullion contract tracking COMEX Gold."
    },
    "MCX:GOLDM": {
        "ticker": "GC=F",
        "name": "Gold Mini Futures (100 Grams)",
        "exchange": "MCX",
        "segment": "MCX-FUT",
        "unit": "10 Grams quote",
        "lot_size": 10,
        "tick_size": 1.0,           # ₹1 move per 10g = ₹1 P&L
        "tick_value_inr": 1.0,
        "margin_approx_inr": 75000.0,
        "market_hours": "09:00 - 23:30 IST",
        "square_off_time": "23:15",
        "ctt_rate": 0.0005,
        "description": "Liquid gold mini contract for retail and swing strategies."
    },
    "MCX:SILVER": {
        "ticker": "SI=F",
        "name": "Silver Futures (30 Kg)",
        "exchange": "MCX",
        "segment": "MCX-FUT",
        "unit": "30 Kg (1 Kg quote)",
        "lot_size": 30,
        "tick_size": 1.0,           # ₹1 move = ₹30 P&L
        "tick_value_inr": 30.0,
        "margin_approx_inr": 320000.0,
        "market_hours": "09:00 - 23:30 IST",
        "square_off_time": "23:15",
        "ctt_rate": 0.0005,
        "description": "Standard silver contract with high momentum and daily ATR."
    },
    "MCX:SILVERMIC": {
        "ticker": "SI=F",
        "name": "Silver Micro Futures (1 Kg)",
        "exchange": "MCX",
        "segment": "MCX-FUT",
        "unit": "1 Kg (1 Kg quote)",
        "lot_size": 1,
        "tick_size": 1.0,           # ₹1 move = ₹1 P&L
        "tick_value_inr": 1.0,
        "margin_approx_inr": 13000.0,
        "market_hours": "09:00 - 23:30 IST",
        "square_off_time": "23:15",
        "ctt_rate": 0.0005,
        "description": "Lowest margin precious metals contract. Perfect for beginners and tight risk bots."
    },

    # ─── Base Metals ───────────────────────────────────────────────────
    "MCX:COPPER": {
        "ticker": "HG=F",
        "name": "Copper Futures (2500 Kg)",
        "exchange": "MCX",
        "segment": "MCX-FUT",
        "unit": "2500 Kg (1 Kg quote)",
        "lot_size": 2500,
        "tick_size": 0.05,          # ₹0.05 move = ₹125 P&L
        "tick_value_inr": 125.0,
        "margin_approx_inr": 210000.0,
        "market_hours": "09:00 - 23:30 IST",
        "square_off_time": "23:15",
        "ctt_rate": 0.0005,
        "description": "Dr. Copper - global economic barometer tracking LME and COMEX."
    },
    "MCX:ZINC": {
        "ticker": "ZN=F",
        "name": "Zinc Futures (5000 Kg)",
        "exchange": "MCX",
        "segment": "MCX-FUT",
        "unit": "5000 Kg",
        "lot_size": 5000,
        "tick_size": 0.05,
        "tick_value_inr": 250.0,
        "margin_approx_inr": 190000.0,
        "market_hours": "09:00 - 23:30 IST",
        "square_off_time": "23:15",
        "ctt_rate": 0.0005,
        "description": "High volume industrial metal on MCX."
    }
}


class CommodityEngine:
    @staticmethod
    def is_commodity(symbol: str) -> bool:
        """Determines if a symbol represents an MCX commodity or global futures contract."""
        cleaned = symbol.upper().replace(" ", "")
        if cleaned.startswith("MCX:") or cleaned in ("CL=F", "NG=F", "GC=F", "SI=F", "HG=F", "ZN=F"):
            return True
        for key in COMMODITY_SPECS:
            base_sym = key.replace("MCX:", "")
            if base_sym in cleaned or cleaned in base_sym:
                return True
        return False

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        """Normalizes inputs like 'CRUDEOIL', 'crudeoil', 'MCX:CRUDEOIL26NOVFUT' to standard spec key."""
        clean = symbol.upper().strip().replace(" ", "")
        if clean in COMMODITY_SPECS:
            return clean
        if f"MCX:{clean}" in COMMODITY_SPECS:
            return f"MCX:{clean}"
        
        # Check contract variations like CRUDEOIL26NOVFUT or CRUDEOILM26NOVFUT
        for key in COMMODITY_SPECS:
            base_sym = key.replace("MCX:", "")
            if base_sym in clean:
                return key
        return clean

    @staticmethod
    def get_specs(symbol: str) -> Optional[Dict[str, Any]]:
        norm = CommodityEngine.normalize_symbol(symbol)
        return COMMODITY_SPECS.get(norm)

    @staticmethod
    def get_lot_size(symbol: str) -> int:
        specs = CommodityEngine.get_specs(symbol)
        if specs:
            return int(specs.get("lot_size", 1))
        # Fallbacks
        sym = symbol.upper()
        if "CRUDEOILM" in sym:
            return 10
        if "CRUDEOIL" in sym:
            return 100
        if "NATGASMINI" in sym:
            return 250
        if "NATURALGAS" in sym:
            return 1250
        if "SILVERMIC" in sym:
            return 1
        if "SILVERM" in sym:
            return 5
        if "SILVER" in sym:
            return 30
        if "GOLDM" in sym:
            return 10
        if "GOLD" in sym:
            return 100
        if "COPPER" in sym:
            return 2500
        return 1

    @staticmethod
    def get_tick_size(symbol: str) -> float:
        specs = CommodityEngine.get_specs(symbol)
        return float(specs.get("tick_size", 0.05)) if specs else 0.05

    @staticmethod
    def get_commodity_sessions() -> List[Dict[str, Any]]:
        """
        Tracks MCX commodity operational trading phases throughout the day.
        """
        ist = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.now(ist)
        cur_time = now_ist.time()

        def is_in_time(start_h: int, start_m: int, end_h: int, end_m: int) -> bool:
            return time(start_h, start_m) <= cur_time <= time(end_h, end_m)

        sessions = [
            {
                "phase": "Domestic Morning Open",
                "hours": "09:00 - 12:30 IST",
                "active": is_in_time(9, 0, 12, 30),
                "regime": "Initial price discovery, reacts to overnight Asian markets.",
                "liquidity": "Moderate"
            },
            {
                "phase": "European Pre-Open / Midday Lull",
                "hours": "12:30 - 17:00 IST",
                "active": is_in_time(12, 30, 17, 0),
                "regime": "Low domestic volume, sideways chop. Recommended to pause new entries.",
                "liquidity": "Low / Choppy"
            },
            {
                "phase": "US NYMEX & COMEX Peak Power Hours",
                "hours": "18:30 - 22:30 IST",
                "active": is_in_time(18, 30, 22, 30),
                "regime": "Prime Institutional Trend Window. NYMEX open, EIA inventory data, high ATR.",
                "liquidity": "Ultra High"
            },
            {
                "phase": "Intraday Square-Off Cutoff",
                "hours": "23:15 IST",
                "active": is_in_time(23, 15, 23, 30),
                "regime": "Mandatory square-off before broker auto-close at 23:25 IST.",
                "liquidity": "Exiting"
            }
        ]
        return sessions

    @staticmethod
    def is_inventory_window(symbol: str) -> Tuple[bool, str]:
        """
        Warns or halts entries during high-impact US inventory reports:
        - Crude Oil: EIA report every Wednesday 20:00 or 20:30 IST
        - Natural Gas: EIA report every Thursday 20:00 or 20:30 IST
        """
        ist = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.now(ist)
        weekday = now_ist.strftime("%A")
        cur_time = now_ist.time()

        sym = symbol.upper()
        # Wednesday: Crude Oil inventory (19:55 - 20:35 IST)
        if "CRUDE" in sym and weekday == "Wednesday":
            if time(19, 55) <= cur_time <= time(20, 35):
                return True, "EIA Crude Oil Inventory Release in progress! Extreme slippage & volatility risk."

        # Thursday: Natural Gas inventory (19:55 - 20:35 IST)
        if ("NATURALGAS" in sym or "NATGAS" in sym) and weekday == "Thursday":
            if time(19, 55) <= cur_time <= time(20, 35):
                return True, "EIA Natural Gas Storage Report in progress! Extreme whipsaw risk."

        return False, "Clear: No scheduled high-impact inventory release right now."
