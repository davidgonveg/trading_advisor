import pandas as pd
import numpy as np

def check_csv():
    try:
        df = pd.read_csv("data/ml/training_data.csv")
        print(f"Total rows: {len(df)}")
        print("Feature Non-Zero Counts:")
        
        features = [c for c in df.columns if c not in ['symbol', 'strategy', 'timestamp', 'side', 'pnl', 'label']]
        
        for f in features:
            nz = np.count_nonzero(df[f])
            print(f"{f}: {nz} / {len(df)} ({nz/len(df)*100:.1f}%)")
            if nz > 0:
                print(f"  Sample: {df[f].iloc[100:105].values}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_csv()
