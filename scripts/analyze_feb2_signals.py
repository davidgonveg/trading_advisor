"""
Analyze signals detected on 2026-02-02 in the backtest audit logs.
"""
import json
import sys

def analyze_signals(audit_file, symbol):
    """Analyze signals for a specific date in audit log."""
    with open(audit_file, 'r') as f:
        data = json.load(f)
    
    # Filter bars for 2026-02-02
    target_date = '2026-02-02'
    feb2_bars = [b for b in data['bars'] if target_date in b['timestamp']]
    
    print(f"\n{'='*80}")
    print(f"Analysis for {symbol} on {target_date}")
    print(f"{'='*80}")
    print(f"Total bars on {target_date}: {len(feb2_bars)}")
    
    # Find signals
    signals = [b for b in feb2_bars if b.get('signal') != 'HOLD']
    print(f"Signals detected: {len(signals)}")
    
    # Find trades
    trades_executed = []
    for bar in feb2_bars:
        if 'trades' in bar and bar['trades']:
            trades_executed.extend(bar['trades'])
    
    print(f"Trades executed: {len(trades_executed)}")
    
    # Show signal details
    if signals:
        print(f"\n{'='*80}")
        print("SIGNAL DETAILS:")
        print(f"{'='*80}")
        for sig in signals:
            print(f"\nTimestamp: {sig['timestamp']}")
            print(f"Signal: {sig['signal']}")
            print(f"OHLC: O={sig['ohlc']['Open']:.2f}, H={sig['ohlc']['High']:.2f}, "
                  f"L={sig['ohlc']['Low']:.2f}, C={sig['ohlc']['Close']:.2f}")
            
            # Check for rejection reasons
            if 'rejection_reason' in sig:
                print(f"❌ REJECTION REASON: {sig['rejection_reason']}")
            
            # Check portfolio state
            if 'portfolio_before' in sig:
                port = sig['portfolio_before']
                print(f"Cash before: ${port['cash']:.2f}")
                print(f"Open trades: {len(port.get('open_trades', []))}")
            
            # Check if orders were submitted
            if 'orders_submitted' in sig:
                print(f"Orders submitted: {len(sig['orders_submitted'])}")
                for order in sig['orders_submitted']:
                    print(f"  - {order}")
            else:
                print("⚠️  NO ORDERS SUBMITTED")
            
            # Check indicators
            if 'indicators' in sig:
                ind = sig['indicators']
                print(f"Indicators: VWAP={ind.get('VWAP', 'N/A')}, ATR={ind.get('ATR', 'N/A')}, "
                      f"RSI={ind.get('RSI', 'N/A')}")
    
    # Show trade details
    if trades_executed:
        print(f"\n{'='*80}")
        print("TRADES EXECUTED:")
        print(f"{'='*80}")
        for trade in trades_executed:
            print(f"\n{trade}")
    
    return signals, trades_executed

if __name__ == "__main__":
    # Analyze GLD
    gld_signals, gld_trades = analyze_signals(
        'backtesting/logs/audit_GLD_VWAPBounce_20260203_195307.json',
        'GLD'
    )
    
    # Analyze XLK
    xlk_signals, xlk_trades = analyze_signals(
        'backtesting/logs/audit_XLK_VWAPBounce_20260203_195307.json',
        'XLK'
    )
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"GLD: {len(gld_signals)} signals, {len(gld_trades)} trades")
    print(f"XLK: {len(xlk_signals)} signals, {len(xlk_trades)} trades")
    print(f"\n⚠️  Discrepancy: Signals detected but trades not executed!")
