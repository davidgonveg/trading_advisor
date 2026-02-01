import glob
import os
import pandas as pd
import sys

def main():
    log_dir = "backtesting/logs"
    pattern = os.path.join(log_dir, "optimization_results_*.csv")
    files = glob.glob(pattern)
    
    if not files:
        print("No optimization results found.")
        return

    # Get latest file
    latest_file = max(files, key=os.path.getctime)
    print(f"Analyzing latest result: {latest_file}")
    
    df = pd.read_csv(latest_file)
    
    if df.empty:
        print("Dataset is empty.")
        return

    # Clean and Sort
    # Remove rows where P&L is NaN
    df = df.dropna(subset=["Total P&L %"])
    
    # Sort by Sharpe Ratio (or P&L)
    df_sorted = df.sort_values(by="Sharpe Ratio", ascending=False)
    
    print("\n--- TOP 10 CONFIGURATIONS (By Sharpe Ratio) ---")
    print(df_sorted.head(10).to_markdown(index=False))
    
    print("\n--- TOP 10 CONFIGURATIONS (By Total P&L) ---")
    df_pnl = df.sort_values(by="Total P&L %", ascending=False)
    print(df_pnl.head(10).to_markdown(index=False))
    
    # Parameter Correlations
    param_cols = [c for c in df.columns if c.startswith("p_")]
    metric_cols = ["Total P&L %", "Max Drawdown %", "Sharpe Ratio", "Win Rate %"]
    
    print("\n--- PARAMETER CORRELATIONS ---")
    correlations = df[param_cols + metric_cols].corr()
    print(correlations.loc[param_cols, metric_cols].to_markdown())

if __name__ == "__main__":
    main()
