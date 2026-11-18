"""
Full-Day Paper Trading Session Simulator & Performance Analytics.
Simulates a complete intraday trading day (9:15 AM to 3:15 PM IST = 72 five-minute candles)
and computes exact realized Profit & Loss, Win Rate, and Risk Metrics.
"""
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from config.settings import settings
from core.risk_manager import RiskManager
from core.client import PaperTradingClient
from core.forex import ForexEngine
from strategies.supertrend_ema import SuperTrendEMAStrategy
from execution.journal import TradeJournal, calculate_transaction_costs

console = Console()


def generate_intraday_day_data(symbol: str = "NSE:NIFTY 50", seed: int = 42) -> pd.DataFrame:
    """
    Generates realistic 5-minute candle intraday price action for today (9:15 AM - 3:15 PM = 72 candles).
    Simulates morning opening momentum, midday consolidation, and afternoon trend expansion.
    """
    np.random.seed(seed)
    start_time = datetime.now().replace(hour=9, minute=15, second=0, microsecond=0)
    
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
        else: # USDINR default
            base_price = 84.45
            scale = 0.012
            decimals = 4
    elif "NIFTY" in symbol:
        base_price = 24350.0
        scale = 7.0
        decimals = 2
    else:
        base_price = 1280.0
        scale = 1.5
        decimals = 2

    records = []
    current_price = base_price

    # Market regime:
    # 09:15 - 10:30: Initial opening swing (candles 0-15)
    # 10:30 - 13:00: Midday range/pullback (candles 16-45)
    # 13:00 - 15:15: Afternoon trend run (candles 46-72)
    
    for i in range(72):
        candle_time = start_time + timedelta(minutes=i * 5)
        
        if i < 15:
            # Bullish morning gap & rally
            step = float(np.random.normal(0.4 * scale, 1.1 * scale))
        elif i < 45:
            # Midday choppy pullback
            step = float(np.random.normal(-0.15 * scale, 0.9 * scale))
        else:
            # Afternoon expansion
            step = float(np.random.normal(0.5 * scale, 1.1 * scale))

        open_p = current_price
        close_p = open_p + step
        high_p = max(open_p, close_p) + abs(float(np.random.normal(0.25 * scale, 0.4 * scale)))
        low_p = min(open_p, close_p) - abs(float(np.random.normal(0.25 * scale, 0.4 * scale)))
        vol = int(np.random.uniform(70000, 250000))

        records.append({
            "timestamp": candle_time,
            "open": round(open_p, decimals),
            "high": round(high_p, decimals),
            "low": round(low_p, decimals),
            "close": round(close_p, decimals),
            "volume": vol
        })
        current_price = close_p

    return pd.DataFrame(records)


def run_full_day_session(symbol: str = "NSE:NIFTY 50") -> dict:
    is_fx = ForexEngine.is_forex(symbol)
    lot_desc = "1 Lot (1,000 units)" if is_fx else ("1 Lot (75 qty)" if "NIFTY" in symbol else "1 Unit")
    console.print(Panel(
        f"[bold cyan]🗓️ SIMULATING FULL INTRADAY SESSION (9:15 AM - 3:15 PM IST)[/bold cyan]\n"
        f"Symbol: [bold yellow]{symbol}[/bold yellow] | Lot Size: [green]{lot_desc}[/green] | Strategy: [magenta]SuperTrend + Dual EMA[/magenta]",
        border_style="cyan"
    ))

    risk_mgr = RiskManager(is_forex=is_fx)
    client = PaperTradingClient(risk_manager=risk_mgr)
    strategy = SuperTrendEMAStrategy()
    journal = TradeJournal()

    df_day = generate_intraday_day_data(symbol)
    
    # Warm-up history with first 25 candles
    warmup_count = 25
    active_position = None
    trades_executed = []

    for i in range(warmup_count, len(df_day)):
        current_slice = df_day.iloc[:i + 1]
        last_candle = current_slice.iloc[-1]
        current_price = last_candle["close"]
        candle_time = last_candle["timestamp"].strftime("%H:%M")

        # 1. Update Mock Price in Broker
        client.update_mock_price(symbol, current_price)

        # 2. Check Active Position for SL / Target
        if active_position:
            side = active_position["side"]
            entry_p = active_position["entry_price"]
            sl = active_position["stop_loss"]
            target = active_position["target"]
            qty = active_position["quantity"]

            hit_sl = (side == "BUY" and current_price <= sl) or (side == "SELL" and current_price >= sl)
            hit_tgt = (side == "BUY" and current_price >= target) or (side == "SELL" and current_price <= target)
            is_eod = (i == len(df_day) - 1)  # 3:15 PM mandatory square off

            if hit_sl or hit_tgt or is_eod:
                exit_reason = "PROFIT TARGET REACHED" if hit_tgt else ("STOP-LOSS TRIGGERED" if hit_sl else "3:15 PM MANDATORY SQUARE-OFF")
                diff = (current_price - entry_p) if side == "BUY" else (entry_p - current_price)
                gross_pnl = round(diff * qty, 2)
                costs = calculate_transaction_costs(symbol, side, qty, entry_p, current_price)
                net_pnl = round(gross_pnl - costs["total_charges"], 2)

                trade_record = {
                    "entry_time": active_position["entry_time"],
                    "exit_time": candle_time,
                    "symbol": symbol,
                    "side": side,
                    "quantity": qty,
                    "entry_price": entry_p,
                    "exit_price": current_price,
                    "gross_pnl": gross_pnl,
                    "charges": costs["total_charges"],
                    "pnl": net_pnl,
                    "reason": exit_reason
                }
                trades_executed.append(trade_record)

                # Log to CSV
                journal.log_trade({
                    "order_id": active_position["order_id"],
                    "symbol": symbol,
                    "side": side,
                    "quantity": qty,
                    "fill_price": current_price,
                    "stop_loss": sl,
                    "target": target,
                    "action": "SQUARE_OFF",
                    "gross_pnl": gross_pnl,
                    "charges": costs["total_charges"],
                    "pnl": net_pnl,
                }, mode="PAPER", reason=exit_reason)

                active_position = None
                continue

        # 3. Strategy Signal Evaluation (Only if no active position & before 3:00 PM)
        if not active_position and i < len(df_day) - 3:
            # Enforce Risk Circuit Breaker Gate & Midday Whipsaw Filter
            current_realized = sum(t["pnl"] for t in trades_executed)
            candle_t = last_candle["timestamp"].time()
            allowed, msg = risk_mgr.check_pre_flight(current_realized, 0.0, requested_lots=1, check_time=candle_t)
            if not allowed:
                # If circuit breaker is triggered (loss limit breached), stop day
                if "CIRCUIT BREAKER" in msg:
                    break
                # If midday pause or time restriction, just skip entry for this candle
                continue

            signal = strategy.generate_signal(current_slice)
            action = signal.get("action", "HOLD")

            if action in ("BUY", "SELL"):
                is_fx = ForexEngine.is_forex(symbol)
                qty = 1000 if is_fx else (75 if "NIFTY" in symbol else 1)
                sl, tgt = risk_mgr.calculate_levels(current_price, action)
                order_id = f"PAPER_{np.random.randint(100000, 999999)}"
                active_position = {
                    "order_id": order_id,
                    "entry_time": candle_time,
                    "side": action,
                    "entry_price": current_price,
                    "quantity": qty,
                    "stop_loss": sl,
                    "target": tgt
                }
                # Log entry
                journal.log_trade({
                    "order_id": order_id,
                    "symbol": symbol,
                    "side": action,
                    "quantity": qty,
                    "fill_price": current_price,
                    "stop_loss": sl,
                    "target": tgt,
                    "action": "NEW_ENTRY",
                    "pnl": 0.0,
                }, mode="PAPER", reason=signal.get("reason", ""))

    # Performance Analytics Calculation
    total_trades = len(trades_executed)
    winning_trades = [t for t in trades_executed if t["pnl"] > 0]
    losing_trades = [t for t in trades_executed if t["pnl"] < 0]
    
    total_profit = sum(t["pnl"] for t in winning_trades)
    total_loss = sum(t["pnl"] for t in losing_trades)
    net_pnl = total_profit + total_loss
    
    win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0.0
    profit_factor = (abs(total_profit / total_loss)) if total_loss != 0 else float("inf")

    # Render Table of Trades
    table = Table(title="📜 Today's Intraday Paper Trading Summary", expand=True)
    table.add_column("Entry", style="dim")
    table.add_column("Exit", style="dim")
    table.add_column("Side", justify="center")
    table.add_column("Qty", justify="right")
    table.add_column("Entry Price", justify="right")
    table.add_column("Exit Price", justify="right")
    table.add_column("P&L (₹)", justify="right")
    table.add_column("Exit Trigger", style="italic")

    for t in trades_executed:
        pnl = t["pnl"]
        p_style = "bold green" if pnl >= 0 else "bold red"
        side_style = "bold green" if t["side"] == "BUY" else "bold red"
        table.add_row(
            t["entry_time"],
            t["exit_time"],
            f"[{side_style}]{t['side']}[/{side_style}]",
            str(t["quantity"]),
            f"₹{t['entry_price']:,.2f}",
            f"₹{t['exit_price']:,.2f}",
            f"[{p_style}]₹{pnl:+,.2f}[/{p_style}]",
            t["reason"]
        )

    console.print(table)

    # Render Summary Performance Card
    pnl_color = "bold green" if net_pnl >= 0 else "bold red"
    summary_text = (
        f"[bold]Total Trades:[/bold] {total_trades}  |  "
        f"[bold green]Wins:[/bold green] {len(winning_trades)}  |  "
        f"[bold red]Losses:[/bold red] {len(losing_trades)}  |  "
        f"[bold cyan]Win Rate:[/bold cyan] {win_rate:.1f}%\n"
        f"[bold]Gross Profit:[/bold] [green]₹{total_profit:+,.2f}[/green]  |  "
        f"[bold]Gross Loss:[/bold] [red]₹{total_loss:+,.2f}[/red]  |  "
        f"[bold]Profit Factor:[/bold] {profit_factor:.2f}\n"
        f"[bold text-lg]Net Realized P&L:[/bold text-lg] [{pnl_color}]₹{net_pnl:+,.2f}[/{pnl_color}] "
        f"([cyan]{(net_pnl / 100000.0) * 100:+.2f}% on ₹1,00,000 capital[/cyan])"
    )
    console.print(Panel(summary_text, title="🏁 Day P&L Performance Report", border_style="green" if net_pnl >= 0 else "red"))

    return {
        "total_trades": total_trades,
        "wins": len(winning_trades),
        "losses": len(losing_trades),
        "win_rate": win_rate,
        "gross_profit": total_profit,
        "gross_loss": total_loss,
        "net_pnl": net_pnl,
        "trades": trades_executed
    }
