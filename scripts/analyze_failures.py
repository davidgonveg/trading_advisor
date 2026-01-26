import pandas as pd
import numpy as np

def analyze_failures():
    file_path = "backtesting/results/round_trips_detailed.csv"
    try:
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        print("CSV not found.")
        return

    print("--- Detailed Failure Analysis ---\n")
    
    # 1. Commission Impact
    total_pnl = df['pnl_net'].sum()
    gross_pnl = df['gross_pnl'].sum()
    commissions = df['commission'].sum()
    print(f"Total Net PnL: ${total_pnl:.2f}")
    print(f"Total Gross PnL: ${gross_pnl:.2f}")
    print(f"Total Commissions: ${commissions:.2f}")
    print(f"Commissions as % of Gross Loss: {abs(commissions / gross_pnl)*100:.1f}%" if gross_pnl != 0 else "N/A")
    
    # Check winning trades turned losers by commissions
    turned_losers = df[(df['gross_pnl'] > 0) & (df['pnl_net'] < 0)]
    print(f"\nTrades Positive Gross but Negative Net: {len(turned_losers)}")
    if not turned_losers.empty:
        print(turned_losers[['symbol', 'gross_pnl', 'commission', 'pnl_net']].head())

    # 2. Exit Code Analysis
    print("\n--- PnL by Exit Reason ---")
    print(df.groupby('exit_reason')['pnl_net'].agg(['count', 'mean', 'sum', 'min', 'max']))

    # 3. Strategy Parameters vs Outcome
    # Correlation of Entry Metrics with PnL
    print("\n--- Correlations with Net PnL ---")
    numeric_cols = ['atr', 'adx', 'duration_h']
    print(df[numeric_cols].corrwith(df['pnl_net']))

    # 4. ADX Analysis (Is Trend Filter working?)
    print("\n--- ADX Buckets Performance ---")
    df['adx_bucket'] = pd.cut(df['adx'], bins=[0, 20, 25, 30, 40, 60, 100])
    print(df.groupby('adx_bucket')['pnl_net'].agg(['count', 'mean', 'sum']))

    # 5. Stop Loss Analysis
    # Are we hitting SL too fast? Avg duration of SL trades
    sl_trades = df[df['exit_reason'] == 'SL']
    print(f"\nAvg Duration of SL Trades: {sl_trades['duration_h'].mean():.1f} hours")
    
    # 6. Take Profit Analysis
    # Compare Avg Win vs Avg Loss
    wins = df[df['pnl_net'] > 0]
    losses = df[df['pnl_net'] <= 0]
    avg_win = wins['pnl_net'].mean() if not wins.empty else 0
    avg_loss = losses['pnl_net'].mean() if not losses.empty else 0
    
    print(f"\nAvg Win: ${avg_win:.2f}")
    print(f"Avg Loss: ${avg_loss:.2f}")
    print(f"Risk/Reward Realized: {abs(avg_win/avg_loss):.2f}" if avg_loss != 0 else "Inf")
    
    # 7. Time Stop Analysis
    time_stops = df[df['exit_reason'] == 'TIME_STOP']
    print("\n--- Time Stop Analysis ---")
    print(f"Count: {len(time_stops)}")
    if not time_stops.empty:
        print(f"Avg PnL: ${time_stops['pnl_net'].mean():.2f}")
        # Were they profitable at least grossly?
        print(f"Profitable Gross: {len(time_stops[time_stops['gross_pnl']>0])} / {len(time_stops)}")

if __name__ == "__main__":
    analyze_failures()
