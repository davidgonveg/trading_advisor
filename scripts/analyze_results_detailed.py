import pandas as pd
import numpy as np
import sys
import os
sys.path.append(os.getcwd()) # Add current directory to path


def analyze_trades():
    try:
        df = pd.read_csv('backtesting/results/trades.csv')
    except FileNotFoundError:
        print("trades.csv not found")
        return

    # trades.csv seems to be Fills, not completed Round-Trip trades?
    # run.py says: "NOTE: Broker.trades is a list of fills (entries and exits mixed)."
    # Wait, broker.py Trade object is an execution.
    # We need to reconstruct Round Trips to calculate Win Rate properly.
    
    # Or does the broker export RoundTrips separately?
    # run.py : logger.save_trades(engine.broker.trades)
    # The broker.trades list stores Trade objects which are individual executions (Buy/Sell).
    
    # We need to reconstruct PnL from executions to verify "Final Equity".
    # And to calc Win Rate.
    
    print("--- RAW FILLS ANALYSIS ---")
    print(f"Total Fills: {len(df)}")
    print(df.head())
    
    # We can group by Symbol and FIFO match buys/sells to calculate PnL per "Trade Cycle".
    # Or, does the broker track PnL per trade?
    # broker.py Trade object has 'pnl' field.
    # Let's check if it's populated.
    
    if 'pnl' in df.columns:
        # Check if pnl is non-null
        closes = df[df['pnl'].notna() & (df['pnl'] != 0)]
        print(f"\n--- TRADES WITH PnL ---")
        print(f"Count: {len(closes)}")
        
        if len(closes) > 0:
            wins = closes[closes['pnl'] > 0]
            losses = closes[closes['pnl'] <= 0]
            
            win_rate = len(wins) / len(closes) * 100
            avg_win = wins['pnl'].mean()
            avg_loss = losses['pnl'].mean()
            total_pnl = closes['pnl'].sum()
            
            print(f"Win Rate: {win_rate:.2f}%")
            print(f"Avg Win: ${avg_win:.2f}")
            print(f"Avg Loss: ${avg_loss:.2f}")
            print(f"Total Realized PnL: ${total_pnl:.2f}")
            print(f"Max Win: ${wins['pnl'].max() if not wins.empty else 0}")
            print(f"Max Loss: ${losses['pnl'].min() if not losses.empty else 0}")
            
            # Commissions
            total_comm = df['commission'].sum()
            print(f"Total Commissions: ${total_comm:.2f}")
            print(f"Net PnL (approx): ${total_pnl - total_comm:.2f}")
        else:
            print("No PnL recorded on trades. Broker might not be calculating realized PnL on fills.")

    # Duplicate Data Check moved to verify_backtest_data_strict.py


if __name__ == "__main__":
    analyze_trades()
