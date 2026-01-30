import pandas as pd

def check_stats():
    df = pd.read_csv("data/ml/training_data.csv")
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    
    # Filter 2025
    df_2025 = df[df['timestamp'].dt.year == 2025]
    
    if df_2025.empty:
        print("No data for 2025!")
        return
        
    total = len(df_2025)
    ones = len(df_2025[df_2025['label'] == 1])
    zeros = len(df_2025[df_2025['label'] == 0])
    
    print(f"--- 2025 Statistics ---")
    print(f"Total Samples: {total}")
    print(f"Label 1: {ones} ({ones/total*100:.2f}%)")
    print(f"Label 0: {zeros} ({zeros/total*100:.2f}%)")
    
    # Check QQQ specifically
    qqq = df_2025[df_2025['symbol'] == 'QQQ']
    if not qqq.empty:
        q_total = len(qqq)
        q_ones = len(qqq[qqq['label'] == 1])
        print(f"\n--- QQQ 2025 ---")
        print(f"Total: {q_total}")
        print(f"Label 1: {q_ones} ({q_ones/q_total*100:.2f}%)")

if __name__ == "__main__":
    check_stats()
