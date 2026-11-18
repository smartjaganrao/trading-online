"""
Universal Cryptocurrency Broker Client using CCXT.
Supports Binance, Bybit, OKX, Kraken, and other global crypto exchanges.
Features:
- Live Real-Time Market Data & OHLCV Feed.
- Paper Trading simulation with live market prices & 10,000 USDT virtual wallet.
- Testnet / Sandbox mode for Binance Futures & Bybit.
- Real crypto maker/taker fee accounting & slippage drag modeling.
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
import random
import pandas as pd
import ccxt

from config.settings import settings
from core.client import BaseBrokerClient
from core.risk_manager import RiskManager
from execution.journal import calculate_crypto_transaction_costs, TradeJournal


class CryptoClient(BaseBrokerClient):
    """
    Unified Cryptocurrency Client abstraction.
    Works seamlessly across Binance, Bybit, OKX, Kraken, and other CCXT-supported exchanges.
    """
    def __init__(
        self,
        exchange_id: str = None,
        testnet: bool = None,
        api_key: str = None,
        api_secret: str = None,
        password: str = None,
        paper_trading: bool = None,
        risk_manager: RiskManager = None,
    ):
        self.exchange_id = (exchange_id or settings.crypto_exchange).lower()
        self.testnet = testnet if testnet is not None else settings.crypto_testnet
        self.api_key = api_key or settings.crypto_api_key
        self.api_secret = api_secret or settings.crypto_api_secret
        self.password = password or settings.crypto_api_password
        self.paper_trading = paper_trading if paper_trading is not None else settings.paper_trading

        self.risk_manager = risk_manager or RiskManager(is_crypto=True)
        self.journal = TradeJournal()

        # Paper trading virtual account state
        self.initial_capital = settings.crypto_paper_initial_capital
        self.available_cash = self.initial_capital  # USDT
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.closed_trades: List[Dict[str, Any]] = []

        # Fee schedule (Taker by default for Market orders, Maker for Limit)
        self.maker_fee = settings.crypto_maker_fee
        self.taker_fee = settings.crypto_taker_fee
        self.slippage_pct = settings.crypto_slippage_pct

        # Initialize CCXT exchange
        self.exchange = self._init_exchange()

    def _init_exchange(self) -> ccxt.Exchange:
        """Instantiates and configures the CCXT exchange instance."""
        if not hasattr(ccxt, self.exchange_id):
            raise ValueError(f"Unsupported exchange '{self.exchange_id}'. Choose from: binance, bybit, okx, kraken, etc.")

        exchange_class = getattr(ccxt, self.exchange_id)
        config: Dict[str, Any] = {
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",  # default to perpetual futures where supported
            },
        }

        if self.api_key and self.api_secret:
            config["apiKey"] = self.api_key
            config["secret"] = self.api_secret
            if self.password:
                config["password"] = self.password

        instance: ccxt.Exchange = exchange_class(config)

        # Enable sandbox / testnet mode if requested
        if self.testnet:
            try:
                instance.set_sandbox_mode(True)
            except Exception:
                # Some spot-only endpoints or exchanges do not have set_sandbox_mode
                pass

        return instance

    def get_profile(self) -> Dict[str, Any]:
        mode_str = "Paper Simulated (Live Market Feed)" if self.paper_trading else ("Testnet Sandbox" if self.testnet else "LIVE REAL CAPITAL")
        return {
            "exchange": self.exchange_id.upper(),
            "mode": mode_str,
            "testnet": self.testnet,
            "has_credentials": bool(self.api_key and self.api_secret),
            "status": "ONLINE",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        }

    def get_margins(self) -> Dict[str, Any]:
        """Returns account equity, available USDT margin, and realized/unrealized P&L."""
        if self.paper_trading:
            unrealized_pnl = self.get_unrealized_pnl()
            realized_pnl = self.get_realized_pnl()
            total_equity = self.available_cash + unrealized_pnl
            return {
                "currency": "USDT",
                "initial_capital": self.initial_capital,
                "available_cash": round(self.available_cash, 2),
                "used_margin": round(self.initial_capital - self.available_cash if self.available_cash < self.initial_capital else 0.0, 2),
                "realized_pnl": round(realized_pnl, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "total_portfolio_value": round(total_equity, 2),
            }
        else:
            try:
                balance = self.exchange.fetch_balance()
                usdt_info = balance.get("USDT", {})
                free_usdt = float(usdt_info.get("free", 0.0) or 0.0)
                used_usdt = float(usdt_info.get("used", 0.0) or 0.0)
                total_usdt = float(usdt_info.get("total", 0.0) or 0.0)
                return {
                    "currency": "USDT",
                    "available_cash": round(free_usdt, 2),
                    "used_margin": round(used_usdt, 2),
                    "total_portfolio_value": round(total_usdt, 2),
                    "realized_pnl": 0.0,
                    "unrealized_pnl": 0.0,
                }
            except Exception as e:
                return {
                    "currency": "USDT",
                    "available_cash": 0.0,
                    "used_margin": 0.0,
                    "total_portfolio_value": 0.0,
                    "error": str(e),
                }

    def get_ltp(self, instruments: List[str]) -> Dict[str, float]:
        """Fetches live Last Traded Price for requested symbols."""
        results = {}
        for symbol in instruments:
            try:
                ticker = self.exchange.fetch_ticker(symbol)
                results[symbol] = float(ticker.get("last") or ticker.get("close") or 0.0)
            except Exception as e:
                results[symbol] = 0.0
        return results

    def fetch_candles(self, symbol: str, timeframe: str = "5m", limit: int = 100) -> pd.DataFrame:
        """
        Fetches live historical OHLCV candlestick data from the exchange.
        Returns a clean pandas DataFrame ready for technical indicator calculation.
        """
        raw_candles = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(raw_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        return df

    def get_ticker_stats(self, symbol: str) -> Dict[str, Any]:
        """Returns 24h ticker summary (high, low, percentage change, volume)."""
        ticker = self.exchange.fetch_ticker(symbol)
        return {
            "symbol": symbol,
            "last": float(ticker.get("last", 0.0)),
            "high": float(ticker.get("high", 0.0)),
            "low": float(ticker.get("low", 0.0)),
            "percentage": float(ticker.get("percentage", 0.0)),
            "quote_volume": float(ticker.get("quoteVolume", 0.0)),
        }

    def get_realized_pnl(self) -> float:
        return sum(t.get("pnl", 0.0) for t in self.closed_trades)

    def get_unrealized_pnl(self) -> float:
        total = 0.0
        for symbol, pos in self.positions.items():
            try:
                current_price = self.get_ltp([symbol]).get(symbol, pos["entry_price"])
            except Exception:
                current_price = pos["entry_price"]

            if pos["side"] == "BUY":
                total += (current_price - pos["entry_price"]) * pos["quantity"]
            else:
                total += (pos["entry_price"] - current_price) * pos["quantity"]
        return round(total, 2)

    def place_order(
        self,
        symbol: str,
        transaction_type: str,
        quantity: float,
        order_type: str = "MARKET",
        price: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Executes order. In paper mode, executes with live market price + friction modeling.
        In live/testnet mode, executes via CCXT API.
        """
        # 1. Fetch live market price
        ltp = self.get_ltp([symbol]).get(symbol, 0.0)
        if ltp <= 0.0:
            return {"status": "REJECTED", "reason": f"Could not fetch live price for {symbol}"}

        fill_price = price if (order_type == "LIMIT" and price > 0) else ltp

        # 2. Risk Pre-Flight Check (24/7 continuous crypto check)
        realized = self.get_realized_pnl()
        unrealized = self.get_unrealized_pnl()
        allowed, msg = self.risk_manager.check_pre_flight(
            realized,
            unrealized,
            requested_lots=1,
            ignore_time_cutoff=True,
        )
        if not allowed:
            return {"status": "REJECTED", "reason": msg, "order_id": None}

        # 3. Paper Trading Execution
        if self.paper_trading:
            # Check if this closes/squares off an existing opposite position
            if symbol in self.positions:
                pos = self.positions[symbol]
                if pos["side"] != transaction_type.upper():
                    # Squaring off existing position
                    close_qty = min(pos["quantity"], quantity)
                    if pos["side"] == "BUY":
                        gross_pnl = (fill_price - pos["entry_price"]) * close_qty
                    else:
                        gross_pnl = (pos["entry_price"] - fill_price) * close_qty

                    costs = calculate_crypto_transaction_costs(
                        symbol=symbol,
                        quantity=close_qty,
                        entry_price=pos["entry_price"],
                        exit_price=fill_price,
                        maker_fee_pct=self.maker_fee,
                        taker_fee_pct=self.taker_fee,
                        slippage_pct=self.slippage_pct,
                        is_taker=(order_type == "MARKET"),
                    )
                    total_charges = costs["total_charges"]
                    net_pnl = round(gross_pnl - total_charges, 4)

                    self.available_cash += (pos["margin_locked"] + net_pnl)
                    trade_record = {
                        "symbol": symbol,
                        "side": pos["side"],
                        "exit_side": transaction_type.upper(),
                        "quantity": close_qty,
                        "entry_price": pos["entry_price"],
                        "exit_price": fill_price,
                        "gross_pnl": round(gross_pnl, 4),
                        "charges": total_charges,
                        "pnl": net_pnl,
                        "exit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    self.closed_trades.append(trade_record)
                    del self.positions[symbol]

                    self.journal.log_crypto_trade(
                        {
                            "order_id": f"CRYPTO_{random.randint(100000, 999999)}",
                            "symbol": symbol,
                            "side": transaction_type.upper(),
                            "quantity": close_qty,
                            "fill_price": fill_price,
                            "stop_loss": 0.0,
                            "target": 0.0,
                            "action": "SQUARE_OFF",
                            "gross_pnl": gross_pnl,
                            "charges": total_charges,
                            "pnl": net_pnl,
                        },
                        exchange=self.exchange_id,
                        mode="PAPER",
                        reason="Strategy Exit Signal",
                    )

                    return {
                        "status": "FILLED",
                        "action": "SQUARE_OFF",
                        "symbol": symbol,
                        "side": transaction_type.upper(),
                        "quantity": close_qty,
                        "fill_price": fill_price,
                        "gross_pnl": round(gross_pnl, 4),
                        "charges": total_charges,
                        "pnl": net_pnl,
                    }

            # New Entry Position
            stop_loss, target = self.risk_manager.calculate_levels(fill_price, transaction_type)
            margin_required = fill_price * quantity  # 1x spot/perp unleveraged margin

            if self.available_cash < margin_required:
                return {
                    "status": "REJECTED",
                    "reason": f"Insufficient margin. Required: ${margin_required:.2f} USDT, Available: ${self.available_cash:.2f} USDT",
                }

            self.available_cash -= margin_required
            order_id = f"CRYPTO_{random.randint(100000, 999999)}"

            self.positions[symbol] = {
                "order_id": order_id,
                "symbol": symbol,
                "side": transaction_type.upper(),
                "quantity": quantity,
                "entry_price": fill_price,
                "stop_loss": stop_loss,
                "target": target,
                "margin_locked": margin_required,
                "entry_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            self.journal.log_crypto_trade(
                {
                    "order_id": order_id,
                    "symbol": symbol,
                    "side": transaction_type.upper(),
                    "quantity": quantity,
                    "fill_price": fill_price,
                    "stop_loss": stop_loss,
                    "target": target,
                    "action": "NEW_ENTRY",
                    "gross_pnl": 0.0,
                    "charges": 0.0,
                    "pnl": 0.0,
                },
                exchange=self.exchange_id,
                mode="PAPER",
                reason="Strategy Confluence Entry",
            )

            return {
                "status": "FILLED",
                "action": "NEW_ENTRY",
                "order_id": order_id,
                "symbol": symbol,
                "side": transaction_type.upper(),
                "quantity": quantity,
                "fill_price": fill_price,
                "stop_loss": stop_loss,
                "target": target,
            }

        # 4. Live / Sandbox Execution via CCXT
        else:
            try:
                side = "buy" if transaction_type.upper() == "BUY" else "sell"
                type_ = "market" if order_type.upper() == "MARKET" else "limit"
                params = {}
                if order_type.upper() == "LIMIT":
                    order = self.exchange.create_order(symbol, type_, side, quantity, price, params)
                else:
                    order = self.exchange.create_order(symbol, type_, side, quantity, params=params)

                return {
                    "status": "SUBMITTED",
                    "order_id": order.get("id"),
                    "details": order,
                }
            except Exception as e:
                return {"status": "ERROR", "reason": str(e)}

    def get_positions(self) -> List[Dict[str, Any]]:
        """Returns open positions with unrealized P&L and ROI percentage."""
        if self.paper_trading:
            results = []
            for sym, pos in self.positions.items():
                current_price = self.get_ltp([sym]).get(sym, pos["entry_price"])
                if pos["side"] == "BUY":
                    pnl = (current_price - pos["entry_price"]) * pos["quantity"]
                else:
                    pnl = (pos["entry_price"] - current_price) * pos["quantity"]

                roi_pct = (pnl / pos["margin_locked"]) * 100 if pos["margin_locked"] > 0 else 0.0

                results.append({
                    **pos,
                    "current_price": current_price,
                    "unrealized_pnl": round(pnl, 2),
                    "roi_pct": round(roi_pct, 2),
                })
            return results
        else:
            try:
                # CCXT fetch_positions for derivative accounts
                if hasattr(self.exchange, "fetch_positions"):
                    positions = self.exchange.fetch_positions()
                    return [p for p in positions if float(p.get("contracts", 0) or 0) > 0]
                return []
            except Exception:
                return []
