
import sys
import os
import pandas as pd
from datetime import datetime
import logging

# Ensure root is in path
sys.path.append(os.getcwd())

from data.storage.database import Database
from config.settings import STRATEGY_CONFIG
from analysis.patterns import PatternRecognizer

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("diagnose_full")

def analyze_symbol(symbol: str):
    print(f"\n{'='*20} FULL HISTORY DIAGNOSTIC: {symbol} {'='*20}")
    
    db = Database()
    
    # 1. Load Data
    df_1h = db.load_market_data(symbol, "1h")
    df_ind = db.load_indicators(symbol, "1h")
    
    if df_1h.empty:
        print(f"❌ No 1H Market Data found for {symbol}")
        return
        
    if df_ind.empty:
        print(f"❌ No 1H Indicator Data found for {symbol}")
        return

    # Merge and standardize
    df_1h.columns = [c.capitalize() for c in df_1h.columns]
    df_ind.columns = [c for c in df_ind.columns] # Already capitalized? No, load_indicators lowercases usually? 
    # Wait, check DB load_indicators logic.
    # In step 921 update: "Rename columns" was commented out or partial?
    # Let's verify columns in df_ind.
    
    # Quick fix for columns if needed
    rename_map = {
        'rsi': 'RSI', 'bb_upper': 'BB_Upper', 'bb_lower': 'BB_Lower', 
        'adx': 'ADX', 'sma_50': 'SMA_50', 'volume_sma_20': 'Volume_SMA_20',
        'vwap': 'VWAP', 'atr': 'ATR'
    }
    df_ind.rename(columns=rename_map, inplace=True)
    # Also handle Capitalized from SQL if they are capitalized there (unlikely)
    
    df = df_1h.join(df_ind, how='inner', lsuffix='_price', rsuffix='')
    
    # 2. Check Range
    start_date = df.index.min()
    end_date = df.index.max()
    days = (end_date - start_date).days
    print(f"📅 Data Range: {start_date} -> {end_date} ({days} days)")
    print(f"🕯️ Total Candles: {len(df)}")
    
    # 3. Detect Patterns (Simulate Scanner)
    recognizer = PatternRecognizer()
    df = recognizer.detect_patterns(df)
    
    # 4. Apply Filters Step-by-Step (Long Logic only for brevity, or both)
    # Common
    cfg = STRATEGY_CONFIG
    
    # Filters
    # Note: We use boolean indexing for stats
    
    mask_metrics = df['ADX'] < cfg['ADX_MAX_THRESHOLD']
    mask_volume = df['Volume'] > df['Volume_SMA_20']
    
    # Long Conditions
    mask_rsi_long = df['RSI'] < cfg['RSI_OVERSOLD']
    mask_bb_long = df['Close'] <= df['BB_Lower']
    mask_trend_long = df['Close'] > df['SMA_50'] # Proximate trend check (1H SMA50 is not Daily, but let's check what we have)
    # WAIT: Signal logic uses DAILY SMA50. 
    # df['SMA_50'] in indicators table might be 1H SMA50.
    # If so, this is a discrepancy. Scanner uses passed df_daily.
    # For this diagnostic, we'll assume the 'SMA_50' col in 1H indicators might be wrong for Trend check if it's 1H.
    # But let's check the values.
    
    # Pattern
    # check_bullish_reversal checks: pat_hammer > 0 OR pat_engulfing > 0 OR pat_doji > 0
    # Let's explicity check columns
    has_hammer = df['pat_hammer'] > 0
    has_bull_eng = df['pat_engulfing'] > 0
    has_doji = df['pat_doji'] > 0
    mask_pattern_long = has_hammer | has_bull_eng | has_doji
    
    # Counts
    print(f"\n--- FILTER PASS RATES (LONG Candidates) ---")
    print(f"1. ADX < {cfg['ADX_MAX_THRESHOLD']}: {mask_metrics.sum()} ({mask_metrics.mean()*100:.1f}%)")
    print(f"2. Volume > SMA20: {mask_volume.sum()} ({mask_volume.mean()*100:.1f}%)")
    print(f"3. RSI < {cfg['RSI_OVERSOLD']}: {mask_rsi_long.sum()} ({mask_rsi_long.mean()*100:.1f}%)")
    print(f"4. Price <= BB_Lower: {mask_bb_long.sum()} ({mask_bb_long.mean()*100:.1f}%)")
    
    # Patterns
    print(f"5. Patterns (Any Bullish): {mask_pattern_long.sum()} ({mask_pattern_long.mean()*100:.1f}%)")
    print(f"   - Hammer: {has_hammer.sum()}")
    print(f"   - Bull Engulfing: {has_bull_eng.sum()}")
    print(f"   - Doji: {has_doji.sum()}")
    
    # Intersections
    # Step 1+2 (Context)
    context_ok = mask_metrics & mask_volume
    print(f"\n--- INTERSECTIONS ---")
    print(f"A. Context (ADX & Vol): {context_ok.sum()}")
    
    # Indicators (RSI & BB)
    indicators_long = mask_rsi_long & mask_bb_long
    print(f"B. Indicators (RSI & BB): {indicators_long.sum()}")
    
    # A + B
    candidates = context_ok & indicators_long
    print(f"C. Candidates (Context & Indicators): {candidates.sum()}")
    
    # A + B + Pattern
    final_long = candidates & mask_pattern_long
    print(f"D. FINAL SIGNALS (Candidates + Pattern): {final_long.sum()}")
    
    if candidates.sum() > 0:
        print(f"\n--- INSPECTING {candidates.sum()} CANDIDATES (Metrics OK, Pattern ???) ---")
        debug_df = df[candidates][['Close', 'RSI', 'ADX', 'pat_hammer', 'pat_engulfing', 'pat_doji']]
        print(debug_df.head(20))
        
        # Check why they failed
        no_pat = debug_df[(debug_df['pat_hammer']==0) & (debug_df['pat_engulfing']==0) & (debug_df['pat_doji']==0)]
        print(f"\nCandidates with NO Pattern: {len(no_pat)}")

    if final_long.sum() > 0:
        print("\n✅ Found Potential Signals:")
        print(df[final_long][['Close', 'RSI', 'ADX', 'pat_hammer', 'pat_doji']].head())
    else:
        print("\n❌ No Long Signals (Zero Intersection)")

if __name__ == "__main__":
    analyze_symbol("GLD")
