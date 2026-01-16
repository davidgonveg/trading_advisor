
import sys
import os
import pandas as pd
import numpy as np

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from analysis.indicators import TechnicalIndicators

def test_connors_rsi():
    ti = TechnicalIndicators()
    
    # Create synthetic data: 
    # Alternating up and down to check Streak
    data = [100, 101, 102, 103, 102, 101, 100, 99, 100, 102, 105, 110, 115, 110, 105]
    # Streaks:
    # 100 -> null
    # 101 (+) -> S=1
    # 102 (+) -> S=2
    # 103 (+) -> S=3
    # 102 (-) -> S=-1
    # 101 (-) -> S=-2
    # 100 (-) -> S=-3
    # 99 (-) -> S=-4
    # 100 (+) -> S=1
    # ...
    
    df = pd.DataFrame({'Close': data})
    
    # Calculate Streak manually
    s = ti.streak(df['Close'])
    print("Streaks:")
    print(s.values)
    
    # Check Logic
    # 100->NaN (0)
    # 101->1
    # 102->2
    # 103->3
    # 102->-1
    # 101->-2
    # 100->-3
    # 99->-4
    # 100->1
    
    expected_streaks = [0, 1, 2, 3, -1, -2, -3, -4, 1, 1, 1, 1, 1, -1, -1] # Rough logic check
    # My sequence: 
    # 100, 101(+), 102(+), 103(+), 102(-), 101(-), 100(-), 99(-), 100(+), 102(+), 105(+), 110(+), 115(+), 110(-), 105(-)
    # Streaks: 0, 1, 2, 3, -1, -2, -3, -4, 1, 2, 3, 4, 5, -1, -2
    
    # Let's see what code produces
    
    # CRSI
    # Should be between 0 and 100
    crsi = ti.connors_rsi(df['Close'], 3, 2, 10) # Short rank period for small data
    df['CRSI'] = crsi
    
    print("\nDataFrame with CRSI:")
    print(df)
    
    if (df['CRSI'].dropna() > 100).any() or (df['CRSI'].dropna() < 0).any():
        print("FAIL: CRSI out of bounds (0-100)")
    else:
        print("PASS: CRSI Bounds check")
        
    print("Done.")

if __name__ == "__main__":
    test_connors_rsi()
