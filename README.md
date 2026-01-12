# Smart Trading Advisor (Rebuild V4)

A modular, automated trading system designed for the US Stock Market, specifically aligned with the **Mean Reversion Selectiva** strategy. It focuses on data integrity (gap handling), extended hours trading, and robust signal generation for Tier 1 ETFs (SPY, QQQ, IWM).

## 🏗️ Architecture "Rebuild V4"

This project has been rebuilt from scratch to improve maintainability, scalability, and data reliability.

```
project_root/
├── config/           # Centralized configuration (settings.py)
├── core/             # Core utilities (logger.py)
├── data/             # Data Layer (Robust & Gap-Free)
│   ├── providers/    # API clients (YFinance, TwelveData) with Failover
│   ├── storage/      # SQLite Database (trading.db)
│   └── quality/      # Data Quality Engine (Gap Detection & Repair)
├── analysis/         # Analysis Layer
│   └── indicators.py # Technical Analysis (RSI, BB, ADX, VWAP, ATR)
├── scripts/          # Operational Scripts (Backfill, Deployment)
├── legacy_v3/        # Archived previous version
└── tests/            # Unit and Integration tests
```

## 🚀 Status (Jan 11, 2026)

### ✅ Completed Modules

1.  **Foundation**:
    *   Modular stucture with centralized `config` and `core` logging.
    *   Virtual environment `trading_env` standardized.

2.  **Data Layer (Phase 2)**:
    *   **Providers**: implemented `YFinanceProvider` and `TwelveDataProvider` with a `DataProviderFactory` that handles failover automatically.
    *   **Storage**: SQLite database (`data/storage/trading.db`) storing `market_data` (OHLCV) and `indicators`.
    *   **Data Quality**:
        *   `GapDetector`: Identifies data gaps (Small, Overnight, Weekend).
        *   `GapRepair`: Fills gaps using interpolation (small) or forward-fill/fetch (large) to ensure continuous data streams required for backtesting.
        *   `ContinuousCollector`: Service for real-time data ingestion and repair.

3.  **Analysis Layer (Phase 3)**:
    *   **Indicators**: Implemented specialized `analysis/indicators.py` supporting:
        *   RSI, Bollinger Bands, ADX, ATR, VWAP.
        *   Dual-mode calculation (Pandas or TA-Lib).
    *   **Scanner**: Implemented `analysis/scanner.py` with full "Mean Reversion Selectiva" logic.
    *   **Patterns**: Candle pattern recognition (`analysis/patterns.py`).
    *   **Multi-Timeframe Logic**: Verified Daily SMA50 merging.

4.  **Execution Layer (Phase 4)**:
    *   **Risk**: `analysis/risk.py` for ATR-based position sizing.
    *   **Trade Manager**: `trading/manager.py` converts Signals to Plans (Entries, TPs, SL).
    *   **Alerts**: `alerts/telegram.py` for real-time notifications.

5.  **Strategy Alignment**:
    *   Universe restricted to strategy requirements: `SPY`, `QQQ`, `IWM`, `XLF`, `XLE`, `XLK`, `SMH`, `GLD`, `TLT`, `EEM`.
    *   Timeframes: 1H (Trading) + 1D (Trend Filter).

### ⏳ In Progress

*   **Backtesting**: Calibration of scanner sensitivity.
*   **Execution Database**: Persisting Trade Plans to `trades` table.

## 🛠️ Operational Scripts

*   `python scripts/backfill_data.py`: Fetches max history (730 days 1H, 5yr 1D).
*   `python scripts/verify_data_integrity.py`: Audits data ranges and quality.
*   `python scripts/calculate_history.py`: Populates `trading.db` with indicators.
*   `python scripts/test_scanner.py`: Runs the scanner logic on historical data.
*   `python scripts/test_trade_manager.py`: Verifies position sizing and order generation.

## 💾 Database Schema

*   **market_data**: `symbol`, `timeframe`, `timestamp`, `open`, `high`, `low`, `close`, `volume`, `is_filled`.
*   **indicators**: `rsi`, `bb_upper`, `bb_middle`, `bb_lower`, `adx`, `atr`, `vwap`, `sma_50` (Daily/Hourly mixed), `volume_sma_20`.

## 🧪 Testing

Run the test suite to verify integrity:
```bash
python -m unittest discover tests
```
