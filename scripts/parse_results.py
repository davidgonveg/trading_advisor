import json
import glob
import pandas as pd
import os

def main():
    # Find all audit files from the latest run
    # timestamp was roughly 20260202_163339
    pattern = "backtesting/logs/audit_*_20260202_*.json"
    files = glob.glob(pattern)
    # Sort by modification time (newest first)
    files.sort(key=os.path.getmtime, reverse=True)
    # Keep top 8 (assuming 8 symbols)
    files = files[:8]
    
    summary = []
    print(f"Found {len(files)} audit files.")
    
    for fpath in files:
        try:
            with open(fpath, 'r') as f:
                data = json.load(f)
                
            # Metrics are usually in 'sub-fields' or we can calculate them if missing.
            # But main.py says: results['audit'].save(metrics)
            # Let's check if metrics are in the root of the JSON or appended.
            # Usually AuditTrail.save dumps the whole thing.
            # Let's look for known keys.
            
            m = data.get('final_metrics', {})
            if not m:
                print(f"No metrics found in {fpath}")
                continue
                
            summary.append({
                "Symbol": data.get('metadata', {}).get('symbol', 'Unknown'),
                "P&L %": f"{m.get('Total P&L %', 0):+,.2f}%",
                "Win Rate": f"{m.get('Win Rate %', 0):.1f}%",
                "Sharpe": m.get("Sharpe Ratio", 0),
                "MaxDD": f"{m.get('Max Drawdown %', 0):.1f}%",
                "Trades": m.get("Total Trades", 0),
                "Profit Factor": m.get("Profit Factor", 0)
            })
        except Exception as e:
            print(f"Error parsing {fpath}: {e}")

    output_path = "backtesting/verification_results.txt"
    if summary:
        df = pd.DataFrame(summary).sort_values(by='Symbol')
        with open(output_path, "w") as f:
            f.write("RECONSTRUCTED SUMMARY:\n")
            f.write(df.to_string(index=False))
        print(f"Summary written to {output_path}")
    else:
        print("No summary could be generated.")

if __name__ == "__main__":
    main()
