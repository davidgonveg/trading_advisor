#!/bin/bash
# 🚀 QUICKSTART - Inicio Rápido del Sistema de Backtesting
# ========================================================

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║                                                                    ║"
echo "║      🚀 QUICKSTART - Sistema de Backtesting                       ║"
echo "║                                                                    ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

# Función para imprimir headers
print_header() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
    echo "  $1"
    echo "═══════════════════════════════════════════════════════════════════"
    echo ""
}

# Función para imprimir pasos
print_step() {
    echo ""
    echo -e "${BLUE}▶ PASO $1: $2${NC}"
    echo ""
}

# Función para preguntar al usuario
ask_user() {
    echo -e "${YELLOW}$1${NC}"
    read -p "Continuar? (y/n): " response
    if [ "$response" != "y" ] && [ "$response" != "Y" ]; then
        echo -e "${RED}❌ Cancelado${NC}"
        exit 1
    fi
}

# Verificar que estamos en el directorio correcto
if [ ! -d "backtesting" ]; then
    echo -e "${RED}❌ Error: Ejecutar desde la raíz del proyecto${NC}"
    echo "   cd /home/user/trading_advisor"
    exit 1
fi

echo "Este script te guiará paso a paso para:"
echo "  1️⃣  Verificar que todo está instalado"
echo "  2️⃣  Validar los datos históricos"
echo "  3️⃣  Ejecutar un backtesting de prueba"
echo "  4️⃣  Analizar los resultados"
echo ""

ask_user "¿Empezamos?"

# ============================================================================
# PASO 1: Verificar instalación
# ============================================================================

print_step "1" "Verificación de Sistema"

echo "Verificando Python..."
python3 --version || {
    echo -e "${RED}❌ Python 3 no encontrado${NC}"
    exit 1
}

echo -e "${GREEN}✅ Python encontrado${NC}"

echo ""
echo "Verificando módulos de Python..."
python3 << 'PYEOF'
import sys
missing = []

modules = ['pandas', 'numpy', 'sqlite3']
for module in modules:
    try:
        __import__(module)
        print(f"  ✅ {module}")
    except ImportError:
        print(f"  ❌ {module}")
        missing.append(module)

if missing:
    print(f"\n⚠️  Instalar: pip install {' '.join(missing)}")
    sys.exit(1)
else:
    print("\n✅ Todos los módulos necesarios están instalados")
PYEOF

[ $? -eq 0 ] || exit 1

echo ""
echo "Verificando estructura del proyecto..."

required_files=(
    "backtesting/__init__.py"
    "backtesting/config.py"
    "backtesting/backtest_engine.py"
    "backtesting/run_backtest.py"
    "database/connection.py"
    "scanner.py"
    "position_calculator.py"
)

all_found=true
for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✅ $file"
    else
        echo "  ❌ $file"
        all_found=false
    fi
done

if [ "$all_found" = false ]; then
    echo -e "${RED}❌ Archivos faltantes${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Estructura del proyecto correcta${NC}"

# ============================================================================
# PASO 2: Verificar datos
# ============================================================================

print_step "2" "Verificación de Datos Históricos"

if [ ! -f "database/trading_data.db" ]; then
    echo -e "${RED}❌ Base de datos no encontrada${NC}"
    echo ""
    echo "La base de datos debe estar en: database/trading_data.db"
    echo ""
    ask_user "¿Quieres crearla y poblarla ahora? (puede tardar 10-30 min)"

    echo ""
    echo "Inicializando base de datos..."
    python3 database/models.py

    echo ""
    echo "Poblando con datos históricos..."
    echo "(Esto puede tardar dependiendo de cuántos datos descargue)"
    python3 historical_data/populate_db.py

    echo -e "${GREEN}✅ Base de datos creada y poblada${NC}"
else
    echo -e "${GREEN}✅ Base de datos encontrada${NC}"
fi

echo ""
echo "Verificando datos disponibles..."

python3 << 'PYEOF'
from database.connection import get_connection

conn = get_connection()
cursor = conn.cursor()

cursor.execute("SELECT symbol, COUNT(*) FROM indicators_data GROUP BY symbol")
results = cursor.fetchall()

print("\n📊 DATOS DISPONIBLES:")
print("-" * 50)

if not results:
    print("  ❌ Sin datos")
    conn.close()
    exit(1)

good_symbols = []
for symbol, count in results:
    status = "✅" if count >= 100 else "⚠️"
    print(f"  {status} {symbol}: {count:,} filas")
    if count >= 100:
        good_symbols.append(symbol)

print("-" * 50)
print(f"\n✅ Símbolos con datos suficientes: {len(good_symbols)}")

conn.close()

if not good_symbols:
    print("\n❌ No hay símbolos con datos suficientes")
    exit(1)
PYEOF

[ $? -eq 0 ] || {
    echo -e "${RED}❌ Error verificando datos${NC}"
    exit 1
}

# ============================================================================
# PASO 3: Validar calidad de datos
# ============================================================================

print_step "3" "Validación de Calidad de Datos"

echo "Validando datos de AAPL (ejemplo)..."
echo ""

python3 << 'PYEOF'
from backtesting.data_validator import DataValidator

validator = DataValidator()
report = validator.validate_symbol("AAPL")

print(f"📊 RESULTADOS DE VALIDACIÓN:")
print(f"  Score general: {report.overall_score:.1f}/100")
print(f"  Backtest ready: {'✅ Sí' if report.is_backtest_ready else '❌ No'}")
print(f"  Total filas: {report.total_rows:,}")
print(f"  Completitud: {report.completeness_pct:.1f}%")
print(f"  Gaps: {report.gaps_found}")

if report.is_backtest_ready:
    print("\n✅ Datos de AAPL aptos para backtesting")
else:
    print("\n⚠️  Datos de AAPL tienen issues")
    print("   Se puede continuar pero los resultados pueden ser limitados")
PYEOF

echo ""
ask_user "¿Continuar con el backtesting de prueba?"

# ============================================================================
# PASO 4: Backtesting de prueba
# ============================================================================

print_step "4" "Backtesting de Prueba (AAPL, últimos 30 días)"

echo "Ejecutando backtesting..."
echo ""
echo "⚙️  Configuración:"
echo "   • Símbolo: AAPL"
echo "   • Período: 30 días"
echo "   • Capital inicial: $10,000"
echo "   • Riesgo por trade: 1.5%"
echo ""
echo "⏱️  Esto puede tardar 30-60 segundos..."
echo ""

python3 backtesting/run_backtest.py --symbol AAPL --days 30

[ $? -eq 0 ] || {
    echo -e "${RED}❌ Error en backtesting${NC}"
    exit 1
}

# ============================================================================
# PASO 5: Resultados
# ============================================================================

print_step "5" "Análisis de Resultados"

echo "Buscando últimos resultados generados..."
echo ""

# Encontrar último resumen
summary_file=$(ls -t backtesting/results/summary_*.txt 2>/dev/null | head -1)

if [ -z "$summary_file" ]; then
    echo -e "${RED}❌ No se encontró resumen de resultados${NC}"
    exit 1
fi

echo "📄 Resumen encontrado: $summary_file"
echo ""
cat "$summary_file"

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# Encontrar JSON
json_file=$(ls -t backtesting/results/results_*.json 2>/dev/null | head -1)

if [ -n "$json_file" ]; then
    echo "📊 Análisis detallado disponible en: $json_file"
fi

# Encontrar CSV
csv_file=$(ls -t backtesting/results/trades_*.csv 2>/dev/null | head -1)

if [ -n "$csv_file" ]; then
    echo "📈 Trades en CSV: $csv_file"
fi

echo ""
echo "📂 Todos los reportes en: backtesting/results/"
echo ""

# ============================================================================
# PASO 6: Próximos pasos
# ============================================================================

print_header "✅ QUICKSTART COMPLETADO"

echo "🎉 ¡Felicidades! El sistema de backtesting está funcionando."
echo ""
echo "📚 PRÓXIMOS PASOS:"
echo ""
echo "1️⃣  Ver documentación completa:"
echo "   cat backtesting/README.md"
echo ""
echo "2️⃣  Ver guía de testing detallada:"
echo "   cat backtesting/GUIA_TESTING.md"
echo ""
echo "3️⃣  Ejecutar tests automatizados:"
echo "   python backtesting/test_system.py"
echo ""
echo "4️⃣  Backtesting completo (todos los símbolos):"
echo "   python backtesting/run_backtest.py"
echo ""
echo "5️⃣  Probar diferentes configuraciones:"
echo "   python backtesting/run_backtest.py --conservative"
echo "   python backtesting/run_backtest.py --aggressive"
echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo -e "${GREEN}✨ ¡Todo listo para empezar!${NC}"
echo ""
