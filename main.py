import argparse
import time
import logging
import sys
from datetime import datetime
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
                # A. Update Data
                data_mgr.update_data(symbol)
                
                # B. Get Data
                df_raw = data_mgr.get_latest_data(symbol)
                if df_raw.empty:
                    logger.warning(f"Skipping {symbol}: No data.")
                    continue
                    
                # C. Indicators
                df_analyzed = indicators.calculate_all(df_raw)
                
                # D. Save Indicators (Optional, good for debugging)
                db.save_indicators(symbol, "1h", df_analyzed)
                
                # E. Scan
                # Only scan the LATEST candle in live mode to avoid spamming historical signals
                signals = scanner.find_signals(symbol, df_analyzed, scan_latest=True)
                
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
        
        # Determine sleep time (Next Hour Mark)
        # Sleep 60 seconds for now to verify loop, or calculate next hour.
        # For production: Sleep until next XX:05 or similar.
        # We will sleep 10m for simplicity or use logic.
        
        logger.info("Sleeping... (Press Ctrl+C to stop)")
        time.sleep(60 * 60) # 1 Hour

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
        print("Backtest mode not fully linked yet in main.py. Use legacy or wait for update.")
        # from backtesting.engine import BacktestEngine
        # engine = BacktestEngine()
        # engine.run()

if __name__ == "__main__":
    main()
