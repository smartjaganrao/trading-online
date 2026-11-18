"""
Cryptocurrency Algorithmic Execution Engine & Terminal Dashboard.
Runs automated quantitative strategies (SuperTrend + EMA + ADX regime) on live crypto markets
via CCXT (Binance, Bybit, OKX, etc.) with real-time risk controls and transaction friction modeling.
"""
import time
from datetime import datetime
from typing import Optional
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live

from config.settings import settings
from core.crypto_client import CryptoClient
from core.risk_manager import RiskManager
from strategies.supertrend_ema import SuperTrendEMAStrategy

console = Console()


class CryptoExecutor:
    """
    Orchestrates live market data ingestion, strategy signal generation,
    and order execution for cryptocurrency pairs.
    """
    def __init__(
        self,
        symbol: str = None,
        exchange_id: str = None,
        timeframe: str = None,
        quantity: float = 0.05,
        client: CryptoClient = None,
    ):
        self.symbol = symbol or settings.crypto_default_symbol
        self.exchange_id = exchange_id or settings.crypto_exchange
        self.timeframe = timeframe or settings.crypto_timeframe
        self.quantity = quantity

        self.risk_manager = RiskManager(is_crypto=True)
        self.client = client or CryptoClient(
            exchange_id=self.exchange_id,
            risk_manager=self.risk_manager,
        )
        self.strategy = SuperTrendEMAStrategy()

    def run_cycle(self) -> dict:
        """
        Executes one evaluation cycle:
        1. Fetch latest OHLCV candles
        2. Compute technical indicators
        3. Generate signal
        4. Check and execute orders or SL/TP
        """
        # Fetch live candles
        df = self.client.fetch_candles(self.symbol, timeframe=self.timeframe, limit=100)
        df = self.strategy.calculate_indicators(df)
        signal_data = self.strategy.generate_signal(df)

        current_price = float(df["close"].iloc[-1])
        positions = self.client.get_positions()

        # Check existing positions for SL or Target hit
        for pos in positions:
            if pos["symbol"] == self.symbol:
                entry_price = pos["entry_price"]
                sl = pos.get("stop_loss", 0.0)
                tp = pos.get("target", 0.0)

                # Buy position exit check
                if pos["side"] == "BUY":
                    if current_price <= sl and sl > 0:
                        self.client.place_order(self.symbol, "SELL", pos["quantity"])
                        signal_data["action_taken"] = f"STOP LOSS HIT at ${current_price:,.2f}"
                    elif current_price >= tp and tp > 0:
                        self.client.place_order(self.symbol, "SELL", pos["quantity"])
                        signal_data["action_taken"] = f"TARGET HIT at ${current_price:,.2f}"
                # Sell position exit check
                elif pos["side"] == "SELL":
                    if current_price >= sl and sl > 0:
                        self.client.place_order(self.symbol, "BUY", pos["quantity"])
                        signal_data["action_taken"] = f"STOP LOSS HIT at ${current_price:,.2f}"
                    elif current_price <= tp and tp > 0:
                        self.client.place_order(self.symbol, "BUY", pos["quantity"])
                        signal_data["action_taken"] = f"TARGET HIT at ${current_price:,.2f}"

        # If no position open and strong signal triggered
        action = signal_data.get("action", "HOLD")
        if not positions and action in ("BUY", "SELL"):
            order_res = self.client.place_order(
                symbol=self.symbol,
                transaction_type=action,
                quantity=self.quantity,
            )
            signal_data["order_result"] = order_res

        return {
            "symbol": self.symbol,
            "current_price": current_price,
            "signal_data": signal_data,
            "df": df,
            "positions": self.client.get_positions(),
            "margins": self.client.get_margins(),
            "profile": self.client.get_profile(),
        }

    def render_dashboard(self, cycle_data: dict) -> Panel:
        """Constructs a Rich terminal view of the crypto bot's live status."""
        margins = cycle_data["margins"]
        positions = cycle_data["positions"]
        profile = cycle_data["profile"]
        signal = cycle_data["signal_data"]
        df = cycle_data["df"]
        current_price = cycle_data["current_price"]

        last_row = df.iloc[-1]
        adx_val = float(last_row.get("adx", 0.0))
        chop_val = float(last_row.get("chop", 0.0))
        rsi_val = float(last_row.get("rsi", 50.0))
        ema_f = float(last_row.get("ema_fast", 0.0))
        ema_s = float(last_row.get("ema_slow", 0.0))
        st_dir = "BULLISH" if last_row.get("supertrend_bullish", True) else "BEARISH"

        # Table 1: Account & Margins
        t_acc = Table(title=f"Account & Risk ({profile['exchange']} - {profile['mode']})", expand=True)
        t_acc.add_column("Available USDT", justify="right", style="cyan")
        t_acc.add_column("Locked Margin", justify="right", style="yellow")
        t_acc.add_column("Realized P&L", justify="right")
        t_acc.add_column("Unrealized P&L", justify="right")
        t_acc.add_column("Portfolio Value", justify="right", style="bold white")

        r_pnl = margins.get("realized_pnl", 0.0)
        u_pnl = margins.get("unrealized_pnl", 0.0)
        r_style = "green" if r_pnl >= 0 else "bold red"
        u_style = "green" if u_pnl >= 0 else "bold red"

        t_acc.add_row(
            f"${margins.get('available_cash', 0.0):,.2f}",
            f"${margins.get('used_margin', 0.0):,.2f}",
            f"[{r_style}]${r_pnl:+,.2f}[/{r_style}]",
            f"[{u_style}]${u_pnl:+,.2f}[/{u_style}]",
            f"${margins.get('total_portfolio_value', 0.0):,.2f}",
        )

        # Table 2: Active Positions
        t_pos = Table(title=f"Open Positions ({len(positions)})", expand=True)
        t_pos.add_column("Symbol", style="bold")
        t_pos.add_column("Side", justify="center")
        t_pos.add_column("Qty", justify="right")
        t_pos.add_column("Entry Price", justify="right")
        t_pos.add_column("Mark Price", justify="right")
        t_pos.add_column("Stop Loss", justify="right", style="red")
        t_pos.add_column("Target (TP)", justify="right", style="green")
        t_pos.add_column("Unrealized ROI", justify="right")

        if not positions:
            t_pos.add_row("-", "-", "-", "-", "-", "-", "-", "[dim]No active crypto positions[/dim]")
        else:
            for p in positions:
                pnl = p.get("unrealized_pnl", 0.0)
                roi = p.get("roi_pct", 0.0)
                p_style = "green" if pnl >= 0 else "red"
                s_style = "bold green" if p["side"] == "BUY" else "bold red"
                t_pos.add_row(
                    p["symbol"],
                    f"[{s_style}]{p['side']}[/{s_style}]",
                    f"{p['quantity']:.4f}",
                    f"${p['entry_price']:,.2f}",
                    f"${p['current_price']:,.2f}",
                    f"${p.get('stop_loss', 0.0):,.2f}",
                    f"${p.get('target', 0.0):,.2f}",
                    f"[{p_style}]${pnl:+,.2f} ({roi:+.2f}%)[/{p_style}]",
                )

        # Table 3: Live Signal & Indicators
        t_sig = Table(title=f"Market Intelligence: {self.symbol} ({self.timeframe})", expand=True)
        t_sig.add_column("LTP", justify="right", style="bold yellow")
        t_sig.add_column("SuperTrend", justify="center")
        t_sig.add_column("EMA (9 / 21)", justify="center")
        t_sig.add_column("RSI (14)", justify="center")
        t_sig.add_column("ADX (Trend)", justify="center")
        t_sig.add_column("Choppiness", justify="center")
        t_sig.add_column("Algo Verdict", justify="center")

        st_style = "bold green" if st_dir == "BULLISH" else "bold red"
        ema_style = "green" if ema_f > ema_s else "red"
        rsi_style = "bold red" if rsi_val > 70 else ("bold green" if rsi_val < 30 else "cyan")
        adx_style = "bold green" if adx_val >= 22.0 else "yellow"
        chop_style = "yellow" if chop_val >= 61.8 else "green"

        verdict = signal.get("action", "HOLD")
        verdict_style = "bold green" if verdict == "BUY" else ("bold red" if verdict == "SELL" else "dim yellow")

        t_sig.add_row(
            f"${current_price:,.2f}",
            f"[{st_style}]{st_dir}[/{st_style}]",
            f"[{ema_style}]{ema_f:,.1f} / {ema_s:,.1f}[/{ema_style}]",
            f"[{rsi_style}]{rsi_val:.1f}[/{rsi_style}]",
            f"[{adx_style}]{adx_val:.1f} ({'Strong' if adx_val >= 22 else 'Weak'})[/{adx_style}]",
            f"[{chop_style}]{chop_val:.1f} ({'Chop' if chop_val >= 61.8 else 'Trending'})[/{chop_style}]",
            f"[{verdict_style}]{verdict}[/{verdict_style}]",
        )

        content = Table.grid(padding=1)
        content.add_row(t_acc)
        content.add_row(t_pos)
        content.add_row(t_sig)

        return Panel(
            content,
            title=f"⚡ [bold cyan]Trading Online: Crypto Engine[/bold cyan] | [white]{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}[/white]",
            border_style="cyan",
        )


def run_crypto_live_loop(symbol: str = "BTC/USDT", exchange: str = "binance", timeframe: str = "5m", ticks: int = 10, delay: float = 2.0):
    """Runs live evaluation loop with Rich Live terminal rendering."""
    executor = CryptoExecutor(symbol=symbol, exchange_id=exchange, timeframe=timeframe)
    console.print(f"[bold cyan]Connecting to {exchange.upper()} for {symbol} ({timeframe})...[/bold cyan]")

    count = 0
    with Live(console=console, refresh_per_second=2) as live:
        while True:
            cycle_data = executor.run_cycle()
            panel = executor.render_dashboard(cycle_data)
            live.update(panel)

            count += 1
            if ticks > 0 and count >= ticks:
                break
            time.sleep(delay)

    console.print(f"\n[bold green]✓ Completed {count} crypto market monitoring cycles.[/bold green]")
