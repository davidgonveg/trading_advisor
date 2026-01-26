import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def analyze():
    print("Loading results...")
    trades_path = "backtesting/results/trades.csv"
    equity_path = "backtesting/results/equity.csv"
    
    try:
        trades = pd.read_csv(trades_path)
        equity = pd.read_csv(equity_path)
        equity['timestamp'] = pd.to_datetime(equity['timestamp'])
        equity.set_index('timestamp', inplace=True)
        trades['timestamp'] = pd.to_datetime(trades['timestamp'])
    except Exception as e:
        print(f"Error loading files: {e}")
        return

    # 1. Equity Analysis
    start_equity = equity['equity'].iloc[0]
    end_equity = equity['equity'].iloc[-1]
    total_return = (end_equity - start_equity) / start_equity
    
    # Drawdown
    equity['peak'] = equity['equity'].cummax()
    equity['drawdown'] = (equity['equity'] - equity['peak']) / equity['peak']
    max_drawdown = equity['drawdown'].min()
    
    print("\n--- PERFORMANCE METRICS ---")
    print(f"Start Equity: ${start_equity:.2f}")
    print(f"End Equity:   ${end_equity:.2f}")
    print(f"Total Return: {total_return*100:.2f}%")
    print(f"Max Drawdown: {max_drawdown*100:.2f}%")
    
    # 2. Trade Analysis
    # We need to reconstruct Round Trips to get accurate Win Rate
    # Since trades.csv lists individual fills (Entry, Partial Exit, Exit), we need to group them.
    # Logic: Group by Symbol. Iterate chronologically.
    # Match Entry with subsequent exits until flat.
    
    round_trips = []
    
    # Separate by symbol
    symbols = trades['symbol'].unique()
    
    for sym in symbols:
        sym_trades = trades[trades['symbol'] == sym].sort_values('timestamp')
        
        current_pos = 0
        entry_price = 0
        entry_time = None
        
        # PnL tracking for the current "trip"
        current_realized_pnl = 0
        current_invested = 0
        
        for idx, row in sym_trades.iterrows():
            qty = row['quantity']
            price = row['price']
            side = row['side']
            comm = row['commission']
            
            # Signed Quantity
            signed_qty = qty if side == 'BUY' else -qty
            
            # Check if opening new position (from flat)
            if current_pos == 0:
                current_pos = signed_qty
                entry_price = price
                entry_time = row['timestamp']
                current_realized_pnl = -comm
                # Invested roughly Price * Qty
                current_invested = price * qty
            else:
                # Modifying position
                # If sign is same, adding to position
                if np.sign(signed_qty) == np.sign(current_pos):
                    # Averaging entry
                    total_val = (abs(current_pos) * entry_price) + (abs(signed_qty) * price)
                    current_pos += signed_qty
                    entry_price = total_val / abs(current_pos)
                    current_realized_pnl -= comm
                    current_invested += price * qty
                else:
                    # Reducing/Closing
                    # PnL on the closed portion
                    closed_qty = min(abs(current_pos), abs(signed_qty))
                    
                    if current_pos > 0: # Long Closing
                        pnl = (price - entry_price) * closed_qty
                    else: # Short Closing
                        pnl = (entry_price - price) * closed_qty
                        
                    current_realized_pnl += (pnl - comm)
                    current_pos += signed_qty
                    
                    if abs(current_pos) < 1e-9: # Closed
                        # Record Trip
                        round_trips.append({
                            'symbol': sym,
                            'entry_time': entry_time,
                            'exit_time': row['timestamp'],
                            'pnl': current_realized_pnl,
                            'return_pct': (current_realized_pnl / current_invested) * 100 if current_invested > 0 else 0
                        })
                        current_pos = 0
                        current_invested = 0
                        current_realized_pnl = 0

    rt_df = pd.DataFrame(round_trips)
    
    if not rt_df.empty:
        total_trades = len(rt_df)
        wins = rt_df[rt_df['pnl'] > 0]
        losses = rt_df[rt_df['pnl'] <= 0]
        
        win_rate = len(wins) / total_trades
        avg_win = wins['pnl'].mean() if not wins.empty else 0
        avg_loss = losses['pnl'].mean() if not losses.empty else 0
        
        gross_profit = wins['pnl'].sum()
        gross_loss = abs(losses['pnl'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        print(f"\n--- TRADE STATS ---")
        print(f"Total Trades: {total_trades}")
        print(f"Win Rate:     {win_rate*100:.2f}%")
        print(f"Profit Factor: {profit_factor:.2f}")
        print(f"Avg Win:      ${avg_win:.2f}")
        print(f"Avg Loss:     ${avg_loss:.2f}")
        print(f"Largest Win:  ${rt_df['pnl'].max():.2f}")
        print(f"Largest Loss: ${rt_df['pnl'].min():.2f}")
    else:
        print("No complete round trips found.")

if __name__ == "__main__":
    analyze()
