"""
Configuration settings for Trading Online.
Loads environment variables from .env with fallback defaults.
"""
from pathlib import Path
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import os

# Load .env file from project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class Settings(BaseModel):
    # Mode
    paper_trading: bool = Field(default_factory=lambda: os.getenv("PAPER_TRADING", "True").lower() in ("true", "1", "yes"))
    paper_initial_capital: float = Field(default_factory=lambda: float(os.getenv("PAPER_INITIAL_CAPITAL", "100000.0")))

    # Kite Connect API Credentials
    kite_api_key: str = Field(default_factory=lambda: os.getenv("KITE_API_KEY", ""))
    kite_api_secret: str = Field(default_factory=lambda: os.getenv("KITE_API_SECRET", ""))
    kite_user_id: str = Field(default_factory=lambda: os.getenv("KITE_USER_ID", ""))
    kite_access_token: str = Field(default_factory=lambda: os.getenv("KITE_ACCESS_TOKEN", ""))

    # Risk Management Settings
    max_daily_loss: float = Field(default_factory=lambda: float(os.getenv("MAX_DAILY_LOSS", "1000.0")))
    max_lots: int = Field(default_factory=lambda: int(os.getenv("MAX_LOTS", "1")))
    stop_loss_pct: float = Field(default_factory=lambda: float(os.getenv("STOP_LOSS_PCT", "0.01")))
    target_rr_ratio: float = Field(default_factory=lambda: float(os.getenv("TARGET_RR_RATIO", "2.0")))
    mandatory_square_off_time: str = Field(default_factory=lambda: os.getenv("MANDATORY_SQUARE_OFF_TIME", "15:15"))

    # Midday Chop Protection (11:30 AM - 1:30 PM IST)
    enable_midday_filter: bool = Field(default_factory=lambda: os.getenv("ENABLE_MIDDAY_FILTER", "True").lower() in ("true", "1", "yes"))
    midday_start: str = Field(default_factory=lambda: os.getenv("MIDDAY_START", "11:30"))
    midday_end: str = Field(default_factory=lambda: os.getenv("MIDDAY_END", "13:30"))

    # Strategy & Regime Settings
    adx_threshold: float = Field(default_factory=lambda: float(os.getenv("ADX_THRESHOLD", "22.0")))
    chop_threshold: float = Field(default_factory=lambda: float(os.getenv("CHOP_THRESHOLD", "61.8")))

    # Instrument defaults
    default_symbol: str = Field(default_factory=lambda: os.getenv("DEFAULT_SYMBOL", "NSE:NIFTY 50"))
    timeframe: str = Field(default_factory=lambda: os.getenv("TIMEFRAME", "5minute"))


settings = Settings()
