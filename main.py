import argparse
import time
import logging
import sys
from datetime import datetime, timedelta
from datetime import datetime, timedelta, timezone # Added timezone
from pathlib import Path
import pandas as pd # Added pandas for Timestamp

# Setup Path to include root
sys.path.append(str(Path(__file__).parent))

# Fix Windows Unicode Encode Error for Emojis
try:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from config.settings import SYSTEM_CONFIG, SYMBOLS
from data.storage.database import Database
from data.manager import DataManager
from analysis.scanner import Scanner
from analysis.indicators import TechnicalIndicators
from trading.manager import TradeManager
from alerts.telegram import TelegramBot
from backtesting.data.feed import DatabaseFeed 
from backtesting.strategy.vwap_bounce import VWAPBounceStrategy # v3.1 fix

# Setup Logging
logging.basicConfig(
    level=getattr(logging, SYSTEM_CONFIG["LOG_LEVEL"]),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/trading_advisor.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("main")

def run_gap_check(data_manager: DataManager):
    """
    Checks and fills gaps for all symbols at startup.
    """
    logger.info("--- STARTING GAP CHECK ---")
    for symbol in SYMBOLS:
        try:
            data_manager.resolve_gaps(symbol)
        except Exception as e:
            logger.error(f"Gap check failed for {symbol}: {e}")
    logger.info("--- GAP CHECK COMPLETE ---")

def run_live_loop():
    """
    Main Live Trading Loop.
    """
    logger.info("STARTING LIVE TRADING ADVISOR")
    
    # Initialize Components
    db = Database()
    data_mgr = DataManager()
    scanner = Scanner()
    indicators = TechnicalIndicators()
    trade_mgr = TradeManager()
    telegram = TelegramBot()
    
    # 1. Startup Tasks
    telegram.send_message("🚀 Trading Advisor STARTED. Monitoring market...")
    run_gap_check(data_mgr)
    
    # 2. Main Loop
    while True:
        cycle_start = datetime.now()
        logger.info(f"--- SCAN CYCLE START: {cycle_start} ---")
        
        for symbol in SYMBOLS:
            try:
                # A. Update Data (Hourly and Daily)
                data_mgr.update_data(symbol)
                data_mgr.update_daily_data(symbol)
                
                # B. Get Data
                df_raw = data_mgr.get_latest_data(symbol)
                df_daily = data_mgr.get_latest_daily_data(symbol)
                
                if df_raw.empty:
                    logger.warning(f"Skipping {symbol}: No data.")
                    continue
                    
                # C. Indicators
                df_analyzed = indicators.calculate_all(df_raw)
                
                # D. Save Indicators (Optimize: Only save last 48 hours)
                # We calculate on full history for accuracy, but only persist recent changes.
                rows_to_save = df_analyzed.iloc[-48:] 
                db.save_indicators(symbol, "1h", rows_to_save)
                
                # E. Scan
                # We want to scan the last CLOSED candle to ensure consistency with backtesting.
                # In 1h timeframe, a candle starting at 11:00 is 'closed' at 12:00.
                # We filter df_analyzed to only include rows where timestamp + 1h is in the past.
                now_utc = datetime.now(timezone.utc)
                df_confirmed = df_analyzed[df_analyzed.index + pd.Timedelta(hours=1) <= now_utc]
                
                if df_confirmed.empty:
                    logger.debug(f"No fully closed candles for {symbol} yet.")
                    continue
                    
                # Scan only the latest fully formed candle
                signals = scanner.find_signals(symbol, df_confirmed, df_daily=df_daily, scan_latest=True)
                
                if signals:
                    logger.info(f"SIGNALS FOUND FOR {symbol}: {len(signals)}")
                    for sig in signals:
                        # Generate Plan
                        # Using configurable capital size for risk management
                        cap_size = SYSTEM_CONFIG.get("INITIAL_CAPITAL", 10000)
                        plan = trade_mgr.create_trade_plan(sig, size=cap_size) 
                        
                        if plan:
                            logger.info(f"ALERT: {plan}")
                            # Save to DB
                            db.save_alert(sig, plan)
                            # Send Telegram
                            telegram.send_signal_alert(sig, plan)
                            
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        logger.info("--- CYCLE COMPLETE ---")
        
        # Smart Sleep: Wait until next hour mark + 10 seconds buffer
        now = datetime.now()
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        sleep_seconds = (next_hour - now).total_seconds() + 10
        
        # Safety check for negative sleep (if cycle took > 1 hour)
        if sleep_seconds <= 0:
            sleep_seconds = 60 # Default short sleep
            
        logger.info(f"Sleeping {sleep_seconds:.0f} seconds until {next_hour}...")
        time.sleep(sleep_seconds)

def run_scan():
    """
    Runs a single scan pass.
    """
    logger.info("Running Single Scan...")
    data_mgr = DataManager()
    scanner = Scanner()
    indicators = TechnicalIndicators()
    
    for symbol in SYMBOLS:
        print(f"Scanning {symbol}...")
        try:
            data_mgr.update_data(symbol)
            df = data_mgr.get_latest_data(symbol)
            df = indicators.calculate_all(df)
            signals = scanner.find_signals(symbol, df)
            
            if signals:
                for s in signals:
                    print(f"  FOUND: {s}")
            else:
                print("  No signals.")
        except Exception as e:
            logger.error(f"Scan error {symbol}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Trading Advisor Main CLI")
    parser.add_argument('mode', choices=['live', 'scan', 'backtest'], help="Operating Mode")
    parser.add_argument('--symbol', help="Specific symbol to run (optional)")
    parser.add_argument('--days', type=int, default=365, help="Days of history to load (default: 365)")
    parser.add_argument('--start-date', help="Start Date (YYYY-MM-DD) for backtest")
    parser.add_argument('--end-date', help="End Date (YYYY-MM-DD) for backtest")
    
    args = parser.parse_args()
    
    if args.mode == 'live':
        run_live_loop()
    elif args.mode == 'scan':
        run_scan()
    elif args.mode == 'backtest':
        logger.info(f"--- STARTING BACKTEST MODE ---")
        from backtesting.simulation.engine import BacktestEngine
        
        # 1. Setup Data Feed
        db = Database()
        target_symbols = [args.symbol] if args.symbol else SYMBOLS
        
        if args.start_date:
            start_date = pd.Timestamp(args.start_date, tz='UTC')
            if args.end_date:
                end_date = pd.Timestamp(args.end_date, tz='UTC')
            else:
                end_date = pd.Timestamp.now(tz='UTC')
            logger.info(f"Using explicit date range: {start_date} to {end_date}")
        else:
            start_date = pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=args.days)
            end_date = pd.Timestamp.now(tz='UTC')
            logger.info(f"Using relative date range (Days={args.days}): {start_date} to {end_date}")
        
        print(f"Initializing Data Feed for {target_symbols}...")
        feed = DatabaseFeed(db, target_symbols, start_date, end_date)
        
        # 2. Init Engine
        engine = BacktestEngine(feed, initial_capital=10000.0)
        
        # 3. Setup Strategy
        curr_strategy = VWAPBounceStrategy(target_symbols)
        engine.set_strategy(curr_strategy)
        
        # 4. Run
        engine.run()
        
        # 5. Save Results
        from backtesting.simulation.logger import TradeLogger
        from backtesting.simulation.analytics import BacktestAnalyzer
        
        trade_logger = TradeLogger()
        trade_logger.save_trades(engine.broker.trades)
        
        if hasattr(curr_strategy, 'completed_trades'):
            trade_logger.save_round_trips(curr_strategy.completed_trades)
            # Deep Analysis
            analyzer = BacktestAnalyzer(curr_strategy.completed_trades)
            analyzer.print_report()
            
        logger.info("Saved backtest results to backtesting/results/")


if __name__ == "__main__":
    main()
