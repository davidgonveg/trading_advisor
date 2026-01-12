"""
⚙️ GLOBAL SETTINGS
==================
Centralized configuration for the new architecture.
Migrated from legacy_v3/config.py
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"

# Ensure directories exist
LOG_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# API Keys
TWELVE_DATA_API_KEY = os.getenv('TWELVE_DATA_API_KEY')
ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY')
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')

# Telegram Credentials
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# System Configuration
SYSTEM_CONFIG = {
    "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
    "TIMEZONE": os.getenv("TIMEZONE", "US/Eastern"),
    "DEVELOPMENT_MODE": os.getenv("DEVELOPMENT_MODE", "False").lower() == "true",
}

# Trading Symbols (Tier 1 Core, Tier 2 Sector, Tier 3 Optional)
SYMBOLS = [
    # Tier 1: Core (Indices)
    "SPY", "QQQ", "IWM",
    # Tier 2: Sector
    "XLF", "XLE", "XLK", "SMH",
    # Tier 3: Diversification
    "GLD", "TLT", "EEM"
]

# Risk Management
RISK_CONFIG = {
    "RISK_PER_TRADE_PCT": 1.5,
    "MAX_OPEN_POSITIONS": 3,
}

# Data Collection Configuration
DATA_CONFIG = {
    "HISTORY_DAYS": 90, # Default for continuous loop
    "BACKFILL_DAYS": 730, # Max available commonly for hourly
}

# New Architecture Specifics
DATABASE_PATH = DATA_DIR / "storage" / "trading.db"

# Strategy Configuration (Mean Reversion Selectiva)
STRATEGY_CONFIG = {
    # Indicators
    "RSI_PERIOD": 14,
    "RSI_OVERSOLD": 35,
    "RSI_OVERBOUGHT": 65,
    "RSI_EXIT_LONG": 75,
    "RSI_EXIT_SHORT": 25,
    
    "BB_PERIOD": 20,
    "BB_DEV": 2.0,
    
    "ADX_PERIOD": 14,
    "ADX_MAX_THRESHOLD": 22, # Market must be ranging
    "ADX_CANCEL_THRESHOLD": 3, # If ADX rises > 3 pts, cancel pending orders
    
    "SMA_TREND_PERIOD": 50, # Daily timeframe
    "VOLUME_SMA_PERIOD": 20,
    
    # Time Rules
    "TIME_STOP_HOURS": 48,
    "MIN_MARKET_HOUR": 15, # 15:30 CET approx (handled via UTC/Timezone conversion)
    "MAX_MARKET_HOUR": 21, # 22:00 CET
    
    # Execution (ATR Multiples)
    "ENTRY_2_ATR_DIST": 0.5,
    "ENTRY_3_ATR_DIST": 1.0,
    
    "SL_ATR_MULT": 2.0,
    
    "TP1_ATR_MULT": 1.5,
    "TP2_ATR_MULT": 2.5,
    "TP3_ATR_MULT": 4.0,
    
    "TRAILING_ATR_DIST": 1.0, # Activates after TP2
}
