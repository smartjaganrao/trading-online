"""
AI Expert Market Sentinel & Chief Risk Officer Overseer.
Continuously monitors the market, active positions, regime shifts, and risk invariants.
Provides actionable institutional expert commentary, early-warning alerts, and capital safety recommendations.
"""
from datetime import datetime, time
import time as pytime
from typing import Dict, Any, List
import pandas as pd
import numpy as np
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config.settings import settings
from core.risk_manager import RiskManager
from core.client import PaperTradingClient, KiteLiveClient
from core.auth import KiteAuthManager
from strategies.supertrend_ema import SuperTrendEMAStrategy

console = Console()


class MarketSentinelExpert:
    """
    Acts as an institutional Chief Risk Officer (CRO) and Lead Quant Trader.
    Monitors market anomalies, trailing risk, session phases, and issues real-time advisories.
    """
    def __init__(self, client=None, risk_manager=None):
        self.risk_manager = risk_manager or RiskManager()
        if client:
            self.client = client
        elif settings.paper_trading:
            self.client = PaperTradingClient(risk_manager=self.risk_manager)
        else:
            auth_mgr = KiteAuthManager()
            self.client = KiteLiveClient(auth_mgr.get_kite_client(), self.risk_manager)

        self.strategy = SuperTrendEMAStrategy()
        self.alerts_history: List[str] = []

    def get_market_session_phase(self) -> Dict[str, Any]:
        """Determines the current institutional market regime based on time."""
        now = datetime.now().time()
        
        if now < time(9, 0):
            return {"phase": "PRE_MARKET_DORMANT", "desc": "Market Closed. Global cues & SGX/Gift Nifty discovery.", "action": "WAIT"}
        elif time(9, 0) <= now < time(9, 15):
            return {"phase": "PRE_OPEN_AUCTION", "desc": "Pre-open price discovery. High opening gap volatility.", "action": "OBSERVE_ONLY"}
        elif time(9, 15) <= now < time(10, 15):
            return {"phase": "OPENING_MOMENTUM", "desc": "Initial balance & price discovery. Wide spreads.", "action": "TREND_FOLLOWING"}
        elif time(10, 15) <= now < time(13, 30):
            return {"phase": "MIDDAY_CONSOLIDATION", "desc": "Institutional lull & mean-reversion. High false breakout risk.", "action": "TIGHTEN_FILTERS"}
        elif time(13, 30) <= now < time(14, 45):
            return {"phase": "EUROPEAN_EXPANSION", "desc": "European markets open. Directional liquidity injections.", "action": "MOMENTUM_CONFIRMATION"}
        elif time(14, 45) <= now < time(15, 15):
            return {"phase": "POWER_HOUR_GAMMA", "desc": "High gamma expansion & intraday institutional squaring-off.", "action": "TRAIL_PROFIT_TIGHTLY"}
        elif time(15, 15) <= now < time(15, 30):
            return {"phase": "MANDATORY_SQUARE_OFF", "desc": "Intraday cutoff active. Square off all MIS positions.", "action": "FORCE_EXIT"}
        else:
            return {"phase": "POST_MARKET_SETTLEMENT", "desc": "Exchange closed. Run EOD machine learning & review.", "action": "POST_MARKET_LEARN"}

    def evaluate_expert_diagnostics(self, current_ltp: float, last_signal: dict, df_history: pd.DataFrame) -> List[str]:
        """Performs deep quant diagnostics and generates institutional expert alerts."""
        alerts = []
        phase_info = self.get_market_session_phase()
        metrics = last_signal.get("metrics", {})
        rsi = metrics.get("rsi", 50.0)
        positions = self.client.get_positions()
        margins = self.client.get_margins()

        # 1. Market Phase Alert
        alerts.append(f"[bold cyan]Market Regime:[/bold cyan] {phase_info['phase']} — {phase_info['desc']}")

        # 2. RSI Extreme Conditions
        if rsi > 75.0:
            alerts.append("[bold red]⚠️ OVERBOUGHT EXTREME:[/bold red] RSI is 75+. Buying exhaustion imminent. Avoid chasing long breakouts.")
        elif rsi < 25.0:
            alerts.append("[bold green]⚠️ OVERSOLD EXTREME:[/bold green] RSI is below 25. Panic selling climax. Watch for sharp short-covering bounce.")

        # 3. Position Risk Monitoring
        for p in positions:
            entry_p = p["entry_price"]
            side = p["side"]
            sl = p.get("stop_loss", 0.0)
            target = p.get("target", 0.0)
            pnl = p.get("unrealized_pnl", 0.0)

            # Distance to stop-loss
            sl_dist = abs(current_ltp - sl)
            if sl_dist <= 8.0:
                alerts.append(f"[bold red]🚨 CRITICAL SL WARNING:[/bold red] {p['symbol']} is only {sl_dist:.1f} pts from Stop-Loss (₹{sl:.2f})!")

            # Target proximity
            tgt_dist = abs(target - current_ltp)
            if tgt_dist <= 10.0:
                alerts.append(f"[bold green]🎯 TARGET PROXIMITY:[/bold green] {p['symbol']} is within {tgt_dist:.1f} pts of Profit Target (₹{target:.2f}). Consider trailing stop.")

            if pnl > 3000.0:
                alerts.append(f"[bold green]💰 STRONG UNREALIZED GAIN:[/bold green] Position is up ₹{pnl:+,.2f}. Trailing ratchet engaged to protect profits.")

        # 4. Circuit Breaker Proximity
        loss_headroom = self.risk_manager.max_daily_loss + margins.get("realized_pnl", 0.0)
        if loss_headroom <= 300.0:
            alerts.append(f"[bold red]🛑 CIRCUIT BREAKER ALERT:[/bold red] Only ₹{loss_headroom:.2f} risk buffer remains before mandatory system shutdown!")

        return alerts

    def render_sentinel_panel(self, current_ltp: float, last_signal: dict, df_history: pd.DataFrame) -> Panel:
        phase = self.get_market_session_phase()
        alerts = self.evaluate_expert_diagnostics(current_ltp, last_signal, df_history)
        margins = self.client.get_margins()
        positions = self.client.get_positions()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Top Diagnostic Grid
        grid = Table.grid(expand=True)
        grid.add_column()
        
        # Summary Header
        header = (
            f"[bold cyan]⏰ Sentinel Clock:[/bold cyan] {now_str}  |  "
            f"[bold yellow]Mode:[/bold yellow] {'PAPER (Simulated)' if settings.paper_trading else 'LIVE ZERODHA'}  |  "
            f"[bold magenta]Phase:[/bold magenta] {phase['phase']}\n"
            f"[bold]Capital:[/bold] ₹{margins.get('available_cash', 0.0):,.2f}  |  "
            f"[bold]Unrealized P&L:[/bold] ₹{margins.get('unrealized_pnl', 0.0):+,.2f}  |  "
            f"[bold]Circuit Breaker Risk:[/bold] -₹{self.risk_manager.max_daily_loss:,.2f}"
        )
        grid.add_row(header)
        grid.add_row("\n[bold underline]🧠 AI Chief Risk Officer Live Advisories:[/bold underline]")
        
        for a in alerts:
            grid.add_row(f"  • {a}")

        # Position breakdown if any
        if positions:
            grid.add_row("\n[bold underline]📊 Live Asset Under Surveillance:[/bold underline]")
            for p in positions:
                grid.add_row(
                    f"  └─ {p['symbol']} | {p['side']} {p['quantity']} Qty @ ₹{p['entry_price']:,.2f} | "
                    f"Current: ₹{current_ltp:,.2f} | SL: ₹{p['stop_loss']:,.2f} | Target: ₹{p['target']:,.2f} | "
                    f"P&L: ₹{p.get('unrealized_pnl', 0.0):+,.2f}"
                )
        else:
            grid.add_row("\n[dim]No open market inventory. Sentinel scanning for next A+ confluence setup...[/dim]")

        return Panel(
            grid,
            title=f"🛡️ AI EXPERT MARKET SENTINEL & CRO OVERSEER 🛡️",
            subtitle=f"Recommended Action: {phase['action']}",
            border_style="bright_blue"
        )


def run_expert_monitor_loop(ticks: int = 15, delay: float = 1.0):
    console.print("[bold cyan]Activating AI Expert Market Monitor...[/bold cyan]")
    sentinel = MarketSentinelExpert()
    
    # Load history
    from main import generate_mock_candle_history
    df_candles = generate_mock_candle_history(settings.default_symbol, count=40)

    try:
        for i in range(ticks):
            ltp_map = sentinel.client.get_ltp([settings.default_symbol])
            current_ltp = ltp_map.get(settings.default_symbol, 24395.0)

            # Update candle
            new_row = pd.DataFrame([{
                "timestamp": pd.Timestamp.now(),
                "open": round(df_candles["close"].iloc[-1], 2),
                "high": round(max(df_candles["close"].iloc[-1], current_ltp) + 1.5, 2),
                "low": round(min(df_candles["close"].iloc[-1], current_ltp) - 1.5, 2),
                "close": current_ltp,
                "volume": int(np.random.uniform(50000, 150000)),
            }])
            df_candles = pd.concat([df_candles.iloc[1:], new_row], ignore_index=True)

            signal = sentinel.strategy.generate_signal(df_candles)
            panel = sentinel.render_sentinel_panel(current_ltp, signal, df_candles)

            console.clear()
            console.print(panel)
            pytime.sleep(delay)

    except KeyboardInterrupt:
        console.print("\n[yellow]Sentinel monitor paused.[/yellow]")
