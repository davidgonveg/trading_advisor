import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import warnings

# Suppress futures warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

def load_data():
    try:
        df = pd.read_csv("backtesting/results/round_trips_detailed.csv")
        return df
    except FileNotFoundError:
        print("Error: round_trips_detailed.csv not found.")
        return None

def analyze_exit_reasons(df):
    print("\n--- 1. Exit Reason Forensic Analysis ---")
    
    # 1. Decode UNK reasons
    # Assumption: If PnL > 0 it's likely a TP or signal exit in profit.
    # If PnL < 0 it's likely an SL or signal exit in loss.
    # Let's check if they hit the recorded SL/TP prices.
    
    unknowns = df[df['exit_reason'].isin(['PROFIT_UNK', 'LOSS_UNK'])].copy()
    if not unknowns.empty:
        print(f"Analyzing {len(unknowns)} 'Unknown' Exits...")
        
        # Check proximity to TP1/SL
        # tolerance = 0.5%
        unknowns['dist_tp1'] = abs(unknowns['exit_avg'] - unknowns['tp1_price']) / unknowns['tp1_price']
        unknowns['dist_sl'] = abs(unknowns['exit_avg'] - unknowns['sl_price']) / unknowns['sl_price']
        
        likely_tp1 = len(unknowns[unknowns['dist_tp1'] < 0.005]) 
        likely_sl = len(unknowns[unknowns['dist_sl'] < 0.005])
        
        print(f"  > Of {len(unknowns)} UNK exits:")
        print(f"    - {likely_tp1} appear to be TP1 hits (within 0.5%)")
        print(f"    - {likely_sl} appear to be SL hits (within 0.5%)")
        print(f"    - {len(unknowns) - likely_tp1 - likely_sl} remain unexplained (likely signal-based exits)")
        
        # Deep dive into the unexplained
        unexplained = unknowns[(unknowns['dist_tp1'] >= 0.005) & (unknowns['dist_sl'] >= 0.005)]
        if not unexplained.empty:
            print("\n  > Sample Unexplained Exits:")
            print(unexplained[['symbol', 'entry_time', 'exit_time', 'exit_reason', 'pnl_net', 'duration_h']].head(5).to_string())

def analyze_adx_anomaly(df):
    print("\n--- 2. The 'High ADX' Anomaly Investigation ---")
    
    # Filter for High ADX trades (> 50)
    high_adx = df[df['entry_ADX'] > 50].copy()
    
    if high_adx.empty:
        print("No High ADX trades found.")
        return

    print(f"Found {len(high_adx)} trades with Entry ADX > 50.")
    print(f"Win Rate: {len(high_adx[high_adx['pnl_net'] > 0]) / len(high_adx) * 100:.1f}%")
    print(f"Avg PnL: ${high_adx['pnl_net'].mean():.2f}")
    
    # Check direction
    print("\n  > Direction Breakdown:")
    print(high_adx['direction'].value_counts())
    
    # Check if they are 'catch the knife' (Long when price << Lower Band)
    # We can check distance from BB Lower
    if 'entry_BB_Lower' in high_adx.columns:
        high_adx['dist_bb_lower'] = (high_adx['entry_avg'] - high_adx['entry_BB_Lower'])
        print(f"\n  > Avg Distance from BB Lower at entry: {high_adx['dist_bb_lower'].mean():.2f}")
        print("    (Negative means buying BELOW the band - extreme reversion)")

def analyze_time_stops(df):
    print("\n--- 3. Time Stop Dissection ---")
    time_stops = df[df['exit_reason'] == 'TIME_STOP'].copy()
    
    if time_stops.empty:
        print("No Time Stops found.")
        return
        
    print(f"Analyzing {len(time_stops)} Time Stop Exits.")
    print(f"Avg Duration: {time_stops['duration_h'].mean():.1f} hours")
    print(f"Total Loss: ${time_stops['pnl_net'].sum():.2f}")
    
    # Did they ever have a chance?
    time_stops['price_drift_pct'] = (time_stops['exit_avg'] - time_stops['entry_avg']) / time_stops['entry_avg'] * 100
    print("\n  > Price Drift Analysis (Exit vs Entry %):")
    print(time_stops[['symbol', 'direction', 'price_drift_pct', 'pnl_net']].to_string())
    
    print(f"\n  > Avg Drift: {time_stops['price_drift_pct'].mean():.2f}%")
    print("    (If this is small negative, we are paying theta/opportunity cost. If large negative, stop loss was effectively useless or too wide.)")

def compare_winners_losers(df):
    print("\n--- 4. Winners vs Losers Structure ---")
    winners = df[df['pnl_net'] > 0]
    losers = df[df['pnl_net'] <= 0]
    
    print(f"Winners: {len(winners)} | Losers: {len(losers)}")
    
    cols_to_compare = ['entry_RSI', 'entry_ADX', 'entry_ATR', 'duration_h']
    available_cols = [c for c in cols_to_compare if c in df.columns]
    
    comparison = pd.DataFrame({
        'Winner Avg': winners[available_cols].mean(),
        'Loser Avg': losers[available_cols].mean(),
        'Delta %': (winners[available_cols].mean() - losers[available_cols].mean()) / losers[available_cols].mean() * 100
    })
    
    print(comparison)

def main():
    df = load_data()
    if df is not None:
        analyze_exit_reasons(df)
        analyze_adx_anomaly(df)
        analyze_time_stops(df)
        compare_winners_losers(df)

if __name__ == "__main__":
    main()
