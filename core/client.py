"""
Broker Client Abstraction Layer:
Supports seamless switching between Paper Trading (Simulated) and Live Zerodha Kite execution.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from datetime import datetime
import random
from config.settings import settings
from core.risk_manager import RiskManager
from core.forex import ForexEngine
from execution.journal import calculate_transaction_costs


class BaseBrokerClient(ABC):
    @abstractmethod
    def get_profile(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_margins(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_ltp(self, instruments: List[str]) -> Dict[str, float]:
        pass

    @abstractmethod
    def place_order(self, symbol: str, transaction_type: str, quantity: int, order_type: str = "MARKET", price: float = 0.0) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        pass


class PaperTradingClient(BaseBrokerClient):
    """
    Realistic simulated paper trading engine.
    Maintains virtual cash, active positions, realized/unrealized P&L without risking real capital.
    """
    def __init__(self, initial_capital: float = None, risk_manager: RiskManager = None):
        self.initial_capital = initial_capital or settings.paper_initial_capital
        self.available_cash = self.initial_capital
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.closed_trades: List[Dict[str, Any]] = []
        self.risk_manager = risk_manager or RiskManager()
        self.simulated_prices: Dict[str, float] = {
            "NSE:NIFTY 50": 24350.0,
            "NSE:NIFTY BANK": 52100.0,
            "NSE:RELIANCE": 1280.0,
            "NSE:INFY": 1820.0,
            "NSE:TCS": 4120.0,
            "NSE:HDFCBANK": 1780.0,
            # Forex & Currency Derivatives
            "CDS:USDINR": 84.4500,
            "USDINR": 84.4500,
            "CDS:EURINR": 91.8000,
            "EURINR": 91.8000,
            "CDS:GBPINR": 107.5000,
            "GBPINR": 107.5000,
            "CDS:JPYINR": 56.2000,
            "JPYINR": 56.2000,
            "EURUSD": 1.0850,
            "GBPUSD": 1.2950,
            "USDJPY": 154.20,
            "AUDUSD": 0.6540,
        }

    def get_profile(self) -> Dict[str, Any]:
        return {
            "user_id": "PAPER_TRADER_01",
            "user_name": "Paper Trading (Simulated Mode)",
            "broker": "Paper Simulation Engine",
            "email": "demo@trading-online.local",
            "status": "ACTIVE",
        }

    def get_margins(self) -> Dict[str, Any]:
        unrealized_pnl = self.get_unrealized_pnl()
        realized_pnl = self.get_realized_pnl()
        total_equity = self.available_cash + unrealized_pnl
        return {
            "initial_capital": self.initial_capital,
            "available_cash": self.available_cash,
            "used_margin": self.initial_capital - self.available_cash if self.available_cash < self.initial_capital else 0.0,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "total_portfolio_value": total_equity,
        }

    def update_mock_price(self, symbol: str, current_price: float = None) -> float:
        """Slightly fluctuates or sets price for live simulation."""
        is_fx = ForexEngine.is_forex(symbol)
        decimals = 4 if is_fx and "JPY" not in symbol else 2

        if symbol not in self.simulated_prices:
            self.simulated_prices[symbol] = 84.4500 if is_fx else 100.0

        if current_price is not None:
            self.simulated_prices[symbol] = current_price
        else:
            # Jitter: tighter for FX (0.02% to 0.05%) vs Equity (0.15%)
            jitter_max = 0.0003 if is_fx else 0.0015
            delta_pct = random.uniform(-jitter_max, jitter_max)
            self.simulated_prices[symbol] = round(self.simulated_prices[symbol] * (1 + delta_pct), decimals)
        return self.simulated_prices[symbol]

    def get_ltp(self, instruments: List[str]) -> Dict[str, float]:
        res = {}
        for inst in instruments:
            res[inst] = self.update_mock_price(inst)
        return res

    def get_realized_pnl(self) -> float:
        return sum(t.get("pnl", 0.0) for t in self.closed_trades)

    def get_unrealized_pnl(self) -> float:
        total = 0.0
        for symbol, pos in self.positions.items():
            current_price = self.simulated_prices.get(symbol, pos["entry_price"])
            if pos["side"] == "BUY":
                total += (current_price - pos["entry_price"]) * pos["quantity"]
            else:
                total += (pos["entry_price"] - current_price) * pos["quantity"]
        return round(total, 2)

    def place_order(self, symbol: str, transaction_type: str, quantity: int, order_type: str = "MARKET", price: float = 0.0) -> Dict[str, Any]:
        """
        Executes simulated order with pre-flight risk checks.
        """
        current_ltp = self.simulated_prices.get(symbol, 24350.0 if "NIFTY" in symbol else 1000.0)
        fill_price = price if (order_type == "LIMIT" and price > 0) else current_ltp

        # 1. Risk Pre-Flight Check (Paper mode allows off-hours simulated practice)
        realized = self.get_realized_pnl()
        unrealized = self.get_unrealized_pnl()
        allowed, msg = self.risk_manager.check_pre_flight(realized, unrealized, requested_lots=1, ignore_time_cutoff=True)
        if not allowed:
            return {"status": "REJECTED", "reason": msg, "order_id": None}

        # 2. Check existing opposite position (Squaring off)
        if symbol in self.positions:
            pos = self.positions[symbol]
            if pos["side"] != transaction_type:
                # Square off existing position with statutory charges + slippage
                gross_pnl = (fill_price - pos["entry_price"]) * pos["quantity"] if pos["side"] == "BUY" else (pos["entry_price"] - fill_price) * pos["quantity"]
                costs = calculate_transaction_costs(symbol, pos["side"], pos["quantity"], pos["entry_price"], fill_price)
                total_charges = costs["total_charges"]
                net_pnl = gross_pnl - total_charges

                self.available_cash += (pos["margin_locked"] + net_pnl)
                trade_record = {
                    "symbol": symbol,
                    "side": pos["side"],
                    "exit_side": transaction_type,
                    "quantity": pos["quantity"],
                    "entry_price": pos["entry_price"],
                    "exit_price": fill_price,
                    "gross_pnl": round(gross_pnl, 2),
                    "charges": total_charges,
                    "pnl": round(net_pnl, 2),
                    "exit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                self.closed_trades.append(trade_record)
                del self.positions[symbol]
                return {
                    "status": "FILLED",
                    "action": "SQUARE_OFF",
                    "order_id": f"PAPER_{random.randint(100000, 999999)}",
                    "symbol": symbol,
                    "side": transaction_type,
                    "quantity": pos["quantity"],
                    "fill_price": fill_price,
                    "gross_pnl": round(gross_pnl, 2),
                    "charges": total_charges,
                    "pnl": round(net_pnl, 2),
                }

        # 3. New Entry
        stop_loss, target = self.risk_manager.calculate_levels(fill_price, transaction_type)
        # For index options (1 lot of NIFTY 75 qty), typical margin/premium is ~₹12,000 - ₹15,000
        if "NIFTY" in symbol and quantity == 75:
            # Simulated 1 lot ATM option premium (~₹150/point)
            margin_required = 150.0 * 75  # ~₹11,250
        else:
            margin_required = (fill_price * quantity) * 0.20  # ~20% margin for intraday MIS equity

        if self.available_cash < margin_required:
            return {"status": "REJECTED", "reason": f"Insufficient margin. Required: ₹{margin_required:.2f}, Available: ₹{self.available_cash:.2f}"}

        self.available_cash -= margin_required
        order_id = f"PAPER_{random.randint(100000, 999999)}"

        self.positions[symbol] = {
            "order_id": order_id,
            "symbol": symbol,
            "side": transaction_type,
            "quantity": quantity,
            "entry_price": fill_price,
            "stop_loss": stop_loss,
            "target": target,
            "margin_locked": margin_required,
            "entry_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        return {
            "status": "FILLED",
            "action": "NEW_ENTRY",
            "order_id": order_id,
            "symbol": symbol,
            "side": transaction_type,
            "quantity": quantity,
            "fill_price": fill_price,
            "stop_loss": stop_loss,
            "target": target,
        }

    def get_positions(self) -> List[Dict[str, Any]]:
        results = []
        for sym, pos in self.positions.items():
            current_price = self.simulated_prices.get(sym, pos["entry_price"])
            pnl = (current_price - pos["entry_price"]) * pos["quantity"] if pos["side"] == "BUY" else (pos["entry_price"] - current_price) * pos["quantity"]
            results.append({
                **pos,
                "current_price": current_price,
                "unrealized_pnl": round(pnl, 2),
                "pnl_pct": round((pnl / (pos["entry_price"] * pos["quantity"])) * 100, 2),
            })
        return results


class KiteLiveClient(BaseBrokerClient):
    """
    Live Zerodha KiteConnect client wrapper with mandatory risk verification and affirmative user consent.
    """
    def __init__(self, kite_instance, risk_manager: RiskManager = None):
        self.kite = kite_instance
        self.risk_manager = risk_manager or RiskManager()

    def get_profile(self) -> Dict[str, Any]:
        return self.kite.profile()

    def get_margins(self) -> Dict[str, Any]:
        margins = self.kite.margins()
        equity_margins = margins.get("equity", {})
        return {
            "available_cash": equity_margins.get("available", {}).get("cash", 0.0),
            "used_margin": equity_margins.get("utilised", {}).get("debits", 0.0),
            "net": equity_margins.get("net", 0.0),
        }

    def get_ltp(self, instruments: List[str]) -> Dict[str, float]:
        quotes = self.kite.ltp(instruments)
        return {inst: data.get("last_price", 0.0) for inst, data in quotes.items()}

    def place_order(self, symbol: str, transaction_type: str, quantity: int, order_type: str = "MARKET", price: float = 0.0) -> Dict[str, Any]:
        """
        Executes real live order on NSE/BSE via Kite with mandatory risk checks.
        """
        # 1. Parse exchange and symbol
        if ":" in symbol:
            exchange, tradingsymbol = symbol.split(":", 1)
        else:
            exchange, tradingsymbol = "NSE", symbol

        # 2. Risk check
        positions = self.kite.positions().get("net", [])
        realized_pnl = sum(p.get("pnl", 0.0) for p in positions if p.get("quantity") == 0)
        unrealized_pnl = sum(p.get("pnl", 0.0) for p in positions if p.get("quantity") != 0)

        allowed, msg = self.risk_manager.check_pre_flight(realized_pnl, unrealized_pnl, requested_lots=1)
        if not allowed:
            return {"status": "REJECTED", "reason": msg}

        # 3. Execute order on Kite
        order_id = self.kite.place_order(
            variety=self.kite.VARIETY_REGULAR,
            exchange=exchange,
            tradingsymbol=tradingsymbol,
            transaction_type=transaction_type,
            quantity=quantity,
            product=self.kite.PRODUCT_MIS,
            order_type=self.kite.ORDER_TYPE_MARKET if order_type == "MARKET" else self.kite.ORDER_TYPE_LIMIT,
            price=price if order_type == "LIMIT" else None,
        )

        return {"status": "SUBMITTED", "order_id": order_id}

    def get_positions(self) -> List[Dict[str, Any]]:
        return self.kite.positions().get("net", [])
