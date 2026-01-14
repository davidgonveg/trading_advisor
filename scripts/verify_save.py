
import pandas as pd
from unittest.mock import MagicMock
import sys
from pathlib import Path

# Setup Path
sys.path.append(str(Path.cwd()))

from data.storage.database import Database

def verify_save_logic():
    # Mock DB
    db = MagicMock()
    
    # Create fake large DF
    dates = pd.date_range("2024-01-01", periods=1000, freq="1h")
    df_analyzed = pd.DataFrame(index=dates, data={"RSI": range(1000)})
    
    # Simulate logic from main.py
    rows_to_save = df_analyzed.iloc[-48:] 
    db.save_indicators("TEST", "1h", rows_to_save)
    
    # Verify
    call_args = db.save_indicators.call_args
    saved_df = call_args[0][2]
    
    print(f"Original DF Size: {len(df_analyzed)}")
    print(f"Saved DF Size: {len(saved_df)}")
    
    if len(saved_df) == 48:
        print("SUCCESS: Only 48 rows saved.")
    else:
        print(f"FAILURE: {len(saved_df)} rows saved.")

if __name__ == "__main__":
    verify_save_logic()
