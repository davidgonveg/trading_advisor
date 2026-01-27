import json
import glob
import os
import pandas as pd

def parse_audit(filename):
    with open(filename, 'r') as f:
        data = json.load(f)
        return data.get('final_metrics', {})

def main():
    ts = "20260127_193033"
    base_files = glob.glob(f"backtesting/logs/audit_*_{ts}_BASE.json")
    
    results = []
    for base_file in base_files:
        symbol = os.path.basename(base_file).split('_')[1]
        ml_file = base_file.replace("_BASE.json", "_ML.json")
        
        if not os.path.exists(ml_file):
            continue
            
        m_base = parse_audit(base_file)
        m_ml = parse_audit(ml_file)
        
        pnl_base = m_base.get('Total P&L %', 0)
        pnl_ml = m_ml.get('Total P&L %', 0)
        wr_base = m_base.get('Win Rate %', 0)
        wr_ml = m_ml.get('Win Rate %', 0)
        tr_base = m_base.get('Total Trades', 0)
        tr_ml = m_ml.get('Total Trades', 0)
        
        results.append({
            "Symbol": symbol,
            "Trades(B)": tr_base,
            "Trades(ML)": tr_ml,
            "Reduc": f"{(tr_base-tr_ml)/tr_base*100:.1f}%" if tr_base > 0 else "0%",
            "WR(B)": f"{wr_base:.1f}%",
            "WR(ML)": f"{wr_ml:.1f}%",
            "WR +/-": f"{wr_ml-wr_base:+.1f}%",
            "PNL(B)": f"{pnl_base:+.2f}%",
            "PNL(ML)": f"{pnl_ml:+.2f}%",
            "PNL +/-": f"{pnl_ml-pnl_base:+.2f}%"
        })

    if results:
        df = pd.DataFrame(results).sort_values(by="Symbol")
        print(df.to_markdown(index=False))
        
        # Averages
        avg_wr_base = df["WR(B)"].str.replace('%','').astype(float).mean()
        avg_wr_ml = df["WR(ML)"].str.replace('%','').astype(float).mean()
        avg_pnl_base = df["PNL(B)"].str.replace('%','').astype(float).mean()
        avg_pnl_ml = df["PNL(ML)"].str.replace('%','').astype(float).mean()
        
        print(f"\nAverage Win Rate: {avg_wr_base:.1f}% -> {avg_wr_ml:.1f}% ({avg_wr_ml - avg_wr_base:+.1f}%)")
        print(f"Average P&L:      {avg_pnl_base:.2f}% -> {avg_pnl_ml:.2f}% ({avg_pnl_ml - avg_pnl_base:+.2f}%)")
    else:
        print("No matching BASE/ML files found.")

if __name__ == "__main__":
    main()
