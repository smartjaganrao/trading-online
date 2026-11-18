"""
Trade Journal and Execution Auditor.
Logs trades locally to data/trades.csv with institutional transaction cost and slippage modeling.
"""
from pathlib import Path
import csv
from datetime import datetime
from typing import Dict, Any


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JOURNAL_PATH = DATA_DIR / "trades.csv"


def calculate_transaction_costs(
    symbol: str,
    side: str,
    quantity: int,
    entry_price: float,
    exit_price: float,
    slippage_pct: float = 0.0004,
) -> Dict[str, float]:
    """
    Computes Indian stock market statutory and execution charges:
    - Brokerage: Zerodha flat ₹20 or 0.03% per executed order
    - STT (Securities Transaction Tax): 0.025% on Intraday Sell Equity / 0.1% on Options Sell
    - Exchange Turnover Charges: ~0.00325%
    - SEBI Turnover Charges: ~0.0001% (₹10/crore)
    - Stamp Duty: 0.003% on Buy side
    - GST: 18% on (Brokerage + Exchange + SEBI charges)
    - Estimated Slippage: 0.04% round-trip execution drag
    """
    entry_turnover = entry_price * quantity
    exit_turnover = exit_price * quantity
    turnover = entry_turnover + exit_turnover

    buy_turnover = entry_turnover if side.upper() == "BUY" else exit_turnover
    sell_turnover = exit_turnover if side.upper() == "BUY" else entry_turnover

    # Brokerage (Zerodha style: flat ₹20 or 0.03%)
    brokerage_entry = min(20.0, entry_turnover * 0.0003)
    brokerage_exit = min(20.0, exit_turnover * 0.0003)
    total_brokerage = round(brokerage_entry + brokerage_exit, 2)

    # STT: 0.025% on sell side (for equity intraday); if options 0.1% on sell premium
    stt_rate = 0.001 if "NIFTY" in symbol and quantity >= 50 else 0.00025
    stt = round(sell_turnover * stt_rate, 2)

    # Exchange Turnover Charges (0.00325%)
    exchange_charges = round(turnover * 0.0000325, 2)

    # SEBI Charges (0.0001%)
    sebi_charges = round(turnover * 0.000001, 2)

    # Stamp Duty (0.003% on Buy)
    stamp_duty = round(buy_turnover * 0.00003, 2)

    # GST (18% on Brokerage + Exchange + SEBI charges)
    gst = round((total_brokerage + exchange_charges + sebi_charges) * 0.18, 2)

    # Slippage Cost (0.04% of total turnover)
    slippage_cost = round(turnover * slippage_pct, 2)

    total_charges = round(total_brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst + slippage_cost, 2)

    return {
        "turnover": round(turnover, 2),
        "brokerage": total_brokerage,
        "stt": stt,
        "exchange_charges": exchange_charges,
        "sebi_charges": sebi_charges,
        "stamp_duty": stamp_duty,
        "gst": gst,
        "slippage_cost": slippage_cost,
        "total_charges": total_charges,
    }


class TradeJournal:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._ensure_header()

    def _ensure_header(self):
        if not JOURNAL_PATH.exists():
            with open(JOURNAL_PATH, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp",
                    "order_id",
                    "mode",
                    "symbol",
                    "side",
                    "quantity",
                    "price",
                    "stop_loss",
                    "target",
                    "action",
                    "gross_pnl",
                    "charges",
                    "pnl",
                    "reason",
                ])

    def log_trade(self, order_data: Dict[str, Any], mode: str = "PAPER", reason: str = ""):
        gross_pnl = order_data.get("gross_pnl", order_data.get("pnl", 0.0))
        charges = order_data.get("charges", 0.0)
        net_pnl = order_data.get("net_pnl", order_data.get("pnl", 0.0))

        # Check existing header format
        has_new_header = False
        if JOURNAL_PATH.exists():
            with open(JOURNAL_PATH, "r") as f:
                first_line = f.readline()
                if "gross_pnl" in first_line:
                    has_new_header = True

        with open(JOURNAL_PATH, "a", newline="") as f:
            writer = csv.writer(f)
            if has_new_header:
                writer.writerow([
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    order_data.get("order_id", "N/A"),
                    mode,
                    order_data.get("symbol", "N/A"),
                    order_data.get("side", "N/A"),
                    order_data.get("quantity", 0),
                    order_data.get("fill_price", 0.0),
                    order_data.get("stop_loss", 0.0),
                    order_data.get("target", 0.0),
                    order_data.get("action", "ORDER"),
                    round(gross_pnl, 2),
                    round(charges, 2),
                    round(net_pnl, 2),
                    reason,
                ])
            else:
                # Maintain compatibility with legacy 12-column header
                writer.writerow([
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    order_data.get("order_id", "N/A"),
                    mode,
                    order_data.get("symbol", "N/A"),
                    order_data.get("side", "N/A"),
                    order_data.get("quantity", 0),
                    order_data.get("fill_price", 0.0),
                    order_data.get("stop_loss", 0.0),
                    order_data.get("target", 0.0),
                    order_data.get("action", "ORDER"),
                    round(net_pnl, 2),
                    reason,
                ])
