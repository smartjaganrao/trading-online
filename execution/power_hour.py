"""
Power Hour Maximum-Risk Maximum-Profit Aggressive Engine (Paper Trading).
Simulates full capital deployment (8 Lots = 600 Qty NIFTY) during the 2:45 PM - 3:15 PM Power Hour window.
Features dynamic gamma volatility, trailing stop locks, and auto 3:15 PM square-off.
"""
from datetime import datetime, timedelta
import time
import pandas as pd
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from config.settings import settings
from execution.journal import TradeJournal, calculate_transaction_costs

console = Console()


def run_power_hour_max_risk(starting_price: float = 24395.0, lots: int = 8, ticks: int = 30):
    qty = lots * 75  # 8 lots = 600 quantity
    margin_deployed = lots * 11250.0  # ₹90,000 deployed (90% of capital)
    
    console.print(Panel(
        f"[bold red]⚡ POWER HOUR MAXIMUM RISK AGGRESSIVE MODE (PAPER TRADING)[/bold red]\n"
        f"[bold yellow]Capital Deployed:[/bold yellow] ₹{margin_deployed:,.2f} ([bold red]90% OF ₹1,00,000 CAPITAL[/bold red])\n"
        f"[bold yellow]Position Sizing:[/bold yellow] [bold cyan]{lots} Lots ({qty} Qty)[/bold cyan] of NSE:NIFTY 50\n"
        f"[bold yellow]Leverage Sensitivity:[/bold yellow] [bold green]Every 1 Point move = ₹{qty:,.2f} P&L[/bold green]\n"
        f"[bold yellow]Cutoff Window:[/bold yellow] 2:45 PM to 3:15 PM (Intraday Power Hour)",
        border_style="red"
    ))

    journal = TradeJournal()
    price = starting_price
    entry_price = price
    side = "BUY"  # Trend continuation breakout
    order_id = f"POWER_{np.random.randint(100000, 999999)}"

    # Aggressive Levels
    stop_loss = round(entry_price - 25.0, 2)  # -25 pts initial risk = -₹15,000 max loss
    target = round(entry_price + 60.0, 2)     # +60 pts target = +₹36,000 profit (+36%)
    trailing_sl = stop_loss
    peak_price = entry_price
    peak_pnl = 0.0

    journal.log_trade({
        "order_id": order_id,
        "symbol": "NSE:NIFTY 50",
        "side": side,
        "quantity": qty,
        "fill_price": entry_price,
        "stop_loss": stop_loss,
        "target": target,
        "action": "POWER_HOUR_ENTRY",
        "pnl": 0.0,
    }, mode="PAPER", reason="Aggressive Power Hour Breakout (8 Lots Full Margin)")

    console.print(f"[bold green]🚀 ORDER FILLED: BUY {lots} Lots ({qty} Qty) @ ₹{entry_price:,.2f} | Initial SL: ₹{stop_loss:,.2f} | Target: ₹{target:,.2f}[/bold green]\n")

    start_dt = datetime.now().replace(hour=14, minute=45, second=0)

    for step in range(1, ticks + 1):
        step_time = (start_dt + timedelta(minutes=step)).strftime("%H:%M:%S")

        # Power Hour high volatility simulation (Gamma squeeze + institutional squaring off)
        # Random walk with bullish momentum surge
        fluctuation = float(np.random.normal(1.8, 3.8))
        price = round(price + fluctuation, 2)

        # Update peak price & Trailing Stop Loss
        if price > peak_price:
            peak_price = price
            # Lock in profit: Trail SL up when in profit > +15 points
            if (price - entry_price) > 15.0:
                new_trail = round(price - 12.0, 2)
                if new_trail > trailing_sl:
                    trailing_sl = new_trail

        diff = price - entry_price
        pnl = round(diff * qty, 2)
        if pnl > peak_pnl:
            peak_pnl = pnl

        pnl_pct = (diff / entry_price) * 100
        pnl_style = "bold green neon-glow-green" if pnl >= 0 else "bold red"
        
        console.print(
            f"[{step_time}] Tick #{step:02d} | LTP: [bold]₹{price:,.2f}[/bold] ({diff:+,.2f} pts) | "
            f"Active Trailing SL: ₹{trailing_sl:,.2f} | "
            f"Live P&L: [{pnl_style}]₹{pnl:+,.2f}[/{pnl_style}] ([cyan]{(pnl / 100000.0) * 100:+.2f}% on Cap[/cyan])"
        )

        # Check Target Hit (+60 pts)
        if price >= target:
            gross_pnl = pnl
            costs = calculate_transaction_costs("NSE:NIFTY 50", side, qty, entry_price, price)
            net_pnl = round(gross_pnl - costs["total_charges"], 2)

            journal.log_trade({
                "order_id": order_id,
                "symbol": "NSE:NIFTY 50",
                "side": side,
                "quantity": qty,
                "fill_price": price,
                "stop_loss": trailing_sl,
                "target": target,
                "action": "SQUARE_OFF",
                "gross_pnl": gross_pnl,
                "charges": costs["total_charges"],
                "pnl": net_pnl,
            }, mode="PAPER", reason="POWER HOUR TARGET HIT")
            console.print(f"\n[bold green]🎯🎯 MAXIMUM PROFIT TARGET SMASHED at ₹{price:,.2f}! Net Gain: +₹{net_pnl:,.2f} (Gross: +₹{gross_pnl:,.2f}, Charges: ₹{costs['total_charges']:.2f}) 🚀🚀[/bold green]")
            return {"status": "TARGET_HIT", "pnl": net_pnl, "gross_pnl": gross_pnl, "charges": costs["total_charges"], "peak_pnl": peak_pnl, "exit_price": price}

        # Check Trailing Stop Hit
        if price <= trailing_sl:
            gross_pnl = pnl
            costs = calculate_transaction_costs("NSE:NIFTY 50", side, qty, entry_price, price)
            net_pnl = round(gross_pnl - costs["total_charges"], 2)

            journal.log_trade({
                "order_id": order_id,
                "symbol": "NSE:NIFTY 50",
                "side": side,
                "quantity": qty,
                "fill_price": price,
                "stop_loss": trailing_sl,
                "target": target,
                "action": "SQUARE_OFF",
                "gross_pnl": gross_pnl,
                "charges": costs["total_charges"],
                "pnl": net_pnl,
            }, mode="PAPER", reason="TRAILING STOP-LOSS HIT")
            res_style = "bold green" if net_pnl >= 0 else "bold red"
            console.print(f"\n[{res_style}]🛑 TRAILING STOP HIT at ₹{price:,.2f}! Net Locked In P&L: ₹{net_pnl:+,.2f} (Gross: ₹{gross_pnl:+,.2f}, Charges: ₹{costs['total_charges']:.2f})[/{res_style}]")
            return {"status": "TRAILING_SL_HIT", "pnl": net_pnl, "gross_pnl": gross_pnl, "charges": costs["total_charges"], "peak_pnl": peak_pnl, "exit_price": price}

        time.sleep(0.4)

    # 3:15 PM EOD Mandatory Square-Off
    gross_pnl = pnl
    costs = calculate_transaction_costs("NSE:NIFTY 50", side, qty, entry_price, price)
    net_pnl = round(gross_pnl - costs["total_charges"], 2)

    journal.log_trade({
        "order_id": order_id,
        "symbol": "NSE:NIFTY 50",
        "side": side,
        "quantity": qty,
        "fill_price": price,
        "stop_loss": trailing_sl,
        "target": target,
        "action": "SQUARE_OFF",
        "gross_pnl": gross_pnl,
        "charges": costs["total_charges"],
        "pnl": net_pnl,
    }, mode="PAPER", reason="3:15 PM MANDATORY EOD SQUARE-OFF")

    res_style = "bold green" if net_pnl >= 0 else "bold red"
    console.print(f"\n[{res_style}]⏰ 3:15 PM MANDATORY SQUARE-OFF: Closed at ₹{price:,.2f} | Net Realized P&L: ₹{net_pnl:+,.2f} (Gross: ₹{gross_pnl:+,.2f}, Charges: ₹{costs['total_charges']:.2f})[/{res_style}]")
    return {"status": "EOD_SQUARE_OFF", "pnl": net_pnl, "gross_pnl": gross_pnl, "charges": costs["total_charges"], "peak_pnl": peak_pnl, "exit_price": price}
