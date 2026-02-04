"""Deep analysis of Feb 2 signals to find why trades weren't executed."""
import json

def analyze_signal_execution(filepath, symbol):
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    # Find Feb 2 bars with signals
    feb2_bars = [b for b in data['bars'] if '2026-02-02' in b['timestamp']]
    signals = [b for b in feb2_bars if b['signal'] not in ['HOLD', None]]
    
    print(f"\n{'='*80}")
    print(f"{symbol} - Detailed Signal Analysis for Feb 2, 2026")
    print(f"{'='*80}\n")
    
    for idx, sig in enumerate(signals, 1):
        print(f"Signal #{idx}")
        print(f"  Timestamp: {sig['timestamp']}")
        print(f"  Signal Type: {sig['signal']}")
        print(f"  OHLC: O={sig['ohlc']['Open']:.2f}, H={sig['ohlc']['High']:.2f}, "
              f"L={sig['ohlc']['Low']:.2f}, C={sig['ohlc']['Close']:.2f}")
        
        # Portfolio state
        port = sig['portfolio_before']
        print(f"\n  Portfolio Before Signal:")
        print(f"    Cash: ${port['cash']:.2f}")
        print(f"    Total Equity: ${port.get('total_equity', 0):.2f}")
        print(f"    Open Trades: {len(port.get('open_trades', []))}")
        print(f"    Positions: {port.get('positions', {})}")
        
        # Check for ML filter
        if 'ml_confidence' in sig:
            print(f"\n  ML Filter:")
            print(f"    Confidence: {sig['ml_confidence']:.4f}")
        
        # Check for rejection reasons
        if 'rejection_reason' in sig:
            print(f"\n  ❌ REJECTION: {sig['rejection_reason']}")
        
        # Check if orders were created (this might not be in audit log)
        if 'orders_submitted' in sig:
            print(f"\n  ✅ Orders Submitted: {len(sig['orders_submitted'])}")
        else:
            print(f"\n  ⚠️  NO ORDERS FIELD IN AUDIT LOG")
        
        # Check indicators
        if 'indicators' in sig:
            ind = sig['indicators']
            print(f"\n  Indicators:")
            print(f"    VWAP: {ind.get('VWAP', 'N/A')}")
            print(f"    ATR: {ind.get('ATR', 'N/A')}")
            print(f"    RSI: {ind.get('RSI', 'N/A')}")
            print(f"    Dist_EMA200: {ind.get('Dist_EMA200', 'N/A')}")
        
        print(f"\n{'-'*80}\n")
    
    # Check if there were any trades executed on Feb 2
    trades_on_feb2 = []
    for bar in feb2_bars:
        # Check if bar has trades field
        if 'trades' in bar and bar['trades']:
            trades_on_feb2.extend(bar['trades'])
    
    print(f"\n{'='*80}")
    print(f"TRADES EXECUTED ON FEB 2:")
    print(f"{'='*80}")
    print(f"Total: {len(trades_on_feb2)}")
    
    if trades_on_feb2:
        for trade in trades_on_feb2:
            print(f"\n{trade}")
    else:
        print("❌ NO TRADES EXECUTED ON FEB 2!")
    
    return signals, trades_on_feb2

# Analyze GLD
print("\n" + "="*80)
print("ANALYZING GLD")
print("="*80)
gld_signals, gld_trades = analyze_signal_execution(
    'backtesting/logs/audit_GLD_VWAPBounce_20260203_195307.json',
    'GLD'
)

# Analyze XLK
print("\n" + "="*80)
print("ANALYZING XLK")
print("="*80)
xlk_signals, xlk_trades = analyze_signal_execution(
    'backtesting/logs/audit_XLK_VWAPBounce_20260203_195307.json',
    'XLK'
)

# Final summary
print(f"\n{'='*80}")
print("FINAL SUMMARY")
print(f"{'='*80}")
print(f"GLD: {len(gld_signals)} signals detected, {len(gld_trades)} trades executed")
print(f"XLK: {len(xlk_signals)} signals detected, {len(xlk_trades)} trades executed")
print(f"\n🔍 ROOT CAUSE: Signals were detected but NO trades were executed!")
print(f"   This suggests the issue is in the _handle_signal() method or order submission.")
