"""
Trading Online - Algorithmic Trading Execution Engine & Dashboard.
Supports Paper Trading Simulation & Live Zerodha KiteConnect Execution.
"""
import time
import sys
import argparse
from datetime import datetime
import pandas as pd
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from config.settings import settings
from core.risk_manager import RiskManager
from core.client import PaperTradingClient, KiteLiveClient
from core.auth import KiteAuthManager
from core.forex import ForexEngine, CURRENCY_SPECS
from core.commodity import CommodityEngine, COMMODITY_SPECS
from strategies.supertrend_ema import SuperTrendEMAStrategy
from execution.journal import TradeJournal

console = Console()


def render_dashboard(client, strategy, symbol: str, current_ltp: float, last_signal: dict, risk_manager: RiskManager) -> Panel:
    margins = client.get_margins()
    positions = client.get_positions()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Table 1: Account & Risk Overview
    t_summary = Table(title="Portfolio & Capital Risk", expand=True)
    t_summary.add_column("Available Cash", justify="right", style="cyan")
    t_summary.add_column("Used Margin", justify="right", style="yellow")
    t_summary.add_column("Realized P&L", justify="right")
    t_summary.add_column("Unrealized P&L", justify="right")
    t_summary.add_column("Max Daily Risk", justify="right", style="red")

    realized_val = margins.get("realized_pnl", 0.0)
    unrealized_val = margins.get("unrealized_pnl", 0.0)

    realized_style = "green" if realized_val >= 0 else "bold red"
    unrealized_style = "green" if unrealized_val >= 0 else "bold red"

    t_summary.add_row(
        f"₹{margins.get('available_cash', 0.0):,.2f}",
        f"₹{margins.get('used_margin', 0.0):,.2f}",
        f"[{realized_style}]₹{realized_val:+,.2f}[/{realized_style}]",
        f"[{unrealized_style}]₹{unrealized_val:+,.2f}[/{unrealized_style}]",
        f"₹{risk_manager.max_daily_loss:,.2f}"
    )

    # Table 2: Active Positions
    t_pos = Table(title=f"Active Positions ({len(positions)})", expand=True)
    t_pos.add_column("Symbol", style="bold")
    t_pos.add_column("Side", justify="center")
    t_pos.add_column("Qty", justify="right")
    t_pos.add_column("Entry Price", justify="right")
    t_pos.add_column("Current Price", justify="right")
    t_pos.add_column("SL", justify="right", style="red")
    t_pos.add_column("Target", justify="right", style="green")
    t_pos.add_column("Unrealized P&L", justify="right")

    def fmt_price(sym: str, val: float) -> str:
        if ForexEngine.is_forex(sym):
            pfx = "$" if "INR" not in sym.upper() else "₹"
            return f"{pfx}{ForexEngine.format_price(sym, val)}"
        return f"₹{val:,.2f}"

    if not positions:
        t_pos.add_row("-", "-", "-", "-", "-", "-", "-", "[dim]No open positions[/dim]")
    else:
        for p in positions:
            pnl = p.get("unrealized_pnl", 0.0)
            p_style = "green" if pnl >= 0 else "red"
            side_style = "bold green" if p["side"] == "BUY" else "bold red"
            sym = p["symbol"]
            pfx = "$" if (ForexEngine.is_forex(sym) and "INR" not in sym.upper()) else "₹"
            t_pos.add_row(
                sym,
                f"[{side_style}]{p['side']}[/{side_style}]",
                str(p["quantity"]),
                fmt_price(sym, p['entry_price']),
                fmt_price(sym, p['current_price']),
                fmt_price(sym, p.get('stop_loss', 0.0)),
                fmt_price(sym, p.get('target', 0.0)),
                f"[{p_style}]{pfx}{pnl:+,.2f} ({p.get('pnl_pct', 0.0):+.2f}%)[/{p_style}]"
            )

    # Signal status
    action = last_signal.get("action", "HOLD")
    act_color = "green" if action == "BUY" else ("red" if action == "SELL" else "yellow")
    metrics = last_signal.get("metrics", {})
    regime = metrics.get("regime", "SCANNING")
    regime_color = "green" if regime == "TRENDING" else "yellow"
    signal_line = (
        f"[bold]Latest Signal on {symbol}:[/bold] [{act_color}]{action}[/{act_color}] | "
        f"Regime: [{regime_color}]{regime}[/{regime_color}] (ADX: {metrics.get('adx', 'N/A')}, CHOP: {metrics.get('chop', 'N/A')}) | "
        f"LTP: {fmt_price(symbol, current_ltp)} | "
        f"RSI: {metrics.get('rsi', 'N/A')} | "
        f"SuperTrend: {metrics.get('supertrend', 'N/A')}\n"
        f"[dim]Reason: {last_signal.get('reason', 'N/A')}[/dim]"
    )

    content = f"[bold cyan]⏰ System Time:[/bold cyan] {now_str} | [bold yellow]Mode:[/bold yellow] {'PAPER TRADING (Simulated)' if settings.paper_trading else 'LIVE ZERODHA'}\n"
    content += f"{signal_line}\n\n"

    table_group = Table.grid()
    table_group.add_row(t_summary)
    table_group.add_row(t_pos)

    return Panel(
        table_group,
        title=f"⚡ TRADING ONLINE - {symbol} ⚡",
        subtitle=f"Signal: {action} @ {fmt_price(symbol, current_ltp)} | Risk Limit: ₹{risk_manager.max_daily_loss:,.2f}",
        border_style="bright_blue",
    )


def generate_mock_candle_history(symbol: str, count: int = 50) -> pd.DataFrame:
    """Generates synthetic initial OHLCV candles for strategy warm-up."""
    is_fx = ForexEngine.is_forex(symbol)
    if is_fx:
        if "JPY" in symbol.upper():
            base_price = 154.20
            scale = 0.08
            decimals = 2
        elif "EURUSD" in symbol.upper():
            base_price = 1.0850
            scale = 0.0003
            decimals = 4
        elif "GBP" in symbol.upper():
            base_price = 107.50 if "INR" in symbol.upper() else 1.2950
            scale = 0.02 if "INR" in symbol.upper() else 0.0004
            decimals = 4
        else:
            base_price = 84.45
            scale = 0.012
            decimals = 4
    elif "NIFTY" in symbol:
        base_price = 24300.0
        scale = 15.0
        decimals = 2
    else:
        base_price = 1500.0
        scale = 2.0
        decimals = 2

    records = []
    price = base_price
    for i in range(count):
        change = float(np.random.normal(0, scale))
        o = price
        c = price + change
        h = max(o, c) + abs(float(np.random.normal(0, scale * 0.5)))
        l = min(o, c) - abs(float(np.random.normal(0, scale * 0.5)))
        v = int(np.random.uniform(50000, 200000))
        records.append({
            "timestamp": pd.Timestamp.now() - pd.Timedelta(minutes=(count - i) * 5),
            "open": round(o, decimals),
            "high": round(h, decimals),
            "low": round(l, decimals),
            "close": round(c, decimals),
            "volume": v,
        })
        price = c
    return pd.DataFrame(records)


def run_trading_session(iterations: int = 20, delay_seconds: float = 0.5):
    is_continuous = (iterations <= 0)
    console.print(Panel.fit(
        f"[bold green]Starting Algorithmic Trading Session ({'AUTONOMOUS INFINITE LOOP' if is_continuous else f'{iterations} TICKS'})[/bold green]\n"
        f"Mode: {'[bold yellow]PAPER TRADING (Zero Risk Simulation)[/bold yellow]' if settings.paper_trading else '[bold red]LIVE KITE EXECUTION[/bold red]'}\n"
        f"Symbol: [cyan]{settings.default_symbol}[/cyan] | Max Daily Loss: [red]₹{settings.max_daily_loss}[/red] | Lot Size: [green]{settings.max_lots}[/green]\n"
        f"[dim]{'Press Ctrl+C anytime to pause autonomous execution.' if is_continuous else ''}[/dim]",
        border_style="green"
    ))

    risk_manager = RiskManager()
    journal = TradeJournal()

    # Client Selection
    if settings.paper_trading:
        client = PaperTradingClient(risk_manager=risk_manager)
    else:
        auth_mgr = KiteAuthManager()
        kite_client = auth_mgr.get_kite_client()
        client = KiteLiveClient(kite_instance=kite_client, risk_manager=risk_manager)

    strategy = SuperTrendEMAStrategy()
    df_candles = generate_mock_candle_history(settings.default_symbol, count=40)

    last_signal = {"action": "HOLD", "reason": "System Initializing", "metrics": {}}

    step_count = 0
    try:
        while True:
            step_count += 1
            if not is_continuous and step_count > iterations:
                break

            # 1. Update market quote
            ltp_map = client.get_ltp([settings.default_symbol])
            current_ltp = ltp_map.get(settings.default_symbol, 24350.0)

            # 2. Append new bar / tick
            new_row = pd.DataFrame([{
                "timestamp": pd.Timestamp.now(),
                "open": round(df_candles["close"].iloc[-1], 2),
                "high": round(max(df_candles["close"].iloc[-1], current_ltp) + 2, 2),
                "low": round(min(df_candles["close"].iloc[-1], current_ltp) - 2, 2),
                "close": current_ltp,
                "volume": int(np.random.uniform(50000, 150000)),
            }])
            df_candles = pd.concat([df_candles.iloc[1:], new_row], ignore_index=True)

            # 3. Strategy Signal Evaluation
            last_signal = strategy.generate_signal(df_candles)

            # 4. Check Open Position Exits (Stop-Loss / Target)
            positions = client.get_positions()
            for pos in positions:
                sym = pos["symbol"]
                curr_price = pos["current_price"]
                side = pos["side"]
                sl = pos.get("stop_loss", 0.0)
                target = pos.get("target", 0.0)

                # Hit Stop Loss
                if (side == "BUY" and curr_price <= sl) or (side == "SELL" and curr_price >= sl):
                    exit_side = "SELL" if side == "BUY" else "BUY"
                    res = client.place_order(sym, exit_side, pos["quantity"])
                    journal.log_trade(res, mode="PAPER" if settings.paper_trading else "LIVE", reason=f"STOP-LOSS HIT @ ₹{curr_price}")
                    console.print(f"[bold red]❌ STOP-LOSS TRIGGERED on {sym} @ ₹{curr_price:.2f}[/bold red]")

                # Hit Target
                elif (side == "BUY" and curr_price >= target) or (side == "SELL" and curr_price <= target):
                    exit_side = "SELL" if side == "BUY" else "BUY"
                    res = client.place_order(sym, exit_side, pos["quantity"])
                    journal.log_trade(res, mode="PAPER" if settings.paper_trading else "LIVE", reason=f"PROFIT TARGET REACHED @ ₹{curr_price}")
                    console.print(f"[bold green]🎯 TARGET HIT on {sym} @ ₹{curr_price:.2f} (P&L: ₹{res.get('pnl', 0.0):+,.2f})[/bold green]")

            # 5. Check New Entry Signal
            if last_signal["action"] in ("BUY", "SELL") and len(positions) == 0:
                is_fx = ForexEngine.is_forex(settings.default_symbol)
                is_comm = CommodityEngine.is_commodity(settings.default_symbol)
                if is_comm:
                    trade_qty = CommodityEngine.get_lot_size(settings.default_symbol)
                elif is_fx:
                    trade_qty = 1000
                elif "NIFTY" in settings.default_symbol:
                    trade_qty = 75
                else:
                    trade_qty = 1

                res = client.place_order(
                    symbol=settings.default_symbol,
                    transaction_type=last_signal["action"],
                    quantity=trade_qty,
                )
                if res.get("status") == "FILLED":
                    journal.log_trade(res, mode="PAPER" if settings.paper_trading else "LIVE", reason=last_signal.get("reason", ""))
                    metrics = last_signal.get("metrics", {})
                    pfx = "$" if (is_fx and "INR" not in settings.default_symbol.upper()) else "₹"
                    fill_str = f"{pfx}{ForexEngine.format_price(settings.default_symbol, res.get('fill_price'))}" if is_fx else f"₹{res.get('fill_price'):,.2f}"
                    sl_str = f"{pfx}{ForexEngine.format_price(settings.default_symbol, res.get('stop_loss'))}" if is_fx else f"₹{res.get('stop_loss'):,.2f}"
                    tgt_str = f"{pfx}{ForexEngine.format_price(settings.default_symbol, res.get('target'))}" if is_fx else f"₹{res.get('target'):,.2f}"
                    why_panel = Panel(
                        f"[bold green]🚀 ORDER FILLED:[/bold green] {last_signal['action']} 1 Lot {settings.default_symbol} @ {fill_str}\n"
                        f"[bold cyan]🎯 Why Taken (AI Confluence Diagnosis):[/bold cyan]\n"
                        f"  1. [bold]Momentum Vector:[/bold] Fast EMA(9) @ {pfx}{metrics.get('ema_fast', 0):,.2f} {'above' if last_signal['action'] == 'BUY' else 'below'} Slow EMA(21) @ {pfx}{metrics.get('ema_slow', 0):,.2f}\n"
                        f"  2. [bold]Trend Structural Band:[/bold] SuperTrend (10,3) is [{ 'green' if metrics.get('supertrend') == 'BULLISH' else 'red' }]{metrics.get('supertrend', 'N/A')}[/]\n"
                        f"  3. [bold]Oscillator Validation:[/bold] RSI(14) is {metrics.get('rsi', 0):.1f} ({'Healthy Buying Acceleration' if last_signal['action'] == 'BUY' else 'Healthy Bearish Expansion'})\n"
                        f"  4. [bold]Risk Invariant:[/bold] Hard Stop-Loss set at {sl_str} | Target at {tgt_str} (1:2 Asymmetric R:R)\n"
                        f"  5. [bold]Primary Rationale:[/bold] {last_signal.get('reason', 'N/A')}",
                        title="💡 AI TRADE EXECUTION RATIONALE",
                        border_style="cyan"
                    )
                    console.print(why_panel)
                elif res.get("status") == "REJECTED":
                    console.print(f"[bold yellow]⚠️ ENTRY BLOCKED BY RISK GATE: {res.get('reason')}[/bold yellow]")

            # 6. Render Terminal Dashboard
            panel = render_dashboard(client, strategy, settings.default_symbol, current_ltp, last_signal, risk_manager)
            console.print(panel)

            time.sleep(delay_seconds)

    except KeyboardInterrupt:
        console.print("\n[bold yellow]⏸️ Autonomous Trading Paused by user (Ctrl+C).[/bold yellow]")
        console.print("[dim]All active positions and trade journals are safely preserved.[/dim]")

    console.print("\n[bold green]✅ Execution Cycle Completed.[/bold green]")


def display_history():
    from pathlib import Path
    journal_path = Path("data/trades.csv")
    if not journal_path.exists():
        console.print("[yellow]No trades recorded yet.[/yellow]")
        return
    df = pd.read_csv(journal_path)
    if df.empty:
        console.print("[yellow]Trade journal is empty.[/yellow]")
        return

    table = Table(title="📜 Trade Execution Journal & Audit Log", expand=True)
    table.add_column("Timestamp", style="dim")
    table.add_column("Order ID")
    table.add_column("Mode")
    table.add_column("Symbol", style="bold")
    table.add_column("Side")
    table.add_column("Qty", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("SL", justify="right", style="red")
    table.add_column("Target", justify="right", style="green")
    table.add_column("Action")
    table.add_column("P&L", justify="right")

    for _, row in df.iterrows():
        pnl = float(row.get("pnl", 0.0))
        pnl_str = f"₹{pnl:+,.2f}" if pnl != 0 else "-"
        p_style = "green" if pnl > 0 else ("red" if pnl < 0 else "dim")
        side_style = "bold green" if row.get("side") == "BUY" else "bold red"
        table.add_row(
            str(row.get("timestamp")),
            str(row.get("order_id")),
            str(row.get("mode")),
            str(row.get("symbol")),
            f"[{side_style}]{row.get('side')}[/{side_style}]",
            str(row.get("quantity")),
            f"₹{float(row.get('price', 0.0)):,.2f}",
            f"₹{float(row.get('stop_loss', 0.0)):,.2f}",
            f"₹{float(row.get('target', 0.0)):,.2f}",
            str(row.get("action")),
            f"[{p_style}]{pnl_str}[/{p_style}]"
        )
    console.print(table)


def run_live_feed(iterations: int = 30, delay_seconds: float = 1.0):
    console.print(Panel(
        "[bold cyan]🧠 AI REAL-TIME DECISION STREAM[/bold cyan]\n"
        "[dim]Streaming live tick-by-tick indicator math, AI thought process, and auto-executions.[/dim]",
        border_style="cyan"
    ))

    risk_manager = RiskManager()
    journal = TradeJournal()
    client = PaperTradingClient(risk_manager=risk_manager)
    strategy = SuperTrendEMAStrategy()
    df_candles = generate_mock_candle_history(settings.default_symbol, count=40)

    for i in range(1, iterations + 1):
        ltp_map = client.get_ltp([settings.default_symbol])
        current_ltp = ltp_map.get(settings.default_symbol, 24380.0)

        new_row = pd.DataFrame([{
            "timestamp": pd.Timestamp.now(),
            "open": round(df_candles["close"].iloc[-1], 2),
            "high": round(max(df_candles["close"].iloc[-1], current_ltp) + 1.5, 2),
            "low": round(min(df_candles["close"].iloc[-1], current_ltp) - 1.5, 2),
            "close": current_ltp,
            "volume": int(np.random.uniform(50000, 150000)),
        }])
        df_candles = pd.concat([df_candles.iloc[1:], new_row], ignore_index=True)

        signal = strategy.generate_signal(df_candles)
        metrics = signal.get("metrics", {})
        action = signal.get("action", "HOLD")

        # Live reasoning printout
        now_time = datetime.now().strftime("%H:%M:%S")
        act_style = "bold green" if action == "BUY" else ("bold red" if action == "SELL" else "yellow")
        
        console.print(
            f"[{now_time}] Tick #{i:02d} | LTP: [bold]₹{current_ltp:,.2f}[/bold] | "
            f"EMA9: ₹{metrics.get('ema_fast', 0):,.1f} | EMA21: ₹{metrics.get('ema_slow', 0):,.1f} | "
            f"RSI: {metrics.get('rsi', 0):.1f} | Trend: [magenta]{metrics.get('supertrend', 'N/A')}[/magenta] -> "
            f"AI Decision: [{act_style}]{action}[/{act_style}] ({signal.get('reason', '')})"
        )

        # Check Position Exits
        positions = client.get_positions()
        for pos in positions:
            sym = pos["symbol"]
            curr_price = pos["current_price"]
            side = pos["side"]
            sl = pos.get("stop_loss", 0.0)
            target = pos.get("target", 0.0)
            pnl = pos.get("unrealized_pnl", 0.0)
            pnl_style = "green" if pnl >= 0 else "red"

            console.print(f"       └─ 📊 Active Position: {side} 1 Lot @ ₹{pos['entry_price']:,.2f} | Unrealized P&L: [{pnl_style}]₹{pnl:+,.2f}[/{pnl_style}] (SL: ₹{sl:,.2f}, Target: ₹{target:,.2f})")

            # Check SL / Target
            if (side == "BUY" and curr_price <= sl) or (side == "SELL" and curr_price >= sl):
                exit_side = "SELL" if side == "BUY" else "BUY"
                res = client.place_order(sym, exit_side, pos["quantity"])
                journal.log_trade(res, mode="PAPER", reason=f"STOP-LOSS HIT @ ₹{curr_price}")
                console.print(f"       └─ [bold red]🛑 STOP-LOSS HIT: Squared off at ₹{curr_price:,.2f} (P&L: ₹{res.get('pnl', 0.0):+,.2f})[/bold red]")
            elif (side == "BUY" and curr_price >= target) or (side == "SELL" and curr_price <= target):
                exit_side = "SELL" if side == "BUY" else "BUY"
                res = client.place_order(sym, exit_side, pos["quantity"])
                journal.log_trade(res, mode="PAPER", reason=f"TARGET REACHED @ ₹{curr_price}")
                console.print(f"       └─ [bold green]🎯 PROFIT TARGET REACHED: Squared off at ₹{curr_price:,.2f} (P&L: ₹{res.get('pnl', 0.0):+,.2f})[/bold green]")

        # Check New Entry
        if action in ("BUY", "SELL") and len(positions) == 0:
            if CommodityEngine.is_commodity(settings.default_symbol):
                trade_qty = CommodityEngine.get_lot_size(settings.default_symbol)
            elif ForexEngine.is_forex(settings.default_symbol):
                trade_qty = 1000
            elif "NIFTY" in settings.default_symbol:
                trade_qty = 75
            else:
                trade_qty = 1

            res = client.place_order(
                symbol=settings.default_symbol,
                transaction_type=action,
                quantity=trade_qty,
            )
            if res.get("status") == "FILLED":
                journal.log_trade(res, mode="PAPER", reason=signal.get("reason", ""))
                console.print(f"       └─ [bold cyan]🚀 AUTO ORDER EXECUTED: {action} 1 Lot @ ₹{res.get('fill_price'):,.2f} (SL: ₹{res.get('stop_loss'):,.2f}, TGT: ₹{res.get('target'):,.2f})[/bold cyan]")

        time.sleep(delay_seconds)

    console.print("\n[bold green]✅ Live Feed Completed.[/bold green]")


def display_real_market():
    from core.real_market import RealMarketFeed
    console.print(Panel(
        "[bold green]🌐 CONNECTED TO REAL NATIONAL STOCK EXCHANGE (NSE) MARKET FEED[/bold green]\n"
        "[dim]Streaming actual live market quotes, real volume, and AI confluence on genuine exchange candles.[/dim]",
        border_style="green"
    ))

    table = Table(title="🏛️ Real NSE Market Board (Live Quotes)", expand=True)
    table.add_column("Symbol", style="bold")
    table.add_column("Exchange Ticker", style="dim")
    table.add_column("Real LTP (₹)", justify="right", style="bold cyan")
    table.add_column("Change", justify="right")
    table.add_column("Day High (₹)", justify="right", style="green")
    table.add_column("Day Low (₹)", justify="right", style="red")

    symbols = ["NSE:NIFTY 50", "NSE:BANKNIFTY", "NSE:RELIANCE", "NSE:TCS", "NSE:INFY", "NSE:HDFCBANK"]
    for sym in symbols:
        q = RealMarketFeed.get_real_quote(sym)
        chg = q.get("change_pct", 0.0)
        c_style = "bold green" if chg >= 0 else "bold red"
        table.add_row(
            sym,
            q.get("ticker", "N/A"),
            f"₹{q.get('ltp', 0.0):,.2f}",
            f"[{c_style}]{chg:+.2f}%[/{c_style}]",
            f"₹{q.get('high', 0.0):,.2f}",
            f"₹{q.get('low', 0.0):,.2f}"
        )
    console.print(table)

    # Real AI Analysis on genuine NIFTY 5-min candles
    console.print("\n[bold cyan]🧠 AI Strategy Diagnostics on Real NSE Candles:[/bold cyan]")
    df_real = RealMarketFeed.get_real_historical_candles("NSE:NIFTY 50", interval="5m", period="5d")
    if not df_real.empty:
        strategy = SuperTrendEMAStrategy()
        signal = strategy.generate_signal(df_real)
        metrics = signal.get("metrics", {})
        action = signal.get("action", "HOLD")
        act_color = "green" if action == "BUY" else ("red" if action == "SELL" else "yellow")

        console.print(Panel(
            f"[bold]Active Instrument:[/bold] NSE:NIFTY 50 (Genuine 5-Min Candles)\n"
            f"[bold]Real Exchange Close:[/bold] ₹{metrics.get('close', 0.0):,.2f}\n"
            f"[bold]EMA 9 (Fast):[/bold] ₹{metrics.get('ema_fast', 0.0):,.2f}  |  [bold]EMA 21 (Slow):[/bold] ₹{metrics.get('ema_slow', 0.0):,.2f}\n"
            f"[bold]RSI (14):[/bold] {metrics.get('rsi', 0.0):.1f}  |  [bold]SuperTrend:[/bold] {metrics.get('supertrend', 'N/A')}\n\n"
            f"[bold text-lg]AI Decision:[/bold text-lg] [{act_color}]{action}[/{act_color}] — {signal.get('reason', 'N/A')}",
            title="⚡ Live AI Analysis on Real NSE Market Data ⚡",
            border_style="bright_blue"
        ))


def display_crypto_status(exchange_id: str = None, symbol: str = None):
    """Fetches and displays live cryptocurrency exchange status and prices."""
    from core.crypto_client import CryptoClient
    client = CryptoClient(exchange_id=exchange_id)
    profile = client.get_profile()
    margins = client.get_margins()
    check_pairs = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
    if symbol and symbol not in check_pairs:
        check_pairs.insert(0, symbol)
    ltps = client.get_ltp(check_pairs)

    table = Table(title=f"🌐 Cryptocurrency Market Feeds ({profile['exchange']})", expand=True)
    table.add_column("Pair", style="bold cyan")
    table.add_column("Last Traded Price", justify="right", style="bold yellow")
    table.add_column("Status", justify="center", style="green")

    for pair, price in ltps.items():
        table.add_row(pair, f"${price:,.2f}" if price > 0 else "N/A", "LIVE FEED" if price > 0 else "ERROR")

    console.print(Panel(
        f"[bold]Exchange:[/bold] {profile['exchange']}\n"
        f"[bold]Execution Mode:[/bold] {profile['mode']}\n"
        f"[bold]Testnet Sandbox:[/bold] {'Enabled' if profile['testnet'] else 'Disabled'}\n"
        f"[bold]API Credentials Configured:[/bold] {'Yes' if profile['has_credentials'] else 'No (Public Market Data Only)'}\n"
        f"[bold]Available Cash:[/bold] ${margins.get('available_cash', 0.0):,.2f} USDT\n"
        f"[bold]Used Margin:[/bold] ${margins.get('used_margin', 0.0):,.2f} USDT\n"
        f"[bold]Portfolio Total:[/bold] ${margins.get('total_portfolio_value', 0.0):,.2f} USDT",
        title="⚡ Cryptocurrency Broker & Account Status ⚡",
        border_style="cyan"
    ))
    console.print(table)


def display_forex_market():
    """Fetches and displays real-time currency derivatives (NSE CDS) and global Forex market board."""
    from core.real_market import RealMarketFeed
    from core.forex import ForexEngine, CURRENCY_SPECS

    console.print(Panel(
        "[bold green]🌐 FOREX & NSE CURRENCY DERIVATIVES (CDS) COMMAND CENTER[/bold green]\n"
        "[dim]Institutional currency trading engine: Live Exchange LTP, Global 24/5 Sessions, Pip Value, and AI Confluence.[/dim]",
        border_style="green"
    ))

    # 1. Global Forex Sessions Tracker Table
    t_sessions = Table(title="🕒 Global Forex Trading Sessions & Market Clocks", expand=True)
    t_sessions.add_column("Session", style="bold")
    t_sessions.add_column("Region", style="cyan")
    t_sessions.add_column("IST Trading Hours", justify="center")
    t_sessions.add_column("Status", justify="center")
    t_sessions.add_column("Volatility", justify="center")
    t_sessions.add_column("Primary Currency Pairs", style="dim")

    sessions = ForexEngine.get_global_sessions()
    for s in sessions:
        status_str = "[bold green]🟢 ACTIVE[/bold green]" if s["is_active"] else "[dim]🔴 CLOSED[/dim]"
        t_sessions.add_row(
            s["name"],
            s["region"],
            s["hours_ist"],
            status_str,
            s["volatility"],
            s["key_pairs"]
        )
    console.print(t_sessions)

    # 2. NSE Currency Derivatives Segment (CDS) Live Table
    t_cds = Table(title="🏛️ NSE Currency Derivatives Segment (CDS) — Exchange Traded Futures", expand=True)
    t_cds.add_column("Pair", style="bold cyan")
    t_cds.add_column("Ticker", style="dim")
    t_cds.add_column("Live LTP (₹)", justify="right", style="bold yellow")
    t_cds.add_column("Change", justify="right")
    t_cds.add_column("Day High (₹)", justify="right", style="green")
    t_cds.add_column("Day Low (₹)", justify="right", style="red")
    t_cds.add_column("Lot Size", justify="right")
    t_cds.add_column("Pip Size", justify="right")
    t_cds.add_column("Tick Val / Lot", justify="right", style="cyan")
    t_cds.add_column("Approx Margin", justify="right", style="magenta")
    t_cds.add_column("STT Tax", justify="center", style="bold green")

    cds_pairs = ["CDS:USDINR", "CDS:EURINR", "CDS:GBPINR", "CDS:JPYINR"]
    for sym in cds_pairs:
        specs = ForexEngine.get_specs(sym) or {}
        q = RealMarketFeed.get_real_quote(sym)
        chg = q.get("change_pct", 0.0)
        c_style = "bold green" if chg >= 0 else "bold red"
        ltp = q.get("ltp", 0.0)
        decimals = specs.get("decimals", 4)
        ltp_str = f"₹{ltp:.{decimals}f}"
        high_str = f"₹{q.get('high', 0.0):.{decimals}f}"
        low_str = f"₹{q.get('low', 0.0):.{decimals}f}"

        t_cds.add_row(
            sym.replace("CDS:", ""),
            q.get("ticker", "N/A"),
            ltp_str,
            f"[{c_style}]{chg:+.2f}%[/{c_style}]",
            high_str,
            low_str,
            f"{specs.get('lot_size', 1000):,} units",
            f"{specs.get('pip_size', 0.0025)}",
            f"₹{specs.get('pip_value_inr', 2.50):.2f}",
            f"₹{specs.get('margin_approx_inr', 2500):,.0f}",
            "0% (Exempt)"
        )
    console.print(t_cds)

    # 3. Global Major Forex Pairs Table
    t_global = Table(title="🌍 Global Major Forex Pairs (24/5 Live Spot Feed)", expand=True)
    t_global.add_column("Pair", style="bold cyan")
    t_global.add_column("Ticker", style="dim")
    t_global.add_column("Spot Rate", justify="right", style="bold yellow")
    t_global.add_column("Change", justify="right")
    t_global.add_column("Day High", justify="right", style="green")
    t_global.add_column("Day Low", justify="right", style="red")
    t_global.add_column("Pip Size", justify="right")
    t_global.add_column("Std Lot Pip Value", justify="right", style="cyan")

    global_pairs = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF"]
    for sym in global_pairs:
        specs = ForexEngine.get_specs(sym) or {}
        q = RealMarketFeed.get_real_quote(sym)
        chg = q.get("change_pct", 0.0)
        c_style = "bold green" if chg >= 0 else "bold red"
        ltp = q.get("ltp", 0.0)
        decimals = specs.get("decimals", 4)
        ltp_str = f"{ltp:.{decimals}f}"
        high_str = f"{q.get('high', 0.0):.{decimals}f}"
        low_str = f"{q.get('low', 0.0):.{decimals}f}"
        pip_val = f"${specs.get('pip_value_usd', 10.0):.2f}"

        t_global.add_row(
            sym,
            q.get("ticker", "N/A"),
            ltp_str,
            f"[{c_style}]{chg:+.2f}%[/{c_style}]",
            high_str,
            low_str,
            f"{specs.get('pip_size', 0.0001)}",
            pip_val
        )
    console.print(t_global)

    # 4. Live Quantitative AI Strategy Diagnostics on Real Exchange Candles for USDINR
    console.print("\n[bold cyan]🧠 AI Strategy Diagnostics on Real Currency Candles (USDINR & EURUSD):[/bold cyan]")
    df_usdinr = RealMarketFeed.get_real_historical_candles("CDS:USDINR", interval="5m", period="5d")
    if not df_usdinr.empty:
        strategy = SuperTrendEMAStrategy()
        signal = strategy.generate_signal(df_usdinr)
        metrics = signal.get("metrics", {})
        action = signal.get("action", "HOLD")
        act_color = "green" if action == "BUY" else ("red" if action == "SELL" else "yellow")

        console.print(Panel(
            f"[bold]Active Pair:[/bold] CDS:USDINR (Genuine 5-Min Exchange Candles)\n"
            f"[bold]Real Exchange Rate:[/bold] ₹{metrics.get('close', 0.0):.4f}\n"
            f"[bold]EMA 9 (Fast):[/bold] ₹{metrics.get('ema_fast', 0.0):.4f}  |  [bold]EMA 21 (Slow):[/bold] ₹{metrics.get('ema_slow', 0.0):.4f}\n"
            f"[bold]RSI (14):[/bold] {metrics.get('rsi', 0.0):.1f}  |  [bold]SuperTrend:[/bold] {metrics.get('supertrend', 'N/A')}\n"
            f"[bold]Regime Filter:[/bold] {metrics.get('regime', 'SCANNING')} (ADX: {metrics.get('adx', 0.0):.1f}, CHOP: {metrics.get('chop', 0.0):.1f})\n\n"
            f"[bold text-lg]AI Decision:[/bold text-lg] [{act_color}]{action}[/{act_color}] — {signal.get('reason', 'N/A')}",
            title="⚡ Live AI Analysis on Real USD/INR Exchange Data ⚡",
            border_style="bright_blue"
        ))

    # 5. Regulatory & FEMA / SEBI Framework Overview Panel
    console.print(Panel(
        "[bold yellow]🏛️ Regulatory Compliance Framework for Indian Traders (SEBI & RBI Guidelines):[/bold yellow]\n"
        "• [bold green]LEGAL & REGULATED:[/bold green] Trading Currency Derivatives on SEBI-recognized Indian exchanges (NSE & BSE CDS) in INR pairs (USDINR, EURINR, GBPINR, JPYINR) and approved cross-currency pairs (EURUSD, GBPUSD, USDJPY).\n"
        "• [bold green]ZERO STT ADVANTAGE:[/bold green] Currency futures trade with 0% Securities Transaction Tax (STT), making statutory transaction costs significantly lower than equity options.\n"
        "• [bold red]RBI FEMA WARNING:[/bold red] Resident Indians are strictly prohibited under the Foreign Exchange Management Act (FEMA) from remitting funds through LRS to unauthorized offshore forex brokers / CFD apps.\n"
        "• [bold cyan]ZERODHA KITE CDS SUPPORT:[/bold cyan] Ensure 'Currency Derivatives' segment is activated in your Zerodha Console -> Account -> Segments to trade live contracts.",
        title="⚖️ Statutory & Compliance Guide",
        border_style="yellow"
    ))


def display_commodity_market(symbol: str = None):
    """Fetches and displays real-time MCX commodity intelligence, sessions, and live prices."""
    from core.real_market import RealMarketFeed
    from core.commodity import CommodityEngine, COMMODITY_SPECS

    console.print(Panel(
        "[bold yellow]⚡ MCX COMMODITIES & GLOBAL FUTURES COMMAND CENTER ⚡[/bold yellow]\n"
        "[dim]Trading hours: 09:00 AM – 11:30 PM / 11:55 PM IST | Peak Institutional Window: 18:30 – 22:30 IST | CTT: 0.05%[/dim]",
        border_style="yellow"
    ))

    # 1. Trading Sessions
    sessions = CommodityEngine.get_commodity_sessions()
    t_sess = Table(title="🕒 MCX Commodity Session Clocks & Volatility Tracker", expand=True)
    t_sess.add_column("Session Phase", style="bold cyan")
    t_sess.add_column("Trading Hours (IST)", justify="center")
    t_sess.add_column("Current Status", justify="center")
    t_sess.add_column("Institutional Regime & Liquidity", style="dim")

    for s in sessions:
        status_str = "[bold green]🟢 ACTIVE NOW[/bold green]" if s["active"] else "[dim]⚪ INACTIVE[/dim]"
        t_sess.add_row(s["phase"], s["hours"], status_str, f"{s['regime']} ({s['liquidity']})")
    console.print(t_sess)

    # 2. Major MCX Commodities Table
    check_syms = [
        "MCX:CRUDEOIL", "MCX:CRUDEOILM",
        "MCX:NATURALGAS", "MCX:NATGASMINI",
        "MCX:GOLD", "MCX:GOLDM",
        "MCX:SILVER", "MCX:SILVERMIC",
        "MCX:COPPER"
    ]
    if symbol and symbol not in check_syms:
        check_syms.insert(0, symbol)

    t_quotes = Table(title="📊 Major MCX Commodities & Benchmark Specifications", expand=True)
    t_quotes.add_column("Symbol", style="bold")
    t_quotes.add_column("Contract Name", style="cyan")
    t_quotes.add_column("Lot Size", justify="right")
    t_quotes.add_column("Benchmark LTP", justify="right", style="bold yellow")
    t_quotes.add_column("Point Value (₹)", justify="right", style="magenta")
    t_quotes.add_column("Approx Margin", justify="right", style="green")
    t_quotes.add_column("Statutory Tax", justify="center", style="blue")

    for sym in check_syms:
        specs = CommodityEngine.get_specs(sym)
        if not specs:
            continue
        q = RealMarketFeed.get_real_quote(sym)
        ltp_val = q.get("ltp", 0.0)
        tick_val = specs.get("tick_value_inr", 1.0)
        lot_sz = specs.get("lot_size", 1)
        margin_req = specs.get("margin_approx_inr", 0.0)

        in_inv, _ = CommodityEngine.is_inventory_window(sym)
        sym_display = f"[bold red]⚠️ {sym}[/bold red]" if in_inv else sym

        t_quotes.add_row(
            sym_display,
            specs.get("name", sym),
            f"{lot_sz} ({specs.get('unit', '')})",
            f"₹{ltp_val:,.2f}" if ltp_val > 0 else "N/A",
            f"₹{tick_val:,.1f} / pt",
            f"₹{margin_req:,.0f}",
            "0.05% CTT (No STT)"
        )
    console.print(t_quotes)

    # 3. Live AI Confluence Strategy Diagnostics on Real Benchmark Candles (Crude Oil & NatGas)
    console.print("\n[bold cyan]🧠 AI Strategy Diagnostics on Real Commodity Candles (Crude Oil & NatGas):[/bold cyan]")
    diag_syms = ["MCX:CRUDEOIL", "MCX:NATURALGAS"]
    for sym in diag_syms:
        df_candles = RealMarketFeed.get_real_historical_candles(sym, interval="5m", period="5d")
        if not df_candles.empty:
            strategy = SuperTrendEMAStrategy()
            sig = strategy.generate_signal(df_candles)
            m = sig.get("metrics", {})
            act = sig.get("action", "HOLD")
            act_col = "green" if act == "BUY" else ("red" if act == "SELL" else "yellow")
            console.print(Panel(
                f"[bold]Instrument:[/bold] {sym} ({COMMODITY_SPECS.get(sym, {}).get('name', '')})\n"
                f"[bold]Latest Close:[/bold] {m.get('close', 0.0):,.2f}  |  [bold]EMA 9 / 21:[/bold] {m.get('ema_fast', 0.0):,.2f} / {m.get('ema_slow', 0.0):,.2f}\n"
                f"[bold]SuperTrend:[/bold] {m.get('supertrend', 'N/A')}  |  [bold]RSI(14):[/bold] {m.get('rsi', 0.0):.1f}  |  [bold]ADX:[/bold] {m.get('adx', 0.0):.1f}\n"
                f"[bold]AI Action:[/bold] [{act_col}]{act}[/{act_col}] — {sig.get('reason', '')}",
                title=f"⚡ Live AI Diagnostics: {sym}",
                border_style="cyan"
            ))

    # 4. Inventory Alert Guidelines
    console.print(Panel(
        "[bold yellow]⚠️ High-Impact US Inventory Alerts & Strict Safety Rules:[/bold yellow]\n"
        " • [bold]Wednesdays (20:00 / 20:30 IST):[/bold] US EIA Crude Oil Inventory Reports\n"
        " • [bold]Thursdays (20:00 / 20:30 IST):[/bold] US EIA Natural Gas Storage Reports\n"
        " • [bold]Protocol:[/bold] Never enter within 15 minutes before/after these releases due to severe spread widening & slippage.",
        title="Institutional Risk Guard",
        border_style="red"
    ))


def main():
    parser = argparse.ArgumentParser(description="Trading Online - Algorithmic Trading Platform")
    parser.add_argument("--mode", choices=["paper", "live"], default="paper", help="Execution mode")
    parser.add_argument("--commodity", action="store_true", help="Launch MCX Commodity Trading Command Center & Live Intelligence")
    parser.add_argument("--forex", action="store_true", help="Launch Forex (Currencies) Command Center & Global Market Clocks")
    parser.add_argument("--crypto", action="store_true", help="Launch 24/7 Cryptocurrency Algorithmic Trading Engine")
    parser.add_argument("--exchange", type=str, default=None, help="Crypto exchange: binance, bybit, okx, kraken (default: binance)")
    parser.add_argument("--crypto-status", action="store_true", help="Display Crypto exchange balance, connection status, and live prices")
    parser.add_argument("--timeframe", type=str, default=None, help="Candle timeframe (e.g. '1m', '5m', '15m', '1h')")
    parser.add_argument("--login", action="store_true", help="Generate Zerodha Kite Login URL")
    parser.add_argument("--token", type=str, help="Complete login by providing request_token from Kite redirect")
    parser.add_argument("--status", action="store_true", help="Check broker margins and profile")
    parser.add_argument("--history", action="store_true", help="Display trade log and P&L history")
    parser.add_argument("--day", action="store_true", help="Simulate a full day intraday session and report total P&L")
    parser.add_argument("--power-hour", action="store_true", help="Take maximum risk maximum profit 8-lot Power Hour run")
    parser.add_argument("--learn", action="store_true", help="Analyze today's trades, extract lessons, and update market memory")
    parser.add_argument("--backtest", action="store_true", help="Run 500-candle quantitative backtest with Sharpe & Drawdown")
    parser.add_argument("--live-feed", action="store_true", help="Stream real-time AI thought process and trade logs")
    parser.add_argument("--monitor", action="store_true", help="Activate AI Chief Risk Officer & Market Sentinel Overseer")
    parser.add_argument("--real", action="store_true", help="Connect to the Real Live Market and stream actual NSE exchange quotes")
    parser.add_argument("--auto", action="store_true", help="Run autonomous 24/7 infinite trading loop")
    parser.add_argument("--symbol", type=str, default=None, help="Instrument symbol (e.g. 'NSE:NIFTY 50', 'NSE:RELIANCE')")
    parser.add_argument("--simulate", action="store_true", help="Run simulated trading loop")
    parser.add_argument("--ticks", type=int, default=10, help="Number of simulation ticks")

    args = parser.parse_args()

    if args.symbol:
        if CommodityEngine.is_commodity(args.symbol):
            settings.default_symbol = CommodityEngine.normalize_symbol(args.symbol)
        elif ForexEngine.is_forex(args.symbol):
            settings.default_symbol = ForexEngine.normalize_forex_symbol(args.symbol)
        else:
            settings.default_symbol = args.symbol

    if args.commodity:
        display_commodity_market(symbol=settings.default_symbol)
        return

    if args.forex:
        display_forex_market()
        return

    if args.history:
        display_history()
        return

    if args.day:
        from execution.day_simulator import run_full_day_session
        run_full_day_session(symbol=settings.default_symbol)
        return

    if args.power_hour:
        from execution.power_hour import run_power_hour_max_risk
        run_power_hour_max_risk(starting_price=24395.0, lots=8, ticks=30)
        return

    if args.learn:
        from core.market_learner import MarketLearner
        learner = MarketLearner()
        learner.analyze_session()
        return

    if args.backtest:
        from execution.backtester import run_strategy_backtest
        run_strategy_backtest(symbol=settings.default_symbol, num_candles=500)
        return

    if args.monitor:
        from core.expert_monitor import run_expert_monitor_loop
        run_expert_monitor_loop(ticks=args.ticks, delay=0.8)
        return

    if args.real:
        display_real_market()
        return

    if args.live_feed:
        run_live_feed(iterations=args.ticks, delay_seconds=0.7)
        return

    if args.login:
        auth_mgr = KiteAuthManager()
        try:
            url = auth_mgr.get_login_url()
            console.print(Panel(
                f"[bold cyan]1. Open this URL in your browser to sign in:[/bold cyan]\n[underline]{url}[/underline]\n\n"
                f"[bold yellow]2. After login, copy the 'request_token' parameter from the redirected URL.[/bold yellow]\n"
                f"[bold green]3. Run:[/bold green] uv run python main.py --token <request_token>",
                title="Zerodha KiteConnect Authentication",
                border_style="yellow"
            ))
        except Exception as e:
            console.print(f"[bold red]Error generating login URL:[/bold red] {e}")
        return

    if args.token:
        auth_mgr = KiteAuthManager()
        try:
            token = auth_mgr.complete_login(args.token)
            console.print(f"[bold green]🎉 Authentication Successful! Access Token saved for today's session.[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Login exchange failed:[/bold red] {e}")
        return

    if args.crypto_status:
        display_crypto_status(exchange_id=args.exchange, symbol=args.symbol)
        return

    if args.crypto:
        from execution.crypto_executor import run_crypto_live_loop
        crypto_symbol = args.symbol or settings.crypto_default_symbol
        crypto_exchange = args.exchange or settings.crypto_exchange
        crypto_timeframe = args.timeframe or settings.crypto_timeframe
        ticks_to_run = 0 if args.auto else args.ticks
        run_crypto_live_loop(
            symbol=crypto_symbol,
            exchange=crypto_exchange,
            timeframe=crypto_timeframe,
            ticks=ticks_to_run,
            delay=2.0 if args.auto else 1.0,
        )
        return

    if args.status:
        risk_mgr = RiskManager()
        client = PaperTradingClient(risk_manager=risk_mgr) if settings.paper_trading else KiteLiveClient(KiteAuthManager().get_kite_client(), risk_mgr)
        margins = client.get_margins()
        profile = client.get_profile()

        console.print(Panel(
            f"[bold]User Profile:[/bold] {profile.get('user_name', 'N/A')} ({profile.get('user_id', 'N/A')})\n"
            f"[bold]Available Cash:[/bold] ₹{margins.get('available_cash', 0.0):,.2f}\n"
            f"[bold]Used Margin:[/bold] ₹{margins.get('used_margin', 0.0):,.2f}\n"
            f"[bold]Realized P&L:[/bold] ₹{margins.get('realized_pnl', 0.0):,.2f}\n"
            f"[bold]Risk Circuit Breaker:[/bold] -₹{risk_mgr.max_daily_loss:,.2f}",
            title="Account Status",
            border_style="green"
        ))
        return

    # Action: run trading session (Continuous if --auto, else bounded by --ticks)
    ticks_to_run = 0 if args.auto else args.ticks
    run_trading_session(iterations=ticks_to_run, delay_seconds=0.7)


if __name__ == "__main__":
    main()
