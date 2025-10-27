#!/usr/bin/env python3
"""
🚀 RUN BACKTEST - Script Principal de Ejecución
==============================================

Script principal para ejecutar backtesting con análisis completo.

Uso:
    python backtesting/run_backtest.py                    # Backtesting completo
    python backtesting/run_backtest.py --symbol AAPL      # Solo AAPL
    python backtesting/run_backtest.py --conservative     # Modo conservador
    python backtesting/run_backtest.py --aggressive       # Modo agresivo
"""

import logging
import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Añadir path del proyecto
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backtesting.config import BacktestConfig
from backtesting.backtest_engine import BacktestEngine
from backtesting.performance_analyzer import PerformanceAnalyzer
from backtesting.indicator_analyzer import IndicatorAnalyzer
from backtesting.report_generator import ReportGenerator

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backtesting/results/backtest.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Función principal"""
    parser = argparse.ArgumentParser(
        description='🔙 Sistema de Backtesting - Trading Advisor',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python backtesting/run_backtest.py                    # Backtesting completo
  python backtesting/run_backtest.py --symbol AAPL      # Solo AAPL
  python backtesting/run_backtest.py --conservative     # Modo conservador
  python backtesting/run_backtest.py --aggressive       # Modo agresivo
  python backtesting/run_backtest.py --days 60          # Últimos 60 días
        """
    )

    parser.add_argument('--symbol', type=str, help='Símbolo específico (ej: AAPL)')
    parser.add_argument('--conservative', action='store_true', help='Modo conservador')
    parser.add_argument('--aggressive', action='store_true', help='Modo agresivo')
    parser.add_argument('--days', type=int, help='Días hacia atrás (ej: 60)')
    parser.add_argument('--capital', type=float, default=10000.0, help='Capital inicial')
    parser.add_argument('--risk', type=float, help='Riesgo por trade (%)')
    parser.add_argument('--min-signal', type=int, help='Señal mínima (55-100)')
    parser.add_argument('--no-validate', action='store_true', help='Saltar validación de datos')
    parser.add_argument('--no-exit-manager', action='store_true', help='Desactivar exit manager')

    args = parser.parse_args()

    try:
        print("=" * 70)
        print("🚀 SISTEMA DE BACKTESTING - TRADING ADVISOR")
        print("=" * 70)
        print(f"⏰ Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # 1. Crear configuración
        if args.conservative:
            config = BacktestConfig.create_conservative()
            logger.info("📊 Modo: CONSERVADOR")
        elif args.aggressive:
            config = BacktestConfig.create_aggressive()
            logger.info("📊 Modo: AGRESIVO")
        elif args.symbol:
            config = BacktestConfig.create_single_symbol(args.symbol)
            logger.info(f"📊 Modo: SÍMBOLO ÚNICO ({args.symbol})")
        else:
            config = BacktestConfig()
            logger.info("📊 Modo: NORMAL")

        # Aplicar overrides de argumentos
        if args.capital:
            config.initial_capital = args.capital

        if args.risk:
            config.risk_per_trade = args.risk

        if args.min_signal:
            config.min_signal_strength = args.min_signal

        if args.no_validate:
            config.validate_data_before_backtest = False

        if args.no_exit_manager:
            config.enable_exit_manager = False

        # Período
        if args.days:
            config.end_date = datetime.now()
            config.start_date = config.end_date - timedelta(days=args.days)
            logger.info(f"📅 Período: últimos {args.days} días")

        logger.info(f"💰 Capital inicial: ${config.initial_capital:,.2f}")
        logger.info(f"🎯 Riesgo por trade: {config.risk_per_trade}%")
        logger.info(f"📊 Símbolos: {len(config.symbols)}")
        logger.info(f"🔍 Señal mínima: {config.min_signal_strength} pts")

        # 2. Ejecutar backtesting
        logger.info("\n" + "=" * 70)
        logger.info("🔄 Ejecutando backtesting...")
        logger.info("=" * 70 + "\n")

        engine = BacktestEngine(config)
        results = engine.run()

        if 'error' in results:
            logger.error(f"❌ Error en backtesting: {results['error']}")
            return 1

        # 3. Análisis adicional
        logger.info("\n" + "=" * 70)
        logger.info("📊 Análisis de rendimiento...")
        logger.info("=" * 70 + "\n")

        perf_analyzer = PerformanceAnalyzer()
        ind_analyzer = IndicatorAnalyzer()

        # Análisis por símbolo
        symbol_performance = perf_analyzer.analyze_by_symbol(results['trades'])
        if symbol_performance:
            print("\n📈 RENDIMIENTO POR SÍMBOLO:")
            print("-" * 70)
            for symbol, metrics in symbol_performance.items():
                print(f"\n{symbol}:")
                print(f"  Trades: {metrics['total_trades']} | Win Rate: {metrics['win_rate']:.1f}%")
                print(f"  P&L: ${metrics['total_pnl']:.2f} | PF: {metrics['profit_factor']:.2f}")

        # Análisis LONG vs SHORT
        long_short = perf_analyzer.analyze_long_vs_short(results['trades'])
        if long_short:
            print("\n📊 LONG vs SHORT:")
            print("-" * 70)
            for direction, metrics in long_short.items():
                print(f"\n{direction}:")
                print(f"  Trades: {metrics['total_trades']} | Win Rate: {metrics['win_rate']:.1f}%")
                print(f"  P&L: ${metrics['total_pnl']:.2f} | PF: {metrics['profit_factor']:.2f}")

        # Análisis por fuerza de señal
        signal_perf = perf_analyzer.analyze_signal_strength_performance(results['trades'])
        if signal_perf:
            print("\n🎯 RENDIMIENTO POR FUERZA DE SEÑAL:")
            print("-" * 70)
            for range_name, metrics in signal_perf.items():
                print(f"\n{range_name}: {metrics['count']} trades")
                print(f"  Win Rate: {metrics['win_rate']:.1f}% | Avg P&L: ${metrics['avg_pnl']:.2f}")

        # 4. Generar reportes
        logger.info("\n" + "=" * 70)
        logger.info("📝 Generando reportes...")
        logger.info("=" * 70 + "\n")

        # Añadir análisis a results
        results['performance_analysis'] = {
            'by_symbol': symbol_performance,
            'long_vs_short': long_short,
            'by_signal_strength': signal_perf,
        }

        report_gen = ReportGenerator()
        report_files = report_gen.generate_all_reports(results)

        print("\n📄 REPORTES GENERADOS:")
        print("-" * 70)
        for report_type, filepath in report_files.items():
            if filepath:
                print(f"  {report_type}: {filepath}")

        # 5. Resumen final
        print("\n" + "=" * 70)
        print("✅ BACKTESTING COMPLETADO")
        print("=" * 70)
        print(f"⏰ Fin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📂 Reportes en: backtesting/results/")
        print("=" * 70 + "\n")

        return 0

    except KeyboardInterrupt:
        print("\n\n⏸️  Backtesting interrumpido por el usuario")
        return 130

    except Exception as e:
        logger.error(f"❌ Error fatal: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
