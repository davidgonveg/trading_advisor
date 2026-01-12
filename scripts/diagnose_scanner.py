
import logging
import sys
import pandas as pd
import os

sys.path.append(os.getcwd())
from data.storage.database import Database
from config.settings import STRATEGY_CONFIG

def main():
    db = Database()
    symbol = "SPY"
    
    # Load Data
    df_1h = db.load_market_data(symbol, "1h")
    df_1h.columns = [c.capitalize() for c in df_1h.columns]
    
    df_ind = db.load_indicators(symbol, "1h")
    df_combined = df_1h.join(df_ind, how='inner', lsuffix='_price', rsuffix='')
    
    total = len(df_combined)
    print(f"Total Rows: {total}")
    
    # Check Conditions
    cfg = STRATEGY_CONFIG
    
    # 1. ADX
    adx_ok = df_combined[df_combined['ADX'] < cfg['ADX_MAX_THRESHOLD']]
    print(f"ADX < {cfg['ADX_MAX_THRESHOLD']}: {len(adx_ok)} ({len(adx_ok)/total*100:.1f}%)")
    
    # 2. RSI Long
    rsi_ok = df_combined[df_combined['RSI'] < cfg['RSI_OVERSOLD']]
    print(f"RSI < {cfg['RSI_OVERSOLD']}: {len(rsi_ok)} ({len(rsi_ok)/total*100:.1f}%)")
    
    # 3. BB Lower Long
    bb_ok = df_combined[df_combined['Close'] <= df_combined['BB_Lower']]
    print(f"Close <= BB_Lower: {len(bb_ok)} ({len(bb_ok)/total*100:.1f}%)")
    
    # 4. Volume
    vol_ok = df_combined[df_combined['Volume'] > df_combined['Volume_SMA_20']]
    print(f"Volume > SMA20: {len(vol_ok)} ({len(vol_ok)/total*100:.1f}%)")
    
    # 5. Combined ADX + RSI + BB
    comb = df_combined[
        (df_combined['ADX'] < cfg['ADX_MAX_THRESHOLD']) &
        (df_combined['RSI'] < cfg['RSI_OVERSOLD']) &
        (df_combined['Close'] <= df_combined['BB_Lower'])
    ]
    print(f"Combined (ADX+RSI+BB): {len(comb)}")
    
    if len(comb) > 0:
        print("Sample Combined Candidates:")
        print(comb[['Close', 'RSI', 'ADX', 'BB_Lower']].head())

if __name__ == "__main__":
    main()
