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

    if not positions:
        t_pos.add_row("-", "-", "-", "-", "-", "-", "-", "[dim]No open positions[/dim]")
    else:
        for p in positions:
            pnl = p.get("unrealized_pnl", 0.0)
            p_style = "green" if pnl >= 0 else "red"
            side_style = "bold green" if p["side"] == "BUY" else "bold red"
            t_pos.add_row(
                p["symbol"],
                f"[{side_style}]{p['side']}[/{side_style}]",
                str(p["quantity"]),
                f"₹{p['entry_price']:,.2f}",
                f"₹{p['current_price']:,.2f}",
                f"₹{p.get('stop_loss', 0.0):,.2f}",
                f"₹{p.get('target', 0.0):,.2f}",
                f"[{p_style}]₹{pnl:+,.2f} ({p.get('pnl_pct', 0.0):+.2f}%)[/{p_style}]"
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
        f"LTP: ₹{current_ltp:,.2f} | "
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
        subtitle=f"Signal: {action} @ ₹{current_ltp:,.2f} | Risk Limit: ₹{risk_manager.max_daily_loss:,.2f}",
        border_style="bright_blue",
    )


def generate_mock_candle_history(symbol: str, count: int = 50) -> pd.DataFrame:
    """Generates synthetic initial OHLCV candles for strategy warm-up."""
    base_price = 24300.0 if "NIFTY" in symbol else 1500.0
    records = []
    price = base_price
    for i in range(count):
        change = float(np.random.normal(0, 15))
        o = price
        c = price + change
        h = max(o, c) + abs(float(np.random.normal(0, 8)))
        l = min(o, c) - abs(float(np.random.normal(0, 8)))
        v = int(np.random.uniform(50000, 200000))
        records.append({
            "timestamp": pd.Timestamp.now() - pd.Timedelta(minutes=(count - i) * 5),
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
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
                res = client.place_order(
                    symbol=settings.default_symbol,
                    transaction_type=last_signal["action"],
                    quantity=75,  # 1 Lot of NIFTY
                )
                if res.get("status") == "FILLED":
                    journal.log_trade(res, mode="PAPER" if settings.paper_trading else "LIVE", reason=last_signal.get("reason", ""))
                    metrics = last_signal.get("metrics", {})
                    why_panel = Panel(
                        f"[bold green]🚀 ORDER FILLED:[/bold green] {last_signal['action']} 1 Lot {settings.default_symbol} @ ₹{res.get('fill_price'):,.2f}\n"
                        f"[bold cyan]🎯 Why Taken (AI Confluence Diagnosis):[/bold cyan]\n"
                        f"  1. [bold]Momentum Vector:[/bold] Fast EMA(9) @ ₹{metrics.get('ema_fast', 0):,.1f} {'above' if last_signal['action'] == 'BUY' else 'below'} Slow EMA(21) @ ₹{metrics.get('ema_slow', 0):,.1f}\n"
                        f"  2. [bold]Trend Structural Band:[/bold] SuperTrend (10,3) is [{ 'green' if metrics.get('supertrend') == 'BULLISH' else 'red' }]{metrics.get('supertrend', 'N/A')}[/]\n"
                        f"  3. [bold]Oscillator Validation:[/bold] RSI(14) is {metrics.get('rsi', 0):.1f} ({'Healthy Buying Acceleration' if last_signal['action'] == 'BUY' else 'Healthy Bearish Expansion'})\n"
                        f"  4. [bold]Risk Invariant:[/bold] Hard Stop-Loss set at ₹{res.get('stop_loss'):,.2f} | Target at ₹{res.get('target'):,.2f} (1:2 Asymmetric R:R)\n"
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
            res = client.place_order(
                symbol=settings.default_symbol,
                transaction_type=action,
                quantity=75,
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


def main():
    parser = argparse.ArgumentParser(description="Trading Online - Algorithmic Trading Platform")
    parser.add_argument("--mode", choices=["paper", "live"], default="paper", help="Execution mode")
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
        settings.default_symbol = args.symbol

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
