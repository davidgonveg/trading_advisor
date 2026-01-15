import logging
from datetime import datetime, timezone
from data.storage.database import Database
from backtesting.data.feed import DatabaseFeed
from backtesting.simulation.engine import BacktestEngine
from backtesting.strategy.mean_reversion import MeanReversionStrategy
from backtesting.simulation.logger import TradeLogger

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
    symbols = ["SPY", "QQQ", "IWM", "XLF", "XLE", "XLK", "SMH"] # Tier 1 + Tier 2
    start_date = datetime(2020, 1, 1, tzinfo=timezone.utc) # 1 Year Verification
    end_date = datetime(2025, 12, 31, tzinfo=timezone.utc) # Up to now
    initial_capital = 10000.0
    
    print(f"--- STARTING BACKTEST Runner ---")
    print(f"Symbols: {symbols}")
    print(f"Period: {start_date} to {end_date}")
    print(f"Capital: ${initial_capital}")
    
    # 2. Initialize Components
    db = Database()
    feed = DatabaseFeed(db, symbols, start_date, end_date)
    
    engine = BacktestEngine(feed, initial_capital)
    strategy = MeanReversionStrategy(symbols)
    
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
    
    # Save Detailed Signals
    strategy.signal_logger.save_signals()
    
    # 5. Summary
    print("\n--- SUMMARY ---")
    print(f"Final Equity: ${engine.broker.equity:.2f}")
    print(f"Total Trades: {len(engine.broker.trades)}")
    
    # Simple Win Rate Calc
    # NOTE: Broker.trades is a list of fills (entries and exits mixed).
    # To calculate Win Rate we need to pair them (Round Trips).
    # For now, just dumping the raw ledger is step 1.
    
    if engine.broker.trades:
        last_trade = engine.broker.trades[-1]
        print(f"Last Trade: {last_trade.timestamp} {last_trade.symbol} {last_trade.side.value}")

if __name__ == "__main__":
    main()
