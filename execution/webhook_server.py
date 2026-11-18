"""
TradingView Webhook Execution Server.
Listens for HTTP POST alert webhooks from TradingView and dispatches orders
to PaperTradingClient or Live Kite/Crypto broker with institutional risk verification.
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
from datetime import datetime
from rich.console import Console
from rich.panel import Panel

from config.settings import settings
from core.risk_manager import RiskManager
from core.client import PaperTradingClient, KiteLiveClient
from core.auth import KiteAuthManager
from core.commodity import CommodityEngine
from core.forex import ForexEngine
from execution.journal import TradeJournal

console = Console()


class TradingViewWebhookHandler(BaseHTTPRequestHandler):
    client = None
    risk_manager = None
    journal = None
    webhook_secret = os.getenv("WEBHOOK_SECRET", "tradingonline_secret")

    def _set_headers(self, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_GET(self):
        """Health check endpoint."""
        margins = self.client.get_margins() if self.client else {}
        resp = {
            "status": "online",
            "service": "Trading Online Webhook Gateway",
            "timestamp": datetime.now().isoformat(),
            "mode": "PAPER TRADING" if settings.paper_trading else "LIVE EXECUTION",
            "available_cash": margins.get("available_cash", 0.0),
            "realized_pnl": margins.get("realized_pnl", 0.0),
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(resp, indent=2).encode("utf-8"))

    def do_POST(self):
        """Processes incoming TradingView Webhook alert payloads."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Empty payload"}).encode("utf-8"))
            return

        post_data = self.rfile.read(content_length).decode("utf-8")
        try:
            payload = json.loads(post_data)
        except Exception:
            # Fallback for plain text or string formatted payloads
            try:
                payload = {"action": post_data.strip().upper(), "symbol": settings.default_symbol}
            except Exception as e:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": f"Invalid JSON payload: {e}"}).encode("utf-8"))
                return

        # 1. Authenticate Secret
        req_secret = payload.get("secret", "")
        if self.webhook_secret and req_secret != self.webhook_secret:
            console.print(f"[bold red]❌ UNAUTHORIZED WEBHOOK:[/bold red] Secret mismatch from {self.client_address[0]}")
            self._set_headers(401)
            self.wfile.write(json.dumps({"error": "Unauthorized: Invalid secret"}).encode("utf-8"))
            return

        # 2. Extract Alert Parameters
        action = str(payload.get("action", "")).upper()
        raw_symbol = payload.get("symbol", settings.default_symbol)
        price = float(payload.get("price", 0.0))
        quantity = payload.get("quantity")
        comment = payload.get("comment", "TradingView Alert")

        # Symbol normalization
        if CommodityEngine.is_commodity(raw_symbol):
            symbol = CommodityEngine.normalize_symbol(raw_symbol)
        elif ForexEngine.is_forex(raw_symbol):
            symbol = ForexEngine.normalize_forex_symbol(raw_symbol)
        else:
            symbol = raw_symbol

        # Quantity calculation if not provided
        if not quantity or int(quantity) <= 0:
            if CommodityEngine.is_commodity(symbol):
                quantity = CommodityEngine.get_lot_size(symbol)
            elif ForexEngine.is_forex(symbol):
                quantity = 1000
            elif "NIFTY" in symbol.upper():
                quantity = 75
            else:
                quantity = 1
        else:
            quantity = int(quantity)

        console.print(Panel(
            f"[bold cyan]📥 TRADINGVIEW WEBHOOK RECEIVED[/bold cyan]\n"
            f" • Action: [bold yellow]{action}[/bold yellow]\n"
            f" • Symbol: [bold]{symbol}[/bold]\n"
            f" • Quantity: {quantity}\n"
            f" • Price Reference: ₹{price:,.2f}\n"
            f" • Source Note: {comment}",
            title="TradingView Alert Dispatch",
            border_style="magenta"
        ))

        # 3. Handle Order Actions (BUY, SELL, EXIT, CLOSE)
        if action in ("BUY", "SELL"):
            order_res = self.client.place_order(
                symbol=symbol,
                transaction_type=action,
                quantity=quantity,
                order_type="MARKET",
                price=price
            )
            if order_res.get("status") == "FILLED":
                self.journal.log_trade(
                    order_res,
                    mode="PAPER" if settings.paper_trading else "LIVE",
                    reason=f"TradingView Alert: {comment}"
                )
                console.print(f"[bold green]🚀 ORDER EXECUTED:[/bold green] {action} {quantity} {symbol} @ ₹{order_res.get('fill_price', price):,.2f}")
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "SUCCESS", "execution": order_res}).encode("utf-8"))
            else:
                console.print(f"[bold red]⛔ ORDER REJECTED:[/bold red] {order_res.get('reason')}")
                self._set_headers(422)
                self.wfile.write(json.dumps({"status": "REJECTED", "reason": order_res.get("reason")}).encode("utf-8"))

        elif action in ("EXIT", "CLOSE", "FLAT"):
            positions = self.client.get_positions()
            target_pos = next((p for p in positions if p["symbol"] == symbol), None)
            if target_pos:
                exit_side = "SELL" if target_pos["side"] == "BUY" else "BUY"
                exit_res = self.client.place_order(symbol, exit_side, target_pos["quantity"])
                self.journal.log_trade(
                    exit_res,
                    mode="PAPER" if settings.paper_trading else "LIVE",
                    reason=f"TradingView Alert Square-Off: {comment}"
                )
                console.print(f"[bold yellow]⏹️ POSITION SQUARED OFF:[/bold yellow] {symbol} (P&L: ₹{exit_res.get('pnl', 0.0):+,.2f})")
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "SQUARED_OFF", "result": exit_res}).encode("utf-8"))
            else:
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "NO_POSITION_FOUND", "symbol": symbol}).encode("utf-8"))
        else:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": f"Unknown action: {action}"}).encode("utf-8"))


def start_webhook_server(port: int = 5000, secret: str = None):
    """Initializes and runs the webhook listener."""
    risk_mgr = RiskManager()
    if settings.paper_trading:
        client = PaperTradingClient(risk_manager=risk_mgr)
        mode_str = "[bold yellow]PAPER TRADING (Simulated)[/bold yellow]"
    else:
        auth_mgr = KiteAuthManager()
        client = KiteLiveClient(auth_mgr.get_kite_client(), risk_mgr)
        mode_str = "[bold green]LIVE ZERODHA KITE[/bold green]"

    journal = TradeJournal()
    webhook_secret = secret or os.getenv("WEBHOOK_SECRET", "tradingonline_secret")

    TradingViewWebhookHandler.client = client
    TradingViewWebhookHandler.risk_manager = risk_mgr
    TradingViewWebhookHandler.journal = journal
    TradingViewWebhookHandler.webhook_secret = webhook_secret

    server = HTTPServer(("0.0.0.0", port), TradingViewWebhookHandler)

    console.print(Panel(
        f"[bold green]⚡ TradingView Webhook Gateway Running on Port {port} ⚡[/bold green]\n\n"
        f" • [bold]Execution Engine:[/bold] {mode_str}\n"
        f" • [bold]Local Webhook URL:[/bold] http://localhost:{port}/webhook\n"
        f" • [bold]Health Status URL:[/bold] http://localhost:{port}/\n"
        f" • [bold]Webhook Secret:[/bold] [yellow]{webhook_secret}[/yellow]\n\n"
        f"[bold cyan]TradingView Alert Webhook Setup:[/bold cyan]\n"
        f" 1. Expose this port using ngrok / cloudflare: [bold]ngrok http {port}[/bold]\n"
        f" 2. Paste the public URL (e.g. https://xyz.ngrok-free.app/webhook) into TradingView Alert Webhook URL.\n"
        f" 3. Send JSON alert message containing action ('BUY' / 'SELL' / 'EXIT').",
        title="TradingView Integration Gateway",
        border_style="cyan"
    ))

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[bold red]Shutting down Webhook Gateway server...[/bold red]")
        server.server_close()
