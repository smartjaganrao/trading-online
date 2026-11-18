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
CRYPTO_JOURNAL_PATH = DATA_DIR / "crypto_trades.csv"


def calculate_crypto_transaction_costs(
    symbol: str,
    quantity: float,
    entry_price: float,
    exit_price: float,
    maker_fee_pct: float = 0.0002,
    taker_fee_pct: float = 0.0005,
    slippage_pct: float = 0.0002,
    is_taker: bool = True,
) -> Dict[str, float]:
    """
    Computes cryptocurrency market transaction costs:
    - Exchange Fees: Maker (0.02%) or Taker (0.05%) fee on turnover
    - Bid-Ask Spread Slippage: ~0.02% on deep liquidity pairs (BTC/USDT, ETH/USDT)
    All costs are denominated in quote currency (typically USDT/USD).
    """
    entry_turnover = entry_price * quantity
    exit_turnover = exit_price * quantity
    turnover = entry_turnover + exit_turnover

    fee_rate = taker_fee_pct if is_taker else maker_fee_pct
    exchange_fee = round(turnover * fee_rate, 4)
    slippage_cost = round(turnover * slippage_pct, 4)
    total_charges = round(exchange_fee + slippage_cost, 4)

    return {
        "turnover": round(turnover, 4),
        "exchange_fee": exchange_fee,
        "slippage_cost": slippage_cost,
        "total_charges": total_charges,
    }


from core.forex import ForexEngine

def calculate_transaction_costs(
    symbol: str,
    side: str,
    quantity: int,
    entry_price: float,
    exit_price: float,
    slippage_pct: float = 0.0004,
) -> Dict[str, float]:
    """
    Computes statutory and execution charges:
    - Equity/F&O: Brokerage, STT (0.025% / 0.1%), Exchange (0.00325%), SEBI (₹10/cr), Stamp (0.003%), GST (18%).
    - Currency Derivatives (NSE CDS):
        - Brokerage: ₹20 flat or 0.03%
        - STT: ₹0.0 (STT EXEMPT in Indian Currency Futures!)
        - Exchange Turnover Charges: 0.0009%
        - SEBI Charges: 0.0001% (₹10/crore)
        - Stamp Duty: 0.0001% on Buy side
        - GST: 18% on (Brokerage + Exchange + SEBI)
        - Slippage: 0.0025 tick drag (~0.01%)
    """
    is_fx = ForexEngine.is_forex(symbol)

    entry_turnover = entry_price * quantity
    exit_turnover = exit_price * quantity
    turnover = entry_turnover + exit_turnover

    buy_turnover = entry_turnover if side.upper() == "BUY" else exit_turnover
    sell_turnover = exit_turnover if side.upper() == "BUY" else entry_turnover

    # Brokerage (Zerodha style: flat ₹20 or 0.03%)
    brokerage_entry = min(20.0, entry_turnover * 0.0003)
    brokerage_exit = min(20.0, exit_turnover * 0.0003)
    total_brokerage = round(brokerage_entry + brokerage_exit, 2)

    if is_fx:
        # Currency Derivatives (NSE CDS) - STT is ZERO
        stt = 0.0
        exchange_charges = round(turnover * 0.000009, 2)  # 0.0009% for CDS
        sebi_charges = round(turnover * 0.000001, 2)       # ₹10/crore
        stamp_duty = round(buy_turnover * 0.000001, 2)     # 0.0001% on Buy
        gst = round((total_brokerage + exchange_charges + sebi_charges) * 0.18, 2)
        # Tight slippage for currencies (0.0025 tick)
        fx_slippage = min(0.0001, slippage_pct)
        slippage_cost = round(turnover * fx_slippage, 2)
    else:
        # STT: 0.025% on sell side (for equity intraday); if options 0.1% on sell premium
        stt_rate = 0.001 if "NIFTY" in symbol and quantity >= 50 else 0.00025
        stt = round(sell_turnover * stt_rate, 2)
        exchange_charges = round(turnover * 0.0000325, 2)
        sebi_charges = round(turnover * 0.000001, 2)
        stamp_duty = round(buy_turnover * 0.00003, 2)
        gst = round((total_brokerage + exchange_charges + sebi_charges) * 0.18, 2)
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
        self._ensure_crypto_header()

    def _ensure_crypto_header(self):
        if not CRYPTO_JOURNAL_PATH.exists():
            with open(CRYPTO_JOURNAL_PATH, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp",
                    "order_id",
                    "exchange",
                    "mode",
                    "symbol",
                    "side",
                    "quantity",
                    "price",
                    "stop_loss",
                    "target",
                    "action",
                    "gross_pnl_usdt",
                    "fee_usdt",
                    "net_pnl_usdt",
                    "reason",
                ])

    def log_crypto_trade(self, order_data: Dict[str, Any], exchange: str = "binance", mode: str = "PAPER", reason: str = ""):
        self._ensure_crypto_header()
        gross_pnl = order_data.get("gross_pnl", 0.0)
        charges = order_data.get("charges", 0.0)
        net_pnl = order_data.get("pnl", 0.0)

        with open(CRYPTO_JOURNAL_PATH, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                order_data.get("order_id", "N/A"),
                exchange.upper(),
                mode,
                order_data.get("symbol", "N/A"),
                order_data.get("side", "N/A"),
                order_data.get("quantity", 0.0),
                order_data.get("fill_price", 0.0),
                order_data.get("stop_loss", 0.0),
                order_data.get("target", 0.0),
                order_data.get("action", "ORDER"),
                round(gross_pnl, 4),
                round(charges, 4),
                round(net_pnl, 4),
                reason,
            ])

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
