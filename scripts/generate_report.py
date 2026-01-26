import pandas as pd
import sys
import os
import glob

def generate_report():
    print("Generating comprehensive backtest report...")
    results_dir = "backtesting/results"
    
    # Files
    trades_path = os.path.join(results_dir, "round_trips_detailed.csv")
    equity_path = os.path.join(results_dir, "equity.csv")
    report_path = os.path.join(results_dir, "report.md")
    
    if not os.path.exists(trades_path):
        print("❌ Detailed trades file not found.")
        return

    # Load Data
    df_trades = pd.read_csv(trades_path)
    df_equity = pd.read_csv(equity_path) if os.path.exists(equity_path) else pd.DataFrame()
    
    # --- METRICS CALCULATION ---
    total_trades = len(df_trades)
    wins = df_trades[df_trades['pnl_net'] > 0]
    losses = df_trades[df_trades['pnl_net'] <= 0]
    
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0
    total_pnl = df_trades['pnl_net'].sum()
    gross_pnl = df_trades['gross_pnl'].sum() if 'gross_pnl' in df_trades.columns else total_pnl
    total_comm = df_trades['commission'].sum() if 'commission' in df_trades.columns else 0.0
    
    avg_win = wins['pnl_net'].mean() if not wins.empty else 0
    avg_loss = losses['pnl_net'].mean() if not losses.empty else 0
    profit_factor = abs(wins['pnl_net'].sum() / losses['pnl_net'].sum()) if not losses.empty and losses['pnl_net'].sum() != 0 else float('inf')
    
    # Duration
    avg_duration = df_trades['duration_h'].mean()
    
    # Equity Stats
    initial_cap = 10000.0 # Standard
    final_equity = initial_cap + total_pnl
    if not df_equity.empty:
        final_equity = df_equity['equity'].iloc[-1]
        max_equity = df_equity['equity'].max()
        # Drawdown
        # Calculate running max
        run_max = df_equity['equity'].cummax()
        dd = (df_equity['equity'] - run_max) / run_max * 100
        max_dd = dd.min()
    else:
        max_dd = 0.0 # Unknown
    
    # --- MARKDOWN GENERATION ---
    lines = []
    lines.append("# Backtest Report: Mean Reversion Selectiva")
    lines.append(f"**Date:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n")
    
    lines.append("## 1. Performance Summary")
    lines.append("| Metric | Value | Code |")
    lines.append("| :--- | :--- | :--- |")
    lines.append(f"| **Final Equity** | **${final_equity:,.2f}** | `EQUITY` |")
    lines.append(f"| Total PnL | ${total_pnl:,.2f} | `PNL_NET` |")
    lines.append(f"| Max Drawdown | {max_dd:.2f}% | `MAX_DD` |")
    lines.append(f"| Win Rate | {win_rate:.1f}% | `WIN_RATE` |")
    lines.append(f"| Profit Factor | {profit_factor:.2f} | `PF` |")
    lines.append(f"| Total Trades | {total_trades} | `COUNT` |")
    lines.append(f"| Avg Trade Duration | {avg_duration:.1f} hours | `AVG_DUR` |")
    lines.append(f"| Returns | {((final_equity-initial_cap)/initial_cap)*100:.1f}% | `ROI` |")
    
    lines.append("\n## 2. Trade Statistics")
    lines.append(f"- **Wins**: {len(wins)} (Avg: ${avg_win:.2f})")
    lines.append(f"- **Losses**: {len(losses)} (Avg: ${avg_loss:.2f})")
    lines.append(f"- **Commissions**: ${total_comm:.2f}")
    
    # Breakout by Symbol
    lines.append("\n## 3. Performance by Symbol")
    lines.append("| Symbol | Trades | Win Rate | Net PnL | Avg PnL |")
    lines.append("| :--- | :--- | :--- | :--- | :--- |")
    
    by_symbol = df_trades.groupby('symbol')
    for sym, group in by_symbol:
        n = len(group)
        w = len(group[group['pnl_net'] > 0])
        wr = (w/n)*100
        pnl = group['pnl_net'].sum()
        avg = group['pnl_net'].mean()
        lines.append(f"| {sym} | {n} | {wr:.1f}% | ${pnl:.2f} | ${avg:.2f} |")
        
    lines.append("\n## 4. Exit Analysis")
    lines.append("Reason for exit (frequency):")
    counts = df_trades['exit_reason'].value_counts()
    for reason, count in counts.items():
        lines.append(f"- **{reason}**: {count}")

    lines.append("\n## 5. Recent Trades")
    lines.append("| Symbol | Dir | Entry Time | Exit Time | PnL | Reason |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    
    # Last 10 trades
    recent = df_trades.sort_values('exit_time', ascending=False).head(10)
    for idx, row in recent.iterrows():
        pnl_val = row['pnl_net']
        pnl_str = f"${pnl_val:.2f}"
        if pnl_val > 0: pnl_str = f"**{pnl_str}**"
        lines.append(f"| {row['symbol']} | {row['direction']} | {row['entry_time']} | {row['exit_time']} | {pnl_str} | {row['exit_reason']} |")

    # Write Report
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    print(f"✅ Report generated: {report_path}")
    print(f"Equity Curve points: {len(df_equity)}")

if __name__ == "__main__":
    generate_report()
