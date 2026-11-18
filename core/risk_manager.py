"""
Institutional Risk Management Engine.
Enforces capital protection, circuit breakers, lot sizing, and intraday square-off rules.
"""
from datetime import datetime, time
from typing import Tuple
from config.settings import settings


class RiskManager:
    def __init__(self, max_daily_loss: float = None, max_lots: int = None, square_off_time_str: str = None,
                 enable_midday_filter: bool = None, midday_start_str: str = None, midday_end_str: str = None,
                 is_crypto: bool = False, is_forex: bool = False, is_global_fx: bool = False,
                 is_commodity: bool = False, symbol: str = None):
        from core.commodity import CommodityEngine
        from core.forex import ForexEngine

        self.symbol = symbol or ""
        self.is_crypto = is_crypto
        self.is_forex = is_forex or (ForexEngine.is_forex(self.symbol) if self.symbol else False)
        self.is_global_fx = is_global_fx
        self.is_commodity = is_commodity or (CommodityEngine.is_commodity(self.symbol) if self.symbol else False)

        self.max_daily_loss = max_daily_loss or settings.max_daily_loss
        self.max_lots = max_lots or settings.max_lots
        self.stop_loss_pct = settings.stop_loss_pct
        self.target_rr_ratio = settings.target_rr_ratio

        # Parse square-off time (default: "15:15" for NSE equity, "16:45" for NSE CDS, "23:15" for MCX Commodities)
        if self.is_commodity:
            default_sq = "23:15"
        elif self.is_forex and not self.is_global_fx:
            default_sq = "16:45"
        else:
            default_sq = settings.mandatory_square_off_time

        t_str = square_off_time_str or default_sq
        hour, minute = map(int, t_str.split(":"))
        self.square_off_time = time(hour=hour, minute=minute)

        # Midday Chop Filter - For MCX: 12:30 - 17:00 IST lull; For NSE: 11:30 - 13:30 IST
        if self.is_crypto or self.is_global_fx:
            self.enable_midday_filter = False
        else:
            self.enable_midday_filter = enable_midday_filter if enable_midday_filter is not None else settings.enable_midday_filter
        
        if self.is_commodity:
            m_start_str = midday_start_str or "12:30"
            m_end_str = midday_end_str or "17:00"
        else:
            m_start_str = midday_start_str or settings.midday_start
            m_end_str = midday_end_str or settings.midday_end

        m_s_h, m_s_m = map(int, m_start_str.split(":"))
        self.midday_start = time(hour=m_s_h, minute=m_s_m)

        m_e_h, m_e_m = map(int, m_end_str.split(":"))
        self.midday_end = time(hour=m_e_h, minute=m_e_m)

        self.trading_halted = False
        self.halt_reason = ""

    def check_pre_flight(self, current_realized_pnl: float, current_unrealized_pnl: float, requested_lots: int,
                         ignore_time_cutoff: bool = False, check_time: time = None) -> Tuple[bool, str]:
        """
        Validates whether a new trade can be initiated based on institutional risk limits.
        """
        # 1. Check if already halted
        if self.trading_halted:
            return False, f"HALTED: Trading is locked for the day. Reason: {self.halt_reason}"

        # 2. Check Daily Max Loss Circuit Breaker
        total_pnl = current_realized_pnl + current_unrealized_pnl
        if total_pnl <= -abs(self.max_daily_loss):
            self.trading_halted = True
            currency_symbol = "$" if self.is_crypto or self.is_global_fx else "₹"
            self.halt_reason = f"CIRCUIT BREAKER: Total daily P&L ({currency_symbol}{total_pnl:.2f}) breached max limit (-{currency_symbol}{self.max_daily_loss:.2f})."
            return False, self.halt_reason

        # 3. Check Lot Sizing Rules (1-lot validation rule)
        if requested_lots > self.max_lots:
            return False, f"REJECTED: Requested {requested_lots} lots exceeds max allowed limit ({self.max_lots} lot)."

        # 4. Check Mandatory Square-off Cutoff Time and Midday Chop Protection (Skipped in 24/7 Crypto and 24/5 Global FX)
        if not self.is_crypto and not self.is_global_fx and not ignore_time_cutoff:
            target_time = check_time or datetime.now().time()

            if target_time >= self.square_off_time:
                return False, f"TIME RESTRICTION: Current time {target_time.strftime('%H:%M:%S')} is past square-off cutoff ({self.square_off_time.strftime('%H:%M')}). No new entries permitted."

            if self.enable_midday_filter and (self.midday_start <= target_time <= self.midday_end):
                return False, f"MIDDAY NO-TRADE ZONE: Low liquidity / high whipsaw window ({self.midday_start.strftime('%H:%M')} - {self.midday_end.strftime('%H:%M')} IST). New entries blocked."

            if self.is_commodity and self.symbol:
                from core.commodity import CommodityEngine
                in_inv, inv_msg = CommodityEngine.is_inventory_window(self.symbol)
                if in_inv:
                    return False, f"INVENTORY EVENT: {inv_msg}"

        return True, "PASSED: All risk checks cleared."

    def is_midday_pause(self, check_time: time = None) -> bool:
        """Returns True if given time or current time falls within the midday chop pause window."""
        target_time = check_time or datetime.now().time()
        return self.enable_midday_filter and (self.midday_start <= target_time <= self.midday_end)

    def calculate_levels(self, entry_price: float, side: str, decimals: int = None) -> Tuple[float, float]:
        """
        Calculates hard stop-loss and target price based on predefined risk-reward.
        """
        risk_amount = entry_price * self.stop_loss_pct
        reward_amount = risk_amount * self.target_rr_ratio
        dec = decimals if decimals is not None else (4 if self.is_forex else 2)

        if side.upper() == "BUY":
            stop_loss = round(entry_price - risk_amount, dec)
            target = round(entry_price + reward_amount, dec)
        elif side.upper() == "SELL":
            stop_loss = round(entry_price + risk_amount, dec)
            target = round(entry_price - reward_amount, dec)
        else:
            raise ValueError(f"Invalid side {side}. Must be BUY or SELL.")

        return stop_loss, target

    def is_square_off_time(self) -> bool:
        """Returns True if current time has reached or exceeded mandatory square-off time (3:15 PM IST)."""
        return datetime.now().time() >= self.square_off_time
