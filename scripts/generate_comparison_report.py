import json
import glob
import os
import pandas as pd
import logging

def parse_final_metrics(filename):
    """
    Optimized parser to extract 'final_metrics' from the end of a large JSON file
    without loading the entire file into memory.
    """
    try:
        with open(filename, 'rb') as f:
            # Seek to near the end of the file
            f.seek(0, os.SEEK_END)
            size = f.tell()
            # Read last 8KB, which should contain the final_metrics block
            chunk_size = min(size, 8192)
            f.seek(size - chunk_size)
            chunk = f.read().decode('utf-8', errors='ignore')
            
            # Find the start of final_metrics
            start_key = '"final_metrics":'
            if start_key in chunk:
                metrics_json = chunk[chunk.find(start_key) + len(start_key):].strip()
                # Remove trailing } and any whitespace
                if metrics_json.endswith('}'):
                    # The file ends with }} (one for metrics, one for root object)
                    # We want to parse until the end of the metrics object
                    depth = 0
                    actual_json = ""
                    for char in metrics_json:
                        actual_json += char
                        if char == '{': depth += 1
                        if char == '}': 
                            depth -= 1
                            if depth == 0: break
                    return json.loads(actual_json)
            
            # Fallback for small or weirdly formatted files
            f.seek(0)
            data = json.load(f)
            return data.get('final_metrics', {})
    except Exception as e:
        print(f"Error parsing {filename}: {e}")
        return {}

def main():
    # Use a dynamic way to find the latest timestamp if possible, 
    # but for now we look for files with _BASE.json and _ML.json
    base_files = glob.glob("backtesting/logs/audit_*_BASE.json")
    if not base_files:
        print("No matching BASE files found.")
        return

    # Group by timestamp (last part of filename before _BASE.json)
    # e.g. audit_XLK_VWAPBounce_20260128_112504_BASE.json -> 20260128_112504
    latest_ts = None
    timestamps = set()
    for f in base_files:
        parts = os.path.basename(f).split('_')
        if len(parts) >= 5:
            ts = f"{parts[-3]}_{parts[-2]}"
            timestamps.add(ts)
    
    if not timestamps:
        print("Could not extract timestamps from filenames.")
        return
        
    latest_ts = sorted(list(timestamps))[-1]
    print(f"Generating report for latest run: {latest_ts}")
    
    base_files = glob.glob(f"backtesting/logs/audit_*_{latest_ts}_BASE.json")
    
    results = []
    for base_file in base_files:
        symbol = os.path.basename(base_file).split('_')[1]
        ml_file = base_file.replace("_BASE.json", "_ML.json")
        
        if not os.path.exists(ml_file):
            continue
            
        m_base = parse_final_metrics(base_file)
        m_ml = parse_final_metrics(ml_file)
        
        if not m_base or not m_ml:
            continue
            
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
        print("No matching BASE/ML results could be parsed.")

if __name__ == "__main__":
    main()
