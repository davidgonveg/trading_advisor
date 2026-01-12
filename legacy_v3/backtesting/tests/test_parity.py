
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import pytz
import logging
import pandas as pd
import numpy as np

# Setup
project_root = Path("c:/Users/gonza/Documents/trading advisor")
sys.path.insert(0, str(project_root))

from backtesting.mocks import BacktestDataManager
from utils.time_provider import BacktestTimeProvider
from analysis.scanner import SignalScanner
from execution.exit_manager import ExitManager
from backtesting.trade_manager import TradeManager
from backtesting.backtest_engine import BacktestEngine
from backtesting.config import BacktestConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_backtest_components():
    logger.info("🧪 Starting Backtest Smoke Test...")
    
    # 1. Create Mock Data (Sine Wave for predictability)
    dates = pd.date_range(start="2023-01-04", periods=100, freq="1h", tz="US/Eastern")
    data = pd.DataFrame({
        'open_price': 100 + 10 * np.sin(np.linspace(0, 3*np.pi, 100)),
        'close_price': 100 + 10 * np.sin(np.linspace(0.1, 3*np.pi + 0.1, 100)),
        'high_price': 111.0,
        'low_price': 89.0,
        'volume': 10000
    }, index=dates)
    data['high_price'] = data[['open_price', 'close_price']].max(axis=1) + 1
    data['low_price'] = data[['open_price', 'close_price']].min(axis=1) - 1
    
    # Add indicators columns expected by TechnicalIndicators (validation might fail otherwise)
    # Actually, SignalScanner calls calculate_all_indicators which works on raw data.
    # But filtering logic inside Scanner/Indicators expects basic OHLCV.
    
    historical_data = {'TEST': data}
    
    # 2. Config
    config = BacktestConfig()
    config.symbols = ['TEST']
    config.initial_capital = 10000.0
    config.start_date = dates[0]
    config.end_date = dates[-1]
    
    # 3. Initialize Engine
    engine = BacktestEngine(config)
    
    # Inject Mock Data manually (since _prepare_data tries SQL)
    engine.historical_data = historical_data
    engine._initialize_components()
    
    logger.info("✅ Components initialized")
    
    # 4. Run Steps Manually
    time_provider = engine.time_provider
    data_manager = engine.data_manager
    scanner = engine.scanner
    
    # Step 1: Early in the sine wave (price rising)
    idx = 10
    current_time = dates[idx]
    time_provider.set_time(current_time)
    
    logger.info(f"🕐 Step 1: {current_time}")
    
    # Validate Data Manager View
    view = data_manager.get_data('TEST', '1h', days=30)
    assert len(view) == idx + 1, f"Expected {idx+1} bars, got {len(view)}"
    assert view.index[-1] == current_time
    logger.info("✅ DataManager slicing correct")
    
    # Scan
    signals = scanner.scan_multiple_symbols(['TEST'])
    logger.info(f"🔎 Signals found: {len(signals)}")
    
    if signals:
        logger.info(f"Signal: {signals[0].signal_type} Strength: {signals[0].signal_strength}")
        engine._process_new_signal(signals[0])
        logger.info(f"Active Trades: {len(engine.trade_manager.active_trades)}")
        
    # Step 2: Later
    idx = 20
    current_time = dates[idx]
    time_provider.set_time(current_time)
    engine._process_exit_manager()
    
    logger.info("✅ Smoke Test Complete")

if __name__ == "__main__":
    try:
        test_backtest_components()
        print("✅ TEST PASSED")
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
