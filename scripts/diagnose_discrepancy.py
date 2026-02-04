"""
Diagnostic Script to Compare Live vs Backtest Signal Detection
Analyzes why backtesting detected 0 trades when live trading generated 2 signals.
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from datetime import datetime, timezone
from data.storage.database import Database
from analysis.indicators import TechnicalIndicators
from analysis.scanner import Scanner
from backtesting.strategies.vwap_bounce import VWAPBounce
from backtesting.core.strategy_interface import SignalSide
import json

def load_data_for_symbol(db: Database, symbol: str, date_str: str):
    """Load hourly data for a specific symbol and date."""
    df = db.load_market_data(symbol, "1h")
    if df.empty:
        print(f"❌ No data found for {symbol}")
        return pd.DataFrame()
    
    # Filter to specific date
    target_date = pd.Timestamp(date_str, tz='UTC')
    df_day = df[df.index.date == target_date.date()]
    
    print(f"✓ Loaded {len(df_day)} bars for {symbol} on {date_str}")
    return df_day

def compare_indicators(live_df: pd.DataFrame, backtest_df: pd.DataFrame, symbol: str):
    """Compare indicator values between live and backtest."""
    print(f"\n{'='*80}")
    print(f"INDICATOR COMPARISON: {symbol}")
    print(f"{'='*80}")
    
    if live_df.empty or backtest_df.empty:
        print("❌ Cannot compare - missing data")
        return
    
    # Get common timestamps
    common_ts = live_df.index.intersection(backtest_df.index)
    if len(common_ts) == 0:
        print("❌ No common timestamps found!")
        return
    
    print(f"Comparing {len(common_ts)} common timestamps\n")
    
    # Compare key indicators
    indicators_to_check = ['VWAP', 'Volume', 'ATR', 'Close', 'High', 'Low']
    
    for ts in common_ts:
        print(f"\n📅 {ts}")
        print(f"{'-'*80}")
        
        live_row = live_df.loc[ts]
        backtest_row = backtest_df.loc[ts]
        
        # Handle duplicate indices
        if isinstance(live_row, pd.DataFrame):
            live_row = live_row.iloc[0]
        if isinstance(backtest_row, pd.DataFrame):
            backtest_row = backtest_row.iloc[0]
        
        for ind in indicators_to_check:
            live_val = live_row.get(ind, np.nan)
            backtest_val = backtest_row.get(ind, np.nan)
            
            if pd.notna(live_val) and pd.notna(backtest_val):
                diff = abs(live_val - backtest_val)
                match = "✓" if diff < 0.01 else "✗"
                print(f"  {match} {ind:15s}: Live={live_val:10.2f} | Backtest={backtest_val:10.2f} | Diff={diff:.4f}")
            else:
                print(f"  ⚠ {ind:15s}: Live={live_val} | Backtest={backtest_val}")

def check_entry_conditions(df: pd.DataFrame, symbol: str, mode: str):
    """Check which bars meet entry conditions."""
    print(f"\n{'='*80}")
    print(f"ENTRY CONDITIONS CHECK: {symbol} ({mode})")
    print(f"{'='*80}\n")
    
    results = []
    
    for i, (ts, row) in enumerate(df.iterrows()):
        # Handle duplicate indices
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        
        # Extract values
        close = row.get('Close', np.nan)
        high = row.get('High', np.nan)
        low = row.get('Low', np.nan)
        open_price = row.get('Open', np.nan)
        volume = row.get('Volume', np.nan)
        vwap = row.get('VWAP', np.nan)
        vol_sma = row.get('Volume_SMA_20', np.nan)
        ema_200 = row.get('EMA_200', np.nan)
        
        if pd.isna(vwap) or pd.isna(volume) or pd.isna(vol_sma):
            continue
        
        # Calculate wicks
        body = abs(close - open_price)
        lower_wick = min(open_price, close) - low
        upper_wick = high - max(open_price, close)
        
        # Check conditions
        # LONG conditions
        bounce_long = (low <= vwap) and (close > vwap)
        wick_long = lower_wick > (2.0 * body)  # Live uses 2.0
        vol_long = volume > vol_sma
        trend_long = close > ema_200 if pd.notna(ema_200) else False
        
        # SHORT conditions
        bounce_short = (high >= vwap) and (close < vwap)
        wick_short = upper_wick > (2.0 * body)
        vol_short = volume > vol_sma
        trend_short = close < ema_200 if pd.notna(ema_200) else False
        
        signal = None
        if bounce_long and wick_long and vol_long and trend_long:
            signal = "LONG"
        elif bounce_short and wick_short and vol_short and trend_short:
            signal = "SHORT"
        
        if signal or (bounce_long or bounce_short):  # Show near-misses too
            results.append({
                'timestamp': ts,
                'signal': signal or "NONE",
                'close': close,
                'vwap': vwap,
                'ema_200': ema_200,
                'volume': volume,
                'vol_sma': vol_sma,
                'body': body,
                'lower_wick': lower_wick,
                'upper_wick': upper_wick,
                'bounce_long': bounce_long,
                'wick_long': wick_long,
                'vol_long': vol_long,
                'trend_long': trend_long,
                'bounce_short': bounce_short,
                'wick_short': wick_short,
                'vol_short': vol_short,
                'trend_short': trend_short
            })
    
    if results:
        print(f"Found {len(results)} bars with potential signals:\n")
        for r in results:
            print(f"📊 {r['timestamp']} | Signal: {r['signal']}")
            print(f"   Price: ${r['close']:.2f} | VWAP: ${r['vwap']:.2f} | EMA200: ${r['ema_200']:.2f}")
            print(f"   Volume: {r['volume']:.0f} vs SMA: {r['vol_sma']:.0f} ({r['volume']/r['vol_sma']:.2f}x)")
            print(f"   Body: ${r['body']:.2f} | Lower Wick: ${r['lower_wick']:.2f} | Upper Wick: ${r['upper_wick']:.2f}")
            print(f"   LONG Conditions: Bounce={r['bounce_long']} | Wick={r['wick_long']} | Vol={r['vol_long']} | Trend={r['trend_long']}")
            print(f"   SHORT Conditions: Bounce={r['bounce_short']} | Wick={r['wick_short']} | Vol={r['vol_short']} | Trend={r['trend_short']}")
            print()
    else:
        print("❌ No bars met entry conditions")
    
    return results

def run_live_scanner(symbol: str, date_str: str):
    """Run the live trading scanner logic."""
    print(f"\n{'='*80}")
    print(f"RUNNING LIVE SCANNER: {symbol}")
    print(f"{'='*80}\n")
    
    db = Database()
    df = load_data_for_symbol(db, symbol, date_str)
    
    if df.empty:
        return None, pd.DataFrame()
    
    # Calculate indicators using live logic
    indicators = TechnicalIndicators()
    df_analyzed = indicators.calculate_all(df)
    
    # Run scanner
    scanner = Scanner()
    signals = scanner.find_signals(symbol, df_analyzed, scan_latest=False)
    
    print(f"✓ Live scanner found {len(signals)} signals")
    for sig in signals:
        print(f"  - {sig.timestamp} | {sig.type.value} @ ${sig.price:.2f}")
    
    return signals, df_analyzed

def run_backtest_strategy(symbol: str, date_str: str):
    """Run the backtesting strategy logic."""
    print(f"\n{'='*80}")
    print(f"RUNNING BACKTEST STRATEGY: {symbol}")
    print(f"{'='*80}\n")
    
    db = Database()
    df = load_data_for_symbol(db, symbol, date_str)
    
    if df.empty:
        return [], pd.DataFrame()
    
    # Load backtest config
    with open("backtesting/config.json", "r") as f:
        config = json.load(f)
    
    params = config['strategies']['vwap_bounce']
    
    # Initialize strategy
    strategy = VWAPBounce()
    strategy.symbol = symbol
    strategy.setup(params)
    
    # Precompute indicators
    strategy._precompute_indicators(df)
    
    # Run bar by bar
    signals = []
    for i in range(len(df)):
        history = df.iloc[:i+1]
        portfolio_ctx = {
            "positions": {symbol: 0.0},
            "total_equity": 100000.0,
            "cash": 100000.0
        }
        
        signal = strategy.on_bar(history, portfolio_ctx)
        
        if signal and signal.side != SignalSide.HOLD:
            signals.append({
                'timestamp': df.index[i],
                'side': signal.side.value,
                'tag': signal.tag,
                'indicators': strategy.last_indicators.copy()
            })
            print(f"  - {df.index[i]} | {signal.side.value} | {signal.tag}")
    
    print(f"✓ Backtest strategy found {len(signals)} signals")
    
    return signals, strategy.indicators_df

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Diagnose backtest-live discrepancy")
    parser.add_argument('--date', default='2026-02-02', help='Date to analyze (YYYY-MM-DD)')
    parser.add_argument('--symbols', nargs='+', default=['XLK', 'GLD'], help='Symbols to analyze')
    args = parser.parse_args()
    
    print(f"\n{'#'*80}")
    print(f"# BACKTEST-LIVE DISCREPANCY DIAGNOSTIC")
    print(f"# Date: {args.date}")
    print(f"# Symbols: {', '.join(args.symbols)}")
    print(f"{'#'*80}\n")
    
    for symbol in args.symbols:
        print(f"\n\n{'█'*80}")
        print(f"█ ANALYZING: {symbol}")
        print(f"{'█'*80}\n")
        
        # Run live scanner
        live_signals, live_df = run_live_scanner(symbol, args.date)
        
        # Run backtest strategy
        backtest_signals, backtest_df = run_backtest_strategy(symbol, args.date)
        
        # Compare indicators
        if not live_df.empty and not backtest_df.empty:
            compare_indicators(live_df, backtest_df, symbol)
        
        # Check entry conditions for live data
        if not live_df.empty:
            check_entry_conditions(live_df, symbol, "LIVE")
        
        # Check entry conditions for backtest data
        if not backtest_df.empty:
            check_entry_conditions(backtest_df, symbol, "BACKTEST")
        
        # Summary
        print(f"\n{'='*80}")
        print(f"SUMMARY: {symbol}")
        print(f"{'='*80}")
        print(f"Live Signals: {len(live_signals) if live_signals else 0}")
        print(f"Backtest Signals: {len(backtest_signals)}")
        
        if live_signals and len(backtest_signals) != len(live_signals):
            print(f"\n⚠️  DISCREPANCY DETECTED!")
            print(f"   Expected {len(live_signals)} signals, got {len(backtest_signals)}")
        elif live_signals:
            print(f"\n✓ Signal count matches!")
        
        print(f"{'='*80}\n")

if __name__ == "__main__":
    main()
