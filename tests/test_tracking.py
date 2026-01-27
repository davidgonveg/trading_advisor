
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd

# Setup Path
sys.path.append(str(Path(__file__).parent))

from data.storage.database import Database
from trading.manager import TradeManager
from data.manager import DataManager

def test_position_tracking():
    db = Database()
    trade_mgr = TradeManager()
    data_mgr = DataManager()
    
    symbol = "BTC-USD" # Example symbol
    
    print("--- MOCK TEST: Position Tracking ---")
    
    # 1. Manually insert a mock alert if none exist
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM alerts WHERE symbol = ?", (symbol,))
    cursor.execute("DELETE FROM alert_performance WHERE alert_id IN (SELECT id FROM alerts WHERE symbol = ?)", (symbol,))
    
    cursor.execute('''
        INSERT INTO alerts (timestamp, symbol, signal_type, price, sl_price, tp1_price, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (datetime.now().isoformat(), symbol, 'LONG', 50000.0, 49000.0, 52000.0, 'SENT'))
    conn.commit()
    conn.close()
    
    print(f"Inserted mock alert for {symbol} @ 50000.0")
    
    # 2. Simulate monitoring with different price scenarios
    active_alerts = db.get_active_alerts()
    print(f"Active alerts found: {len(active_alerts)}")
    
    for alert in active_alerts:
        # Scenario A: Worsening Conditions (Price below VWAP)
        # We'll mock the DF that is normally returned by data_mgr.get_latest_data
        mock_df = pd.DataFrame([
            {'Close': 49500.0, 'VWAP': 49800.0}
        ], index=[datetime.now()])
        
        print(f"Testing Scenario: Early Exit (Price {mock_df.iloc[-1]['Close']} < VWAP {mock_df.iloc[-1]['VWAP']})")
        trade_mgr.check_exit_conditions(alert, mock_df.iloc[-1]['Close'], mock_df.index[-1], mock_df)
        
    # 3. Check DB results
    performance = db.get_active_alerts()
    print(f"Active alerts after test (should be 0 if closed): {len(performance)}")
    
    report = trade_mgr.generate_performance_report()
    print("\nGenerated Report Preview:")
    print(report)

if __name__ == "__main__":
    test_position_tracking()
