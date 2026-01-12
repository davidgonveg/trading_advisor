import pytest
import pandas as pd
import numpy as np
import sqlite3
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 💉 CRITICAL: Mock external dependencies that might be missing BEFORE importing modules
# This prevents ImportError when the environment lacks these packages
if 'yfinance' not in sys.modules:
    sys.modules['yfinance'] = MagicMock()
if 'talib' not in sys.modules:
    sys.modules['talib'] = MagicMock()
if 'telegram' not in sys.modules:
    import types
    telegram_mock = types.ModuleType('telegram')
    sys.modules['telegram'] = telegram_mock
    
    # Create telegram.error module with REAL exception classes
    telegram_error_mock = types.ModuleType('telegram.error')
    sys.modules['telegram.error'] = telegram_error_mock
    telegram_mock.error = telegram_error_mock
    telegram_mock.Bot = MagicMock
    
    class MockTelegramError(Exception): pass
    class MockNetworkError(MockTelegramError): pass
    class MockTimedOut(MockNetworkError): pass
    class MockRetryAfter(MockTelegramError):
        def __init__(self, retry_after):
            self.retry_after = retry_after
            super().__init__(f"Retry after {retry_after}")

    telegram_error_mock.TelegramError = MockTelegramError
    telegram_error_mock.NetworkError = MockNetworkError
    telegram_error_mock.TimedOut = MockTimedOut
    telegram_error_mock.RetryAfter = MockRetryAfter

if 'telegram.ext' not in sys.modules:
    sys.modules['telegram.ext'] = MagicMock()
if 'telegram.request' not in sys.modules:
    sys.modules['telegram.request'] = MagicMock()
if 'telegram.constants' not in sys.modules:
    sys.modules['telegram.constants'] = MagicMock()

import config

@pytest.fixture
def mock_config(monkeypatch):
    """Override config values for testing"""
    monkeypatch.setattr(config, 'TEST_MODE', True)
    monkeypatch.setattr(config, 'DEVELOPMENT_MODE', True)
    monkeypatch.setattr(config, 'LOG_LEVEL', 'DEBUG')
    monkeypatch.setattr(config, 'TELEGRAM_TOKEN', 'TEST_TOKEN')
    monkeypatch.setattr(config, 'CHAT_ID', '123456')
    monkeypatch.setattr(config, 'SYMBOLS', ['AAPL', 'MSFT'])
    return config

@pytest.fixture
def mock_db():
    """Create an in-memory SQLite database"""
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    
    # Create necessary tables (schema mimicry)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            signal_type TEXT,
            score REAL,
            price REAL,
            stop_loss REAL,
            take_profit_1 REAL,
            take_profit_2 REAL,
            take_profit_3 REAL,
            status TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            entry_price REAL,
            quantity INTEGER,
            side TEXT,
            status TEXT,
            entry_time TEXT,
            exit_time TEXT,
            pnl REAL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gap_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            gap_type TEXT,
            gap_size_pct REAL,
            filled BOOLEAN
        )
    ''')
    
    conn.commit()
    yield conn
    conn.close()

@pytest.fixture
def sample_market_data():
    """Generate generic OHLCV data for testing"""
    dates = pd.date_range(end=datetime.now(), periods=100, freq='15min')
    df = pd.DataFrame(index=dates)
    
    # Create a simple trend + noise
    base_price = 150.0
    trend = np.linspace(0, 10, 100)
    noise = np.random.normal(0, 0.5, 100)
    
    df['Open'] = base_price + trend + noise
    df['High'] = df['Open'] + 1.0
    df['Low'] = df['Open'] - 1.0
    df['Close'] = df['Open'] + 0.2
    df['Volume'] = np.random.randint(1000, 5000, 100)
    
    return df

@pytest.fixture
def mock_yfinance(sample_market_data):
    """Mock yfinance download and Ticker"""
    with patch('yfinance.download') as mock_download, \
         patch('yfinance.Ticker') as mock_ticker:
        
        # Configure download return
        mock_download.return_value = sample_market_data
        
        # Configure Ticker return
        ticker_instance = MagicMock()
        ticker_instance.history.return_value = sample_market_data
        mock_ticker.return_value = ticker_instance
        
        yield mock_download

@pytest.fixture
def mock_telegram():
    """Mock Telegram bot"""
    with patch('services.telegram_bot.TelegramBot') as mock_bot_cls:
        mock_instance = mock_bot_cls.return_value
        mock_instance.send_message.return_value = True
        yield mock_instance
