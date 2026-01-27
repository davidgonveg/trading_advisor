import pandas as pd
import numpy as np
from typing import List, Dict, Any
from backtesting.core.schema import Trade, OrderSide

class MetricsCalculator:
    @staticmethod
    def calculate_metrics(trades: List[Trade], equity_df: pd.DataFrame, initial_capital: float) -> Dict[str, Any]:
        if equity_df.empty:
            return {}
            
        final_equity = equity_df['total_equity'].iloc[-1]
        total_return_pct = (final_equity / initial_capital - 1) * 100
        
        # Returns
        equity_df['returns'] = equity_df['total_equity'].pct_change()
        
        # Drawdown
        equity_df['cum_max'] = equity_df['total_equity'].cummax()
        equity_df['drawdown'] = (equity_df['total_equity'] / equity_df['cum_max'] - 1)
        max_drawdown = equity_df['drawdown'].min() * 100
        
        # Sharpe (Daily approximation if data is sub-daily, ideally annualize properly)
        std = equity_df['returns'].std()
        sharpe = (equity_df['returns'].mean() / std * np.sqrt(252)) if std != 0 else 0
        
        # FIFO Trade Matching (Handles Long and Short)
        trade_results = [] # List of (pnl, side)
        running_qty = 0.0
        open_slots = [] # List of [qty, price, comm_unit]
        
        for t in trades:
            side_multiplier = 1 if t.side == OrderSide.BUY else -1
            
            # Check if this trade opens/adds or closes/reduces position
            is_opening = False
            if abs(running_qty) < 1e-6:
                is_opening = True
            elif running_qty > 0 and t.side == OrderSide.BUY:
                is_opening = True
            elif running_qty < 0 and t.side == OrderSide.SELL:
                is_opening = True
                
            if is_opening:
                # Opening/Adding to position
                open_slots.append([t.quantity, t.price, t.commission / t.quantity])
                running_qty += t.quantity * side_multiplier
            else:
                # Closing/Reducing position
                qty_to_close = t.quantity
                exit_price = t.price
                exit_comm_unit = t.commission / t.quantity
                
                while qty_to_close > 1e-6 and open_slots:
                    slot = open_slots[0]
                    closed_qty = min(qty_to_close, slot[0])
                    
                    entry_price = slot[1]
                    entry_comm_unit = slot[2]
                    
                    # P&L Calculation:
                    if running_qty > 0: # We were LONG
                        pnl = (exit_price - entry_price) * closed_qty
                        side = "LONG"
                    else: # We were SHORT
                        pnl = (entry_price - exit_price) * closed_qty
                        side = "SHORT"
                        
                    # Subtract BOTH commissions
                    pnl -= (entry_comm_unit * closed_qty) + (exit_comm_unit * closed_qty)
                    trade_results.append((pnl, side))
                    
                    slot[0] -= closed_qty
                    qty_to_close -= closed_qty
                    if slot[0] <= 1e-6:
                        open_slots.pop(0)
                
                # Update running qty
                running_qty += t.quantity * side_multiplier
                
                # Handle reversal
                if qty_to_close > 1e-6:
                    open_slots.append([qty_to_close, exit_price, exit_comm_unit])
        
        def get_summary(results: List[tuple]):
            pnls = [r[0] for r in results]
            wins = [r for r in pnls if r > 0]
            losses = [r for r in pnls if r <= 0]
            
            win_rate = (len(wins) / len(pnls)) * 100 if pnls else 0
            profit_factor = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float('inf')
            
            return {
                "Total Trades": len(pnls),
                "Win Rate %": round(win_rate, 2),
                "Profit Factor": round(profit_factor, 2) if profit_factor != float('inf') else "N/A",
                "Total P&L": round(sum(pnls), 2)
            }

        long_trades = [r for r in trade_results if r[1] == "LONG"]
        short_trades = [r for r in trade_results if r[1] == "SHORT"]
        
        overall_pnls = [r[0] for r in trade_results]
        overall_wins = [r for r in overall_pnls if r > 0]
        overall_losses = [r for r in overall_pnls if r <= 0]
        overall_win_rate = (len(overall_wins) / len(overall_pnls)) * 100 if overall_pnls else 0
        overall_pf = (sum(overall_wins) / abs(sum(overall_losses))) if overall_losses and sum(overall_losses) != 0 else float('inf')

        return {
            "Total P&L %": round(total_return_pct, 2),
            "Final Equity": round(final_equity, 2),
            "Max Drawdown %": round(max_drawdown, 2),
            "Sharpe Ratio": round(sharpe, 2),
            "Total Trades": len(trade_results),
            "Win Rate %": round(overall_win_rate, 2),
            "Profit Factor": round(overall_pf, 2) if overall_pf != float('inf') else "N/A",
            "Long Performance": get_summary(long_trades),
            "Short Performance": get_summary(short_trades)
        }
