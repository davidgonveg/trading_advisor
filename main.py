import argparse
import time
import logging
from logging.handlers import RotatingFileHandler
import sys
import os
import requests
from datetime import datetime, timedelta, timezone
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
# from backtesting.data.feed import DatabaseFeed 
# from backtesting.strategy.vwap_bounce import VWAPBounceStrategy # v3.1 fix

# Setup Logging
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_file = os.getenv("LOG_FILE", "logs/trading_advisor.log")

# Rotating File Handler: 5MB per file, keep 5 backups
file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5)
file_handler.setFormatter(log_formatter)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)

logging.basicConfig(
    level=getattr(logging, SYSTEM_CONFIG["LOG_LEVEL"]),
    handlers=[file_handler, stream_handler]
)
logger = logging.getLogger("main")

def run_diagnostic_check():
    """
    Verifies system readiness before starting.
    """
    logger.info("--- STARTING SYSTEM DIAGNOSTICS ---")
    all_ok = True
    
    # 1. Internet Check
    try:
        requests.get("https://8.8.8.8", timeout=5)
        logger.info("Internet Connection: OK")
    except Exception:
        logger.error("Internet Connection: FAILED")
        all_ok = False
        
    # 2. Telegram Check
    from alerts.telegram import TelegramBot
    bot = TelegramBot()
    if bot.enabled:
        # Simple test message might be too much, but let's check config at least
        logger.info("Telegram Config: FOUND")
    else:
        logger.warning("Telegram Config: NOT FOUND (Proceeding without alerts)")
        
    # 3. API Keys Check
    from config.settings import POLYGON_API_KEY, TWELVE_DATA_API_KEY, ALPHA_VANTAGE_API_KEY
    keys = {
        "Polygon": POLYGON_API_KEY,
        "TwelveData": TWELVE_DATA_API_KEY,
        "AlphaVantage": ALPHA_VANTAGE_API_KEY
    }
    for name, key in keys.items():
        if key:
            logger.info(f"{name} API Key: FOUND")
        else:
            logger.warning(f"{name} API Key: MISSING")
            
    logger.info("--- DIAGNOSTICS COMPLETE ---")
    return all_ok

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
    
    # 0. Diagnostics
    if not run_diagnostic_check():
        logger.error("System diagnostics failed. Please check your connection and configuration.")
        if not SYSTEM_CONFIG.get("DEVELOPMENT_MODE", False):
            sys.exit(1)
    
    # 1. Startup Tasks
    telegram.send_message("🚀 Trading Advisor STARTED. Monitoring market...")
    run_gap_check(data_mgr)
    
    # 2. Main Loop
    while True:
        cycle_start = datetime.now()
        logger.info(f"--- SCAN CYCLE START: {cycle_start} ---")
        
        # 0b. Get currently active alerts to avoid duplicates
        active_alerts = db.get_active_alerts()
        active_symbols = {a['symbol'] for a in active_alerts}

        for symbol in SYMBOLS:
            # Skip check for active alert here, because we want to MONITOR it first with fresh data.
            # But we should only SCAN if no active alert?
            # Actually, we can scan even if active alert exists (pyramiding?), but for now let's keep simplistic:
            # 1. Update Data
            # 2. Monitor Position (if any)
            # 3. Scan for New Signal (if none)

            # Optimisation: Check if we have active alert for this symbol
            is_active = symbol in active_symbols
            
            try:
                # A. Update Data (Hourly and Daily)
                # Always update to ensure monitoring has fresh data
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
                rows_to_save = df_analyzed.iloc[-48:] 
                db.save_indicators(symbol, "1h", rows_to_save)
                
                # --- MONITORING (Moved Here) ---
                # Check active positions using FRESH data
                if is_active:
                    # Filter active alerts for this symbol
                    symbol_alerts = [a for a in active_alerts if a['symbol'] == symbol]
                    for alert in symbol_alerts:
                        # Monitor using the specific df we just updated
                        # We need to expose a method in TradeManager that accepts the df directly
                        # The monitor_positions loop in TradeManager iterates all alerts. 
                        # We can refactor check_exit_conditions logic or just call it directly here.
                        # Ideally, TradeManager.monitor_single_position(alert, df) ?
                        # For minimum friction, let's look at what we have.
                        # existing monitor_positions iterates all.
                        # Let's extract the core logic or call `check_exit_conditions` here manually.
                        
                        latest_high = float(df_analyzed.iloc[-1]['High'])
                        latest_low = float(df_analyzed.iloc[-1]['Low'])
                        latest_close = float(df_analyzed.iloc[-1]['Close'])
                        latest_ts = df_analyzed.index[-1]
                        
                        trade_mgr.check_exit_conditions(alert, latest_close, latest_high, latest_low, latest_ts, df_analyzed)
                        
                    # If active, skip scanning for new signals (Simplicity)
                    logger.debug(f"Skipping Scan for {symbol}: Position active.")
                    continue 

                # --- SCANNING ---
                
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
                        # DUPLICATE CHECK (Spam Prevention)
                        if db.signal_exists(sig.symbol, sig.timestamp):
                            logger.debug(f"Signal for {sig.symbol} at {sig.timestamp} already exists. Skipping.")
                            continue
                        
                        # Generate Plan
                        # Using configurable capital size for risk management
                        cap_size = SYSTEM_CONFIG.get("INITIAL_CAPITAL", 10000)
                        plan = trade_mgr.create_trade_plan(sig, size=cap_size) 
                        
                        if plan:
                            logger.info(f"ALERT: {plan}")
                            
                            # SNAPSHOT: Capture last 5 rows of indicators + Signal Data
                            # Convert to JSON string
                            snapshot_rows = df_analyzed.iloc[-5:].copy()
                            # Convert timestamp index to string column
                            snapshot_rows.reset_index(inplace=True)
                            snapshot_rows['timestamp'] = snapshot_rows['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
                            snapshot_json = snapshot_rows.to_json(orient='records')
                            
                            # Save to DB
                            db.save_alert(sig, plan, snapshot_data=snapshot_json)
                            # Send Telegram
                            telegram.send_signal_alert(sig, plan)
                            
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                import traceback
                logger.error(traceback.format_exc())
            
            # Rate Limit Protection: Small sleep between symbols
            time.sleep(2)
        
        logger.info("--- CYCLE COMPLETE ---")
        
        # 3. Daily Report (Optional: Send at 22:00 UTC)
        now_utc = datetime.now(timezone.utc)
        if now_utc.hour == 22 and now_utc.minute < 5: # Small window
            report = trade_mgr.generate_performance_report(data_mgr=data_mgr)
            telegram.send_message(report)

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
        
        # Imports
        from backtesting.core.backtester import BacktestEngine
        from backtesting.core.data_loader import DataLoader
        from backtesting.strategies.vwap_bounce import VWAPBounce
        from backtesting.analytics.metrics import MetricsCalculator
        import json
        
        # 1. Load Config
        try:
            with open("backtesting/config.json", "r") as f:
                config = json.load(f)
        except FileNotFoundError:
            logger.error("Config file backtesting/config.json not found.")
            return

        # 2. Override Config with CLI Args
        target_symbols = [args.symbol] if args.symbol else SYMBOLS
        
        if args.start_date:
            config['backtesting']['start_date'] = args.start_date
        if args.end_date:
            config['backtesting']['end_date'] = args.end_date
            
        # Determine Date Objects for Loader
        try:
            start_date = pd.Timestamp(config['backtesting']['start_date'], tz='UTC')
            end_date = pd.Timestamp(config['backtesting']['end_date'], tz='UTC')
        except ValueError:
            # Fallback for relative days
            end_date = pd.Timestamp.now(tz='UTC')
            start_date = end_date - pd.Timedelta(days=args.days)
            
        logger.info(f"Backtesting Range: {start_date} to {end_date}")
        
        # 3. Initialize Loader
        loader = DataLoader()
        
        all_metrics = []

        # 4. Run Loop
        for symbol in target_symbols:
            logger.info(f"Running Backtest for {symbol}...")
            
            # Load Data
            data = loader.load_data(
                symbol=symbol, 
                interval=config['backtesting']['interval'],
                start_date=start_date,
                end_date=end_date
            )
            
            if data.empty:
                logger.warning(f"No data for {symbol}. Skipping.")
                continue
                
            # Init Engine
            engine = BacktestEngine(
                initial_capital=config['backtesting']['initial_capital'],
                commission=config['backtesting']['commission'],
                slippage=config['backtesting']['slippage'],
                config=config,
                symbol=symbol,
                strategy_name="VWAPBounce"
            )
            
            # Setup Strategy
            strategy = VWAPBounce()
            # Use params from config
            strat_params = config['strategies'].get('vwap_bounce', {})
            engine.set_strategy(strategy, strat_params)
            
            # Run
            results = engine.run(symbol, data)
            
            # Calculate Metrics
            metrics = MetricsCalculator.calculate_metrics(
                results['trades'], 
                results['equity_curve'], 
                config['backtesting']['initial_capital']
            )
            
            # Store for Summary
            metrics['Symbol'] = symbol
            all_metrics.append(metrics)

            # Print Individual Report
            print(f"\nResults for {symbol}:")
            print(f"  P&L: {metrics.get('Total P&L %'):.2f}%")
            print(f"  Win Rate: {metrics.get('Win Rate %'):.2f}%")
            print(f"  Sharpe: {metrics.get('Sharpe Ratio'):.2f}")
            print(f"  Trades: {metrics.get('Total Trades')}")
        
        # 5. Print Final Summary
        if all_metrics:
            print("\n" + "="*80)
            print("FINAL BACKTEST SUMMARY")
            print("="*80)
            
            summary_data = []
            for m in all_metrics:
                summary_data.append({
                    "Symbol": m['Symbol'],
                    "P&L %": f"{m.get('Total P&L %'):+,.2f}%",
                    "Win Rate": f"{m.get('Win Rate %'):.1f}%",
                    "Sharpe": m.get("Sharpe Ratio"),
                    "MaxDD": f"{m.get('Max Drawdown %'):.1f}%",
                    "Trades": m.get("Total Trades"),
                    "Profit Factor": m.get("Profit Factor")
                })
            
            df_summary = pd.DataFrame(summary_data)
            print(df_summary.to_string(index=False))
            print("="*80)

        logger.info("Backtest execution completed.")

if __name__ == "__main__":
    main()
