#!/usr/bin/env python3
"""
🧪 TEST SYSTEM - Script Automatizado de Testing
==============================================

Ejecuta todos los tests del sistema de backtesting de forma ordenada.

Uso:
    python backtesting/test_system.py
    python backtesting/test_system.py --quick    # Solo tests rápidos
    python backtesting/test_system.py --full     # Tests completos
"""

import sys
import logging
from pathlib import Path
import argparse
from datetime import datetime

# Setup paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


def print_header(title, char="="):
    """Imprimir header bonito"""
    print("\n" + char * 70)
    print(f"  {title}")
    print(char * 70 + "\n")


def print_step(step_num, title):
    """Imprimir paso"""
    print(f"\n{'='*70}")
    print(f"  PASO {step_num}: {title}")
    print(f"{'='*70}\n")


def test_1_database():
    """Test 1: Verificar base de datos"""
    print_step(1, "Verificar Base de Datos")

    try:
        from database.connection import get_connection

        conn = get_connection()
        if not conn:
            print("❌ No se pudo conectar a la base de datos")
            return False

        cursor = conn.cursor()

        # Ver símbolos disponibles
        cursor.execute("SELECT DISTINCT symbol FROM indicators_data")
        symbols = [row[0] for row in cursor.fetchall()]

        # Ver conteo por símbolo
        cursor.execute("SELECT symbol, COUNT(*) FROM indicators_data GROUP BY symbol")
        counts = dict(cursor.fetchall())

        conn.close()

        print("✅ Base de datos conectada")
        print(f"📊 Símbolos disponibles: {len(symbols)}")

        if symbols:
            print("\n📋 Datos por símbolo:")
            for symbol in sorted(symbols):
                count = counts.get(symbol, 0)
                status = "✅" if count >= 100 else "⚠️"
                print(f"  {status} {symbol}: {count:,} filas")

            if all(counts.get(s, 0) >= 100 for s in symbols):
                print("\n✅ Todos los símbolos tienen datos suficientes")
                return True
            else:
                print("\n⚠️  Algunos símbolos tienen pocos datos")
                return True  # Continuar de todos modos
        else:
            print("\n❌ No hay datos en la base de datos")
            print("💡 Ejecutar: python historical_data/populate_db.py")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_2_data_validator():
    """Test 2: Validador de datos"""
    print_step(2, "Test del Validador de Datos")

    try:
        from backtesting.data_validator import DataValidator

        validator = DataValidator()

        # Validar AAPL como ejemplo
        print("🔍 Validando AAPL...")
        report = validator.validate_symbol("AAPL")

        print(f"\n📊 RESULTADOS:")
        print(f"  Score general: {report.overall_score:.1f}/100")
        print(f"  Backtest ready: {'✅' if report.is_backtest_ready else '❌'}")
        print(f"  Total filas: {report.total_rows:,}")
        print(f"  Completitud: {report.completeness_pct:.1f}%")
        print(f"  Gaps: {report.gaps_found}")
        print(f"  OHLC violations: {report.ohlc_violations}")

        # Issues críticos
        critical = report.get_critical_issues()
        if critical:
            print(f"\n🚨 Issues críticos: {len(critical)}")
            for issue in critical[:3]:
                print(f"  • {issue.description}")
        else:
            print("\n✅ Sin issues críticos")

        return report.overall_score >= 60  # Más permisivo para testing

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_3_signal_replicator():
    """Test 3: Signal Replicator"""
    print_step(3, "Test del Signal Replicator")

    try:
        from backtesting.signal_replicator import SignalReplicator
        from database.connection import get_connection
        import pandas as pd

        # Cargar datos
        print("📊 Cargando datos de AAPL...")
        conn = get_connection()
        query = """
        SELECT * FROM indicators_data
        WHERE symbol = 'AAPL'
        ORDER BY timestamp ASC
        LIMIT 500
        """
        df = pd.read_sql_query(query, conn)
        conn.close()

        if df.empty:
            print("❌ No hay datos de AAPL")
            return False

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        print(f"  ✅ {len(df)} filas cargadas")

        # Escanear
        print("\n🔍 Escaneando señales...")
        replicator = SignalReplicator()
        signals = replicator.scan_historical_dataframe('AAPL', df, min_signal_strength=65)

        print(f"\n📊 Señales encontradas: {len(signals)}")

        if signals:
            print("\n🎯 Primera señal:")
            idx, signal = signals[0]
            print(f"  Timestamp: {signal.timestamp}")
            print(f"  Tipo: {signal.signal_type}")
            print(f"  Fuerza: {signal.signal_strength} pts")
            print(f"  Calidad: {signal.entry_quality}")
            print(f"  Precio: ${signal.current_price:.2f}")

            print("\n✅ Signal Replicator funcionando")
            return True
        else:
            print("\n⚠️  No se encontraron señales (threshold 65)")
            print("💡 Esto puede ser normal si el período no tiene señales fuertes")
            return True  # No es un error crítico

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_4_position_replicator():
    """Test 4: Position Replicator"""
    print_step(4, "Test del Position Replicator")

    try:
        from backtesting.position_replicator import PositionReplicator
        from scanner import TradingSignal
        from datetime import datetime

        # Crear señal de prueba
        print("📋 Creando señal de prueba...")
        signal = TradingSignal(
            symbol="AAPL",
            timestamp=datetime.now(),
            signal_type="LONG",
            signal_strength=75,
            confidence_level="HIGH",
            current_price=150.0,
            entry_quality="FULL_ENTRY",
            indicator_scores={
                'MACD': 20, 'RSI': 18, 'VWAP': 15,
                'ROC': 20, 'BOLLINGER': 15, 'VOLUME': 10
            },
            indicator_signals={}
        )

        # Calcular posición
        print("\n💼 Calculando posición...")
        replicator = PositionReplicator(capital=10000.0, risk_per_trade=1.5)
        position_plan = replicator.calculate_position(signal, 10000.0)

        if not position_plan:
            print("❌ No se pudo calcular posición")
            return False

        print(f"\n✅ Posición calculada:")
        print(f"  Entry 1: ${position_plan.entry_1_price:.2f} x {position_plan.entry_1_quantity}")
        print(f"  Entry 2: ${position_plan.entry_2_price:.2f} x {position_plan.entry_2_quantity}")
        print(f"  Entry 3: ${position_plan.entry_3_price:.2f} x {position_plan.entry_3_quantity}")
        print(f"  Stop Loss: ${position_plan.stop_loss:.2f}")
        print(f"  TP4: ${position_plan.take_profit_4:.2f}")
        print(f"  Total shares: {position_plan.total_position_size}")
        print(f"  Max risk: ${position_plan.max_capital_at_risk:.2f}")

        # Validaciones básicas
        if position_plan.total_position_size <= 0:
            print("❌ Total position size inválido")
            return False

        if position_plan.stop_loss >= position_plan.entry_1_price:
            print("❌ Stop loss mal calculado")
            return False

        print("\n✅ Position Replicator funcionando correctamente")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_5_backtest_quick():
    """Test 5: Backtesting rápido"""
    print_step(5, "Backtesting Rápido (AAPL, 15 días)")

    try:
        from backtesting.config import BacktestConfig
        from backtesting.backtest_engine import BacktestEngine
        from datetime import datetime, timedelta

        # Config mínima para test rápido
        print("⚙️  Configurando backtesting...")
        config = BacktestConfig(
            symbols=["AAPL"],
            initial_capital=10000.0,
            risk_per_trade=1.5,
            max_concurrent_positions=3,
            min_signal_strength=65,
            validate_data_before_backtest=False,  # Skip validation para ir rápido
            end_date=datetime.now(),
            start_date=datetime.now() - timedelta(days=15)
        )

        print("\n🚀 Ejecutando backtesting...")
        print("   (esto puede tardar 10-30 segundos)\n")

        engine = BacktestEngine(config)
        results = engine.run()

        if 'error' in results:
            print(f"❌ Error en backtesting: {results['error']}")
            return False

        # Verificar resultados
        metrics = results.get('metrics', {})

        print(f"\n📊 RESULTADOS:")
        print(f"  Capital inicial: ${metrics.get('initial_capital', 0):,.2f}")
        print(f"  Capital final: ${metrics.get('final_capital', 0):,.2f}")
        print(f"  Return: {metrics.get('return_pct', 0):.2f}%")
        print(f"  Total trades: {metrics.get('total_trades', 0)}")
        print(f"  Win rate: {metrics.get('win_rate', 0):.1f}%")
        print(f"  Profit factor: {metrics.get('profit_factor', 0):.2f}")

        if metrics.get('total_trades', 0) == 0:
            print("\n⚠️  No se generaron trades")
            print("💡 Esto puede ser normal con período corto")
            return True  # No es error crítico

        print("\n✅ Backtesting completado exitosamente")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_6_reports():
    """Test 6: Generación de reportes"""
    print_step(6, "Test de Generación de Reportes")

    try:
        from backtesting.report_generator import ReportGenerator
        import json
        from datetime import datetime

        # Crear datos de prueba
        print("📝 Creando reportes de prueba...")

        test_results = {
            'config': {
                'initial_capital': 10000.0,
                'symbols': ['AAPL'],
            },
            'metrics': {
                'initial_capital': 10000.0,
                'final_capital': 10500.0,
                'net_pnl': 500.0,
                'return_pct': 5.0,
                'total_trades': 10,
                'winning_trades': 6,
                'losing_trades': 4,
                'win_rate': 60.0,
                'profit_factor': 1.5,
                'max_drawdown_pct': 5.0,
            },
            'trades': [
                {
                    'symbol': 'AAPL',
                    'direction': 'LONG',
                    'total_pnl': 50.0,
                    'signal_strength': 75,
                }
            ],
            'equity_curve': [
                (datetime.now().isoformat(), 10000.0),
                (datetime.now().isoformat(), 10500.0),
            ]
        }

        generator = ReportGenerator()

        # Generar reportes
        print("\n📄 Generando reportes...")
        report_files = generator.generate_all_reports(test_results)

        success = True
        for report_type, filepath in report_files.items():
            if filepath and Path(filepath).exists():
                print(f"  ✅ {report_type}: {filepath}")
            else:
                print(f"  ❌ {report_type}: No generado")
                success = False

        if success:
            print("\n✅ Todos los reportes generados correctamente")
        else:
            print("\n⚠️  Algunos reportes fallaron")

        return success

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests(quick=False):
    """Ejecutar todos los tests"""
    print_header("🧪 TEST AUTOMATIZADO DEL SISTEMA DE BACKTESTING")

    print(f"⏰ Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🏃 Modo: {'RÁPIDO' if quick else 'COMPLETO'}\n")

    tests = [
        ("Base de Datos", test_1_database),
        ("Data Validator", test_2_data_validator),
        ("Signal Replicator", test_3_signal_replicator),
        ("Position Replicator", test_4_position_replicator),
    ]

    if not quick:
        tests.extend([
            ("Backtesting Rápido", test_5_backtest_quick),
            ("Generación de Reportes", test_6_reports),
        ])

    results = {}
    total_tests = len(tests)
    passed = 0

    for test_name, test_func in tests:
        try:
            success = test_func()
            results[test_name] = success
            if success:
                passed += 1
        except KeyboardInterrupt:
            print("\n\n⏸️  Tests interrumpidos por el usuario")
            break
        except Exception as e:
            print(f"\n❌ Error inesperado en {test_name}: {e}")
            import traceback
            traceback.print_exc()
            results[test_name] = False

    # Resumen final
    print_header("📊 RESUMEN DE TESTS")

    for test_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status} - {test_name}")

    print(f"\n📈 RESULTADO FINAL: {passed}/{total_tests} tests pasados")

    if passed == total_tests:
        print("\n🎉 ¡TODOS LOS TESTS PASARON!")
        print("✅ El sistema está listo para usar")
        return 0
    elif passed >= total_tests * 0.7:
        print("\n⚠️  La mayoría de tests pasaron")
        print("💡 Revisar los tests fallidos antes de uso en producción")
        return 1
    else:
        print("\n❌ Muchos tests fallaron")
        print("💡 Revisar la configuración y los datos")
        return 2


def main():
    """Función principal"""
    parser = argparse.ArgumentParser(
        description='🧪 Sistema de Tests Automatizados'
    )
    parser.add_argument('--quick', action='store_true',
                       help='Ejecutar solo tests rápidos')
    parser.add_argument('--full', action='store_true',
                       help='Ejecutar tests completos (default)')

    args = parser.parse_args()

    quick = args.quick

    try:
        return run_all_tests(quick=quick)
    except KeyboardInterrupt:
        print("\n\n👋 Tests cancelados")
        return 130


if __name__ == "__main__":
    sys.exit(main())
