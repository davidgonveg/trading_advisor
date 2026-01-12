# Script to verify P&L calculations

trades_pnl = [
    92.75,   # Trade #1
    92.99,   # Trade #2
    720.32,  # Trade #3
    631.84,  # Trade #4
    620.88,  # Trade #5
    543.98,  # Trade #6
    616.03,  # Trade #7
    690.54,  # Trade #8
    594.38,  # Trade #9
    628.72,  # Trade #10
    626.51,  # Trade #11
    694.54,  # Trade #12
    643.56,  # Trade #13
    760.28,  # Trade #14
    709.81,  # Trade #15
    652.59,  # Trade #16
    664.28,  # Trade #17
    1849.59, # Trade #18
    1688.12, # Trade #19
    1703.78, # Trade #20
]

total_pnl_from_trades = sum(trades_pnl)
print(f"Suma de P&L de todos los trades: {total_pnl_from_trades:.2f} EUR")

initial_capital = 10000
final_equity_reported = 250068.14
unrealized_pnl = -132689.66

print(f"\nCapital inicial: {initial_capital:.2f} EUR")
print(f"Equity final reportado: {final_equity_reported:.2f} EUR")
print(f"Unrealized P&L: {unrealized_pnl:.2f} EUR")

# Cálculo esperado
expected_equity = initial_capital + total_pnl_from_trades + unrealized_pnl
print(f"\nEquity esperado (inicial + trades + unrealized): {expected_equity:.2f} EUR")

# Diferencia
difference = final_equity_reported - expected_equity
print(f"Diferencia: {difference:.2f} EUR")

# Análisis
print(f"\n{'='*60}")
print("ANÁLISIS:")
print(f"{'='*60}")

# Si restamos el unrealized del equity final, ¿cuál es el balance realizado?
realized_balance = final_equity_reported - unrealized_pnl
print(f"Balance realizado (equity - unrealized): {realized_balance:.2f} EUR")
print(f"Diferencia con capital inicial: {realized_balance - initial_capital:.2f} EUR")
print(f"Diferencia con suma de trades: {realized_balance - initial_capital - total_pnl_from_trades:.2f} EUR")
