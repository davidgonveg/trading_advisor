#!/usr/bin/env python3
"""
⚙️ BACKTESTING CONFIGURATION
============================

Configuración específica para el sistema de backtesting.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

@dataclass
class BacktestConfig:
    """Configuración completa del backtesting"""

    # ========== CAPITAL Y RIESGO ==========
    initial_capital: float = 10000.0  # Capital inicial en USD
    risk_per_trade: float = 1.5       # % del capital a arriesgar por trade
    max_concurrent_positions: int = 5  # Máximo de posiciones simultáneas

    # ========== COMISIONES Y SLIPPAGE ==========
    commission_per_share: float = 0.005  # Comisión por acción ($)
    commission_percentage: float = 0.0   # Comisión porcentual (si aplica)
    min_commission: float = 1.0          # Comisión mínima por trade

    # Slippage (se calcula dinámicamente, estos son defaults)
    base_slippage_pct: float = 0.05      # 0.05% base
    max_slippage_pct: float = 0.2        # 0.2% máximo

    # ========== PERÍODO DE BACKTESTING ==========
    start_date: Optional[datetime] = None  # None = usar todos los datos disponibles
    end_date: Optional[datetime] = None    # None = hasta el último dato

    # ========== SÍMBOLOS ==========
    symbols: List[str] = field(default_factory=lambda: [
        "^GSPC", "^NDX", "AAPL", "MSFT", "GOOGL", "NVDA", "TSLA", "META", "AMZN"
    ])

    # ========== VALIDACIÓN DE DATOS ==========
    min_data_quality_score: float = 70.0  # Score mínimo para considerar datos válidos
    max_gap_hours: float = 24.0           # Gap máximo permitido en horas
    require_complete_indicators: bool = True  # Requiere todos los indicadores

    # ========== COMPORTAMIENTO DEL SISTEMA ==========
    use_real_scanner: bool = True         # Usar scanner real (no mock)
    use_real_position_calc: bool = True   # Usar position calculator real
    use_real_exit_manager: bool = True    # Usar exit manager real

    # ========== ENTRADAS ESCALONADAS ==========
    # (se toma del sistema real, pero se puede override)
    entry_distribution: Dict[str, float] = field(default_factory=lambda: {
        'ENTRY_1': 40.0,  # 40% primera entrada
        'ENTRY_2': 30.0,  # 30% segunda entrada
        'ENTRY_3': 30.0,  # 30% tercera entrada
    })

    # ========== SALIDAS ESCALONADAS ==========
    exit_distribution: Dict[str, float] = field(default_factory=lambda: {
        'TP1': 25.0,  # 25% en TP1
        'TP2': 25.0,  # 25% en TP2
        'TP3': 25.0,  # 25% en TP3
        'TP4': 25.0,  # 25% en TP4 (trailing)
    })

    # ========== STOP LOSS ==========
    use_trailing_stop: bool = True        # Usar trailing stop en TP4
    trailing_stop_activation: float = 3.0  # Activar trailing tras 3R
    trailing_stop_distance_atr: float = 1.0  # Distancia del trailing (ATR)

    # ========== EXIT MANAGER ==========
    enable_exit_manager: bool = True      # Activar exit manager
    exit_manager_deterioration_threshold: int = 70  # Umbral de deterioro

    # ========== FILTROS DE SEÑALES ==========
    min_signal_strength: int = 55         # Puntuación mínima de señal
    min_entry_quality: str = "PARTIAL_ENTRY"  # Calidad mínima de entrada

    # ========== ANÁLISIS ==========
    calculate_sharpe_ratio: bool = True
    risk_free_rate: float = 0.02  # 2% anual

    # Análisis de indicadores
    analyze_indicator_importance: bool = True
    indicator_correlation_threshold: float = 0.3

    # ========== OUTPUT ==========
    save_trades_to_json: bool = True
    save_trades_to_excel: bool = True
    save_equity_curve: bool = True
    generate_html_report: bool = True

    output_dir: str = "backtesting/results"

    # ========== VERBOSIDAD ==========
    verbose: bool = True                  # Mostrar progreso
    log_level: str = "INFO"              # DEBUG, INFO, WARNING, ERROR
    print_trade_details: bool = False     # Imprimir cada trade (mucho output)

    # ========== MODO DE EJECUCIÓN ==========
    parallel_processing: bool = False     # Procesar símbolos en paralelo
    num_workers: int = 4                  # Número de workers si parallel=True

    # ========== VALIDACIÓN PREVIA ==========
    validate_data_before_backtest: bool = True
    skip_invalid_symbols: bool = True     # Saltar símbolos con datos malos

    def __post_init__(self):
        """Validar configuración"""
        # Validaciones básicas
        assert self.initial_capital > 0, "Capital inicial debe ser positivo"
        assert 0 < self.risk_per_trade <= 100, "Riesgo por trade debe estar entre 0 y 100%"
        assert self.max_concurrent_positions > 0, "Debe permitir al menos 1 posición"
        assert len(self.symbols) > 0, "Debe haber al menos un símbolo"

        # Validar distribuciones
        entry_sum = sum(self.entry_distribution.values())
        assert abs(entry_sum - 100.0) < 0.01, f"Entry distribution debe sumar 100%, suma {entry_sum}"

        exit_sum = sum(self.exit_distribution.values())
        assert abs(exit_sum - 100.0) < 0.01, f"Exit distribution debe sumar 100%, suma {exit_sum}"

        # Fechas
        if self.start_date and self.end_date:
            assert self.start_date < self.end_date, "Start date debe ser anterior a end date"

    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario para serialización"""
        return {
            'initial_capital': self.initial_capital,
            'risk_per_trade': self.risk_per_trade,
            'max_concurrent_positions': self.max_concurrent_positions,
            'commission_per_share': self.commission_per_share,
            'symbols': self.symbols,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'min_signal_strength': self.min_signal_strength,
            'min_entry_quality': self.min_entry_quality,
            'use_real_scanner': self.use_real_scanner,
            'use_real_position_calc': self.use_real_position_calc,
            'use_real_exit_manager': self.use_real_exit_manager,
            'enable_exit_manager': self.enable_exit_manager,
            'entry_distribution': self.entry_distribution,
            'exit_distribution': self.exit_distribution,
        }

    @classmethod
    def create_conservative(cls) -> 'BacktestConfig':
        """Crear configuración conservadora"""
        return cls(
            initial_capital=10000.0,
            risk_per_trade=1.0,  # Solo 1% de riesgo
            max_concurrent_positions=3,
            min_signal_strength=65,
            min_entry_quality="FULL_ENTRY",
        )

    @classmethod
    def create_aggressive(cls) -> 'BacktestConfig':
        """Crear configuración agresiva"""
        return cls(
            initial_capital=10000.0,
            risk_per_trade=2.5,  # 2.5% de riesgo
            max_concurrent_positions=7,
            min_signal_strength=55,
            min_entry_quality="PARTIAL_ENTRY",
        )

    @classmethod
    def create_single_symbol(cls, symbol: str) -> 'BacktestConfig':
        """Crear configuración para un solo símbolo"""
        return cls(
            symbols=[symbol],
            max_concurrent_positions=1,
        )


# Configuración por defecto
DEFAULT_CONFIG = BacktestConfig()


def get_default_config() -> BacktestConfig:
    """Obtener configuración por defecto"""
    return BacktestConfig()


def get_conservative_config() -> BacktestConfig:
    """Obtener configuración conservadora"""
    return BacktestConfig.create_conservative()


def get_aggressive_config() -> BacktestConfig:
    """Obtener configuración agresiva"""
    return BacktestConfig.create_aggressive()
