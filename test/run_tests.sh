#!/bin/bash
# 🧪 Script de ejecución de tests para Trading Advisor
# =====================================================

set -e  # Exit on error

# Colores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo ""
echo "🧪 Trading Advisor Test Suite"
echo "============================="
echo ""

# Función para mostrar uso
show_usage() {
    echo "Uso: ./run_tests.sh [opción]"
    echo ""
    echo "Opciones:"
    echo "  all           - Ejecutar todos los tests (por defecto)"
    echo "  fast          - Ejecutar solo tests rápidos (excluir 'slow')"
    echo "  database      - Solo tests de base de datos"
    echo "  indicators    - Solo tests de indicadores"
    echo "  gaps          - Solo tests de gap filling"
    echo "  positions     - Solo tests de posiciones"
    echo "  backtest      - Solo tests de backtesting"
    echo "  integration   - Solo tests de integración"
    echo "  coverage      - Ejecutar con reporte de cobertura"
    echo "  parallel      - Ejecutar tests en paralelo (más rápido)"
    echo "  failed        - Re-ejecutar solo tests que fallaron"
    echo "  help          - Mostrar esta ayuda"
    echo ""
    echo "Ejemplos:"
    echo "  ./run_tests.sh"
    echo "  ./run_tests.sh fast"
    echo "  ./run_tests.sh database"
    echo "  ./run_tests.sh coverage"
}

# Verificar que estamos en el directorio correcto
if [ ! -f "conftest.py" ]; then
    echo -e "${RED}❌ Error: Debes ejecutar este script desde el directorio test/${NC}"
    echo "   cd test && ./run_tests.sh"
    exit 1
fi

# Verificar que pytest está instalado
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}❌ Error: pytest no está instalado${NC}"
    echo "   Instala con: pip install pytest"
    exit 1
fi

# Procesar argumentos
OPTION="${1:-all}"

case $OPTION in
    all)
        echo -e "${GREEN}▶ Ejecutando todos los tests...${NC}"
        echo ""
        pytest -v
        ;;

    fast)
        echo -e "${GREEN}▶ Ejecutando tests rápidos...${NC}"
        echo ""
        pytest -v -m "not slow"
        ;;

    database)
        echo -e "${GREEN}▶ Ejecutando tests de base de datos...${NC}"
        echo ""
        pytest -v -m database
        ;;

    indicators)
        echo -e "${GREEN}▶ Ejecutando tests de indicadores...${NC}"
        echo ""
        pytest -v -m indicators
        ;;

    gaps)
        echo -e "${GREEN}▶ Ejecutando tests de gap filling...${NC}"
        echo ""
        pytest -v -m gaps
        ;;

    positions)
        echo -e "${GREEN}▶ Ejecutando tests de posiciones...${NC}"
        echo ""
        pytest -v -m positions
        ;;

    backtest)
        echo -e "${GREEN}▶ Ejecutando tests de backtesting...${NC}"
        echo ""
        pytest -v -m backtest
        ;;

    integration)
        echo -e "${GREEN}▶ Ejecutando tests de integración...${NC}"
        echo ""
        pytest -v -m integration
        ;;

    coverage)
        echo -e "${GREEN}▶ Ejecutando tests con cobertura...${NC}"
        echo ""
        if command -v pytest-cov &> /dev/null; then
            pytest -v --cov=.. --cov-report=term-missing --cov-report=html
            echo ""
            echo -e "${GREEN}✅ Reporte de cobertura generado en htmlcov/index.html${NC}"
        else
            echo -e "${YELLOW}⚠️  pytest-cov no está instalado${NC}"
            echo "   Instala con: pip install pytest-cov"
            exit 1
        fi
        ;;

    parallel)
        echo -e "${GREEN}▶ Ejecutando tests en paralelo...${NC}"
        echo ""
        if command -v pytest-xdist &> /dev/null; then
            pytest -v -n auto
        else
            echo -e "${YELLOW}⚠️  pytest-xdist no está instalado${NC}"
            echo "   Instala con: pip install pytest-xdist"
            echo "   Ejecutando tests normalmente..."
            pytest -v
        fi
        ;;

    failed)
        echo -e "${GREEN}▶ Re-ejecutando tests que fallaron...${NC}"
        echo ""
        pytest -v --lf
        ;;

    help|--help|-h)
        show_usage
        exit 0
        ;;

    *)
        echo -e "${RED}❌ Opción desconocida: $OPTION${NC}"
        echo ""
        show_usage
        exit 1
        ;;
esac

# Capturar código de salida
EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ Todos los tests pasaron exitosamente!${NC}"
else
    echo -e "${RED}❌ Algunos tests fallaron. Ver detalles arriba.${NC}"
fi

echo ""

exit $EXIT_CODE
