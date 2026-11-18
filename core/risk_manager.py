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
                 is_crypto: bool = False):
        self.max_daily_loss = max_daily_loss or settings.max_daily_loss
        self.max_lots = max_lots or settings.max_lots
        self.stop_loss_pct = settings.stop_loss_pct
        self.target_rr_ratio = settings.target_rr_ratio
        self.is_crypto = is_crypto

        # Parse square-off time (e.g., "15:15")
        t_str = square_off_time_str or settings.mandatory_square_off_time
        hour, minute = map(int, t_str.split(":"))
        self.square_off_time = time(hour=hour, minute=minute)

        # Midday Chop Filter (11:30 - 13:30 IST) - Disabled by default in Crypto (24/7 global market)
        if is_crypto:
            self.enable_midday_filter = False
        else:
            self.enable_midday_filter = enable_midday_filter if enable_midday_filter is not None else settings.enable_midday_filter
        
        m_start_str = midday_start_str or settings.midday_start
        m_s_h, m_s_m = map(int, m_start_str.split(":"))
        self.midday_start = time(hour=m_s_h, minute=m_s_m)

        m_end_str = midday_end_str or settings.midday_end
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
            currency_symbol = "$" if self.is_crypto else "₹"
            self.halt_reason = f"CIRCUIT BREAKER: Total daily P&L ({currency_symbol}{total_pnl:.2f}) breached max limit (-{currency_symbol}{self.max_daily_loss:.2f})."
            return False, self.halt_reason

        # 3. Check Lot Sizing Rules (1-lot validation rule)
        if requested_lots > self.max_lots:
            return False, f"REJECTED: Requested {requested_lots} lots exceeds max allowed limit ({self.max_lots} lot)."

        # 4. Check Mandatory Square-off Cutoff Time and Midday Chop Protection (Skipped in 24/7 Crypto mode)
        if not self.is_crypto and not ignore_time_cutoff:
            target_time = check_time or datetime.now().time()

            if target_time >= self.square_off_time:
                return False, f"TIME RESTRICTION: Current time {target_time.strftime('%H:%M:%S')} is past square-off cutoff ({self.square_off_time.strftime('%H:%M')}). No new entries permitted."

            if self.enable_midday_filter and (self.midday_start <= target_time <= self.midday_end):
                return False, f"MIDDAY NO-TRADE ZONE: Low liquidity / high whipsaw window ({self.midday_start.strftime('%H:%M')} - {self.midday_end.strftime('%H:%M')} IST). New entries blocked."

        return True, "PASSED: All risk checks cleared."

    def is_midday_pause(self, check_time: time = None) -> bool:
        """Returns True if given time or current time falls within the midday chop pause window."""
        target_time = check_time or datetime.now().time()
        return self.enable_midday_filter and (self.midday_start <= target_time <= self.midday_end)

    def calculate_levels(self, entry_price: float, side: str) -> Tuple[float, float]:
        """
        Calculates hard stop-loss and target price based on predefined risk-reward.
        """
        risk_amount = entry_price * self.stop_loss_pct
        reward_amount = risk_amount * self.target_rr_ratio

        if side.upper() == "BUY":
            stop_loss = round(entry_price - risk_amount, 2)
            target = round(entry_price + reward_amount, 2)
        elif side.upper() == "SELL":
            stop_loss = round(entry_price + risk_amount, 2)
            target = round(entry_price - reward_amount, 2)
        else:
            raise ValueError(f"Invalid side {side}. Must be BUY or SELL.")

        return stop_loss, target

    def is_square_off_time(self) -> bool:
        """Returns True if current time has reached or exceeded mandatory square-off time (3:15 PM IST)."""
        return datetime.now().time() >= self.square_off_time
