import logging
from datetime import datetime, timezone
import sys
import os
sys.path.insert(0, os.getcwd())

from data.storage.database import Database
from backtesting.data.feed import DatabaseFeed
from backtesting.simulation.engine import BacktestEngine
from backtesting.simulation.engine import BacktestEngine
from backtesting.strategy.vwap_bounce import VWAPBounceStrategy
from backtesting.simulation.logger import TradeLogger
from backtesting.simulation.analytics import BacktestAnalyzer
from config.settings import SYMBOLS

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("backtesting/backtest.log"),
        logging.StreamHandler()
    ]
)

def main():
    # 1. Configuration
    symbols = SYMBOLS
    start_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
    end_date = datetime(2024, 12, 31, tzinfo=timezone.utc)
    initial_capital = 10000.0
    
    print(f"--- STARTING BACKTEST Runner ---")
    print(f"Symbols: {symbols}")
    print(f"Period: {start_date} to {end_date}")
    print(f"Capital: ${initial_capital}")
    
    # 2. Initialize Components
    db = Database()
    feed = DatabaseFeed(db, symbols, start_date, end_date)
    
    engine = BacktestEngine(feed, initial_capital)
    
    strategy = VWAPBounceStrategy(symbols)
    engine.set_strategy(strategy)
    
    # 3. Run
    try:
        engine.run()
    except KeyboardInterrupt:
        print("Backtest interrupted by user.")
    except Exception as e:
        logging.exception("Fatal error during backtest run")
        print(f"Error: {e}")
        
    # 4. Save Results
    logger = TradeLogger()
    logger.save_trades(engine.broker.trades)
    
    # Save Detailed Round Trips (NEW)
    if hasattr(strategy, 'completed_trades'):
        logger.save_round_trips(strategy.completed_trades)
        
        # 4.5. Deep Analysis
        analyzer = BacktestAnalyzer(strategy.completed_trades)
        analyzer.print_report()
    
    # Save Equity Curve (NEW)
    logger.save_equity_curve(engine.equity_curve)
    
    # Save Detailed Signals
    # strategy.signal_logger.save_signals() # VWAP Strategy doesn't have signal logger instantiated yet?
    
    # 5. Summary
    print("\n--- SUMMARY ---")
    print(f"Final Equity: ${engine.broker.equity:.2f}")
    
    print(f"Total Fills: {len(engine.broker.trades)}")
    
    if engine.broker.trades:
        last_trade = engine.broker.trades[-1]
        print(f"Last Trade: {last_trade.timestamp} {last_trade.symbol} {last_trade.side.value}")

if __name__ == "__main__":
    main()
