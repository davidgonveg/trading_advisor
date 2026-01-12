import pandas as pd
import glob
import os

# Find latest trades csv
list_of_files = glob.glob('backtesting/results/trades_*.csv') 
latest_file = max(list_of_files, key=os.path.getctime)
print(f"Reading: {latest_file}")

df = pd.read_csv(latest_file)

if df.empty:
    print("CSV is empty/no trades.")
else:
    # Summarize exits
    if 'exit_reason' in df.columns:
        print("\nExit Reasons Breakdown:")
        print(df['exit_reason'].value_counts())
    
    # Summarize P&L
    print(f"\nTotal P&L: ${df['total_pnl'].sum():.2f}")
    
    # Show dataframe head
    columns = ['symbol', 'direction', 'entry_1_time', 'last_exit_time', 'exit_reason', 'total_pnl']
    # Filter columns that exist
    cols = [c for c in columns if c in df.columns]
    print("\nSample Trades:")
    print(df[cols].head(10).to_string())
    
    print("\nSample Trades (Losses):")
    print(df[df['total_pnl'] < 0][cols].head(5).to_string())
