import argparse
import time
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

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
                
                # D. Save Indicators (Optional, good for debugging)
                db.save_indicators(symbol, "1h", df_analyzed)
                
                # E. Scan
                # Only scan the LATEST candle in live mode to avoid spamming historical signals
                # Pass df_daily for Trend Filter
                signals = scanner.find_signals(symbol, df_analyzed, df_daily=df_daily, scan_latest=True)
                
                if signals:
                    logger.info(f"SIGNALS FOUND FOR {symbol}: {len(signals)}")
                    for sig in signals:
                        # Validate?
                        
                        # Generate Plan
                        plan = trade_mgr.create_trade_plan(sig, size=1000) # Dummy size for now, or calculate
                        
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
    
    args = parser.parse_args()
    
    if args.mode == 'live':
        run_live_loop()
    elif args.mode == 'scan':
        run_scan()
    elif args.mode == 'backtest':
        logger.info("--- STARTING BACKTEST MODE ---")
        from backtesting.engine import BacktestEngine
        
        # 1. Load Data
        data_mgr = DataManager()
        market_data = {}
        daily_data = {}
        
        print("Loading Historical Data...")
        for symbol in SYMBOLS:
            try:
                # Ensure we have data (Optional: could force update)
                # data_mgr.update_data(symbol) 
                
                df_hourly = data_mgr.get_latest_data(symbol, days=365) # 1 Year
                df_daily = data_mgr.get_latest_daily_data(symbol, days=365)
                
                if not df_hourly.empty:
                    market_data[symbol] = df_hourly
                    daily_data[symbol] = df_daily
                    print(f"Loaded {symbol}: {len(df_hourly)} hours, {len(df_daily)} days.")
                else:
                    print(f"Warning: No data for {symbol}")
            except Exception as e:
                logger.error(f"Error loading {symbol}: {e}")
                
        # 2. Init Engine
        engine = BacktestEngine(initial_capital=10000.0)
        engine.load_data(market_data)
        engine.load_daily_data(daily_data)
        
        # 3. Run
        report = engine.run()
        
        print("\n--- BACKTEST RESULTS ---")
        print(f"Final Equity: ${report['final_equity']:.2f}")
        print(f"Trades: {len(report['trades'])}")
        print("------------------------")

if __name__ == "__main__":
    main()
