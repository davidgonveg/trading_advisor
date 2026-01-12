#!/usr/bin/env python3
"""
📊 CSV ANALYZER V1.0 - VALIDACIÓN PARA BACKTESTING
==================================================

Análisis exhaustivo de archivos CSV descargados para validar 
si son aptos para backtesting confiable.

✅ ANÁLISIS INCLUYE:
- Integridad de datos OHLCV
- Gaps de tiempo (períodos faltantes)
- Calidad de precios (outliers, anomalías)
- Volúmenes válidos
- Continuidad temporal
- Cobertura de período requerido
- Estadísticas por símbolo
- Recomendaciones para backtesting

🎯 CRITERIOS DE CALIDAD:
- EXCELENTE: >95% datos, <5 gaps, volúmenes válidos
- BUENO: >90% datos, <10 gaps, algunos problemas menores  
- REGULAR: >80% datos, gaps moderados, requiere limpieza
- POBRE: <80% datos, muchos gaps, no apto para backtesting

USO:
    python csv_analyzer_backtest.py                    # Analizar todos los CSV
    python csv_analyzer_backtest.py --symbol AAPL      # Solo AAPL
    python csv_analyzer_backtest.py --detailed         # Análisis detallado
    python csv_analyzer_backtest.py --save-report      # Guardar reporte HTML
"""

import os
import sys
import pandas as pd
import numpy as np
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import glob
import json
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns

# Configurar paths
current_dir = Path(__file__).parent.absolute()
project_root = current_dir.parent if current_dir.name == 'historical_data' else current_dir
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

class DataQuality(Enum):
    """Niveles de calidad de datos"""
    EXCELLENT = "EXCELENTE"
    GOOD = "BUENO"
    FAIR = "REGULAR"
    POOR = "POBRE"
    UNUSABLE = "INUTILIZABLE"

@dataclass
class DataGap:
    """Representar un gap en los datos"""
    start_time: datetime
    end_time: datetime
    duration_minutes: int
    expected_points: int
    gap_type: str  # 'weekend', 'market_hours', 'data_missing'

@dataclass
class SymbolReport:
    """Reporte de análisis por símbolo"""
    symbol: str
    file_path: str
    total_points: int
    date_range: Tuple[datetime, datetime]
    timeframe: str
    
    # Calidad de datos
    data_quality: DataQuality
    completeness_pct: float
    
    # Análisis OHLCV
    price_anomalies: int
    volume_issues: int
    ohlc_consistency: float
    
    # Análisis temporal
    total_gaps: int
    significant_gaps: int
    largest_gap_hours: float
    
    # Estadísticas de precios
    price_stats: Dict[str, float]
    volume_stats: Dict[str, float]
    
    # Apto para backtesting
    backtest_ready: bool
    warnings: List[str]
    recommendations: List[str]

class CSVBacktestAnalyzer:
    """Analizador de CSV para validación de backtesting"""
    
    def __init__(self, raw_data_dir: str = "raw_data"):
        self.raw_data_dir = Path(raw_data_dir)
        self.reports: Dict[str, SymbolReport] = {}
        
        # Configuración de análisis
        self.timeframe_minutes = {
            '1m': 1, '5m': 5, '15m': 15, '30m': 30, 
            '1h': 60, '4h': 240, '1d': 1440
        }
        
        # Parámetros de calidad
        self.quality_thresholds = {
            'excellent': {'completeness': 95, 'max_gaps': 5},
            'good': {'completeness': 90, 'max_gaps': 10},
            'fair': {'completeness': 80, 'max_gaps': 25},
            'poor': {'completeness': 60, 'max_gaps': 50}
        }
    
    def find_csv_files(self, symbol_filter: Optional[str] = None) -> List[Path]:
        """Encontrar archivos CSV en el directorio"""
        if not self.raw_data_dir.exists():
            logger.error(f"❌ Directorio {self.raw_data_dir} no existe")
            return []
        
        # Patrón de búsqueda
        pattern = f"{symbol_filter}_*.csv" if symbol_filter else "*.csv"
        csv_files = list(self.raw_data_dir.glob(pattern))
        
        # Filtrar solo archivos 15m (según tu estrategia)
        csv_15m = [f for f in csv_files if '15m' in f.name]
        
        logger.info(f"📁 Encontrados {len(csv_15m)} archivos CSV de 15min")
        return csv_15m
    
    def parse_filename_info(self, file_path: Path) -> Dict[str, str]:
        """Extraer información del nombre del archivo"""
        # Formato esperado: SYMBOL_15m_YYYYMMDD_HHMMSS.csv
        name_parts = file_path.stem.split('_')
        
        if len(name_parts) >= 2:
            return {
                'symbol': name_parts[0],
                'timeframe': name_parts[1] if len(name_parts) > 1 else '15m',
                'date_created': name_parts[2] if len(name_parts) > 2 else 'unknown',
                'time_created': name_parts[3] if len(name_parts) > 3 else 'unknown'
            }
        else:
            return {'symbol': 'UNKNOWN', 'timeframe': '15m', 'date_created': '', 'time_created': ''}
    
    def load_and_validate_csv(self, file_path: Path) -> Tuple[Optional[pd.DataFrame], List[str]]:
        """Cargar y validar un archivo CSV"""
        warnings = []
        
        try:
            # Intentar cargar con diferentes configuraciones
            df = None
            
            # Formato 1: Con header
            try:
                df = pd.read_csv(file_path)
                if df.empty:
                    raise ValueError("DataFrame vacío")
            except:
                # Formato 2: Sin header
                try:
                    df = pd.read_csv(file_path, header=None)
                    # Asignar nombres de columnas esperadas
                    expected_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                    if len(df.columns) >= 6:
                        df.columns = expected_cols[:len(df.columns)]
                except Exception as e:
                    warnings.append(f"Error cargando CSV: {e}")
                    return None, warnings
            
            if df is None or df.empty:
                warnings.append("Archivo CSV vacío")
                return None, warnings
            
            # Normalizar nombres de columnas
            df.columns = df.columns.str.lower().str.strip()
            
            # Mapear columnas comunes
            column_mapping = {
                'datetime': 'timestamp',
                'date': 'timestamp',
                'time': 'timestamp',
                'open_price': 'open',
                'high_price': 'high', 
                'low_price': 'low',
                'close_price': 'close',
                'vol': 'volume',
                'volume_traded': 'volume'
            }
            
            df = df.rename(columns=column_mapping)
            
            # Verificar columnas requeridas
            required_cols = ['timestamp', 'open', 'high', 'low', 'close']
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                warnings.append(f"Columnas faltantes: {missing_cols}")
                return None, warnings
            
            # Convertir timestamp
            try:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            except:
                warnings.append("Error convirtiendo timestamps")
                return None, warnings
            
            # Convertir precios a numérico
            price_cols = ['open', 'high', 'low', 'close']
            for col in price_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Volume (opcional)
            if 'volume' in df.columns:
                df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
            else:
                df['volume'] = 0
                warnings.append("Columna volume no encontrada, usando 0")
            
            # Ordenar por timestamp
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            # Remover duplicados de timestamp
            duplicates = df['timestamp'].duplicated().sum()
            if duplicates > 0:
                warnings.append(f"Removidos {duplicates} timestamps duplicados")
                df = df.drop_duplicates(subset=['timestamp'], keep='first')
            
            return df, warnings
            
        except Exception as e:
            warnings.append(f"Error cargando {file_path.name}: {e}")
            return None, warnings
    
    def detect_time_gaps(self, df: pd.DataFrame, expected_interval_min: int = 15) -> List[DataGap]:
        """Detectar gaps temporales en los datos"""
        gaps = []
        
        if len(df) < 2:
            return gaps
        
        expected_delta = timedelta(minutes=expected_interval_min)
        
        for i in range(1, len(df)):
            current_time = df.iloc[i]['timestamp']
            prev_time = df.iloc[i-1]['timestamp']
            actual_delta = current_time - prev_time
            
            # Gap significativo (más de 1.5x el intervalo esperado)
            if actual_delta > expected_delta * 1.5:
                gap_minutes = int(actual_delta.total_seconds() / 60)
                expected_points = max(1, gap_minutes // expected_interval_min - 1)
                
                # Clasificar tipo de gap
                gap_type = "data_missing"
                if current_time.weekday() >= 5 or prev_time.weekday() >= 5:  # Weekend
                    gap_type = "weekend"
                elif gap_minutes > 960:  # > 16 horas
                    gap_type = "market_closed"
                
                gap = DataGap(
                    start_time=prev_time,
                    end_time=current_time,
                    duration_minutes=gap_minutes,
                    expected_points=expected_points,
                    gap_type=gap_type
                )
                gaps.append(gap)
        
        return gaps
    
    def analyze_price_quality(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analizar calidad de precios OHLCV"""
        analysis = {
            'total_points': len(df),
            'null_values': {},
            'price_anomalies': 0,
            'volume_issues': 0,
            'ohlc_consistency': 100.0
        }
        
        price_cols = ['open', 'high', 'low', 'close']
        
        # Contar valores nulos
        for col in price_cols + ['volume']:
            if col in df.columns:
                null_count = df[col].isnull().sum()
                analysis['null_values'][col] = null_count
        
        # Verificar consistencia OHLC (High >= Low, High >= Open, High >= Close, etc.)
        if all(col in df.columns for col in price_cols):
            # High debe ser >= Low, Open, Close
            high_issues = (
                (df['high'] < df['low']) | 
                (df['high'] < df['open']) | 
                (df['high'] < df['close'])
            ).sum()
            
            # Low debe ser <= High, Open, Close  
            low_issues = (
                (df['low'] > df['high']) |
                (df['low'] > df['open']) |
                (df['low'] > df['close'])
            ).sum()
            
            total_issues = high_issues + low_issues
            analysis['ohlc_consistency'] = max(0, 100 - (total_issues / len(df) * 100))
            analysis['price_anomalies'] = total_issues
        
        # Detectar outliers de precio (cambios > 20% en 15min)
        if 'close' in df.columns:
            price_changes = df['close'].pct_change().abs()
            extreme_changes = (price_changes > 0.2).sum()  # > 20%
            analysis['price_anomalies'] += extreme_changes
        
        # Analizar volúmenes
        if 'volume' in df.columns:
            zero_volume = (df['volume'] == 0).sum()
            negative_volume = (df['volume'] < 0).sum()
            analysis['volume_issues'] = zero_volume + negative_volume
        
        return analysis
    
    def calculate_completeness(self, df: pd.DataFrame, expected_interval_min: int = 15) -> float:
        """Calcular porcentaje de completeness de los datos"""
        if len(df) < 2:
            return 0.0
        
        # Rango temporal total
        start_time = df['timestamp'].min()
        end_time = df['timestamp'].max()
        total_duration = end_time - start_time
        
        # Solo contar horas de mercado (aprox 6.5h por día, 5 días por semana)
        total_days = total_duration.days
        market_hours_per_day = 6.5
        market_days = total_days * (5/7)  # Aproximación
        
        expected_total_points = int(market_days * market_hours_per_day * (60 / expected_interval_min))
        
        if expected_total_points == 0:
            return 100.0
        
        actual_points = len(df)
        completeness = min(100.0, (actual_points / expected_total_points) * 100)
        
        return completeness
    
    def determine_data_quality(self, completeness: float, gaps: List[DataGap], 
                             price_analysis: Dict[str, Any]) -> DataQuality:
        """Determinar nivel de calidad general"""
        significant_gaps = len([g for g in gaps if g.gap_type == 'data_missing' and g.duration_minutes > 60])
        
        # Criterios de calidad
        if (completeness >= self.quality_thresholds['excellent']['completeness'] and 
            significant_gaps <= self.quality_thresholds['excellent']['max_gaps'] and
            price_analysis['ohlc_consistency'] > 95):
            return DataQuality.EXCELLENT
        
        elif (completeness >= self.quality_thresholds['good']['completeness'] and 
              significant_gaps <= self.quality_thresholds['good']['max_gaps'] and
              price_analysis['ohlc_consistency'] > 90):
            return DataQuality.GOOD
        
        elif (completeness >= self.quality_thresholds['fair']['completeness'] and 
              significant_gaps <= self.quality_thresholds['fair']['max_gaps'] and
              price_analysis['ohlc_consistency'] > 80):
            return DataQuality.FAIR
        
        elif completeness >= self.quality_thresholds['poor']['completeness']:
            return DataQuality.POOR
        
        else:
            return DataQuality.UNUSABLE
    
    def generate_symbol_report(self, file_path: Path, detailed: bool = False) -> Optional[SymbolReport]:
        """Generar reporte completo para un símbolo"""
        logger.info(f"📊 Analizando {file_path.name}...")
        
        # Parsear info del archivo
        file_info = self.parse_filename_info(file_path)
        symbol = file_info['symbol']
        
        # Cargar datos
        df, load_warnings = self.load_and_validate_csv(file_path)
        if df is None:
            logger.error(f"❌ No se pudo cargar {file_path.name}")
            return None
        
        # Análisis temporal
        gaps = self.detect_time_gaps(df, 15)
        completeness = self.calculate_completeness(df, 15)
        
        # Análisis de precios
        price_analysis = self.analyze_price_quality(df)
        
        # Calcular estadísticas
        price_stats = {}
        volume_stats = {}
        
        if 'close' in df.columns:
            price_stats = {
                'min': float(df['close'].min()),
                'max': float(df['close'].max()),
                'mean': float(df['close'].mean()),
                'std': float(df['close'].std()),
                'median': float(df['close'].median())
            }
        
        if 'volume' in df.columns:
            volume_stats = {
                'min': float(df['volume'].min()),
                'max': float(df['volume'].max()),
                'mean': float(df['volume'].mean()),
                'median': float(df['volume'].median())
            }
        
        # Determinar calidad
        data_quality = self.determine_data_quality(completeness, gaps, price_analysis)
        
        # Generar warnings y recomendaciones
        warnings = load_warnings.copy()
        recommendations = []
        
        significant_gaps = [g for g in gaps if g.gap_type == 'data_missing']
        if len(significant_gaps) > 10:
            warnings.append(f"Muchos gaps de datos: {len(significant_gaps)}")
            recommendations.append("Considerar re-descarga de datos")
        
        if price_analysis['ohlc_consistency'] < 90:
            warnings.append(f"Inconsistencias OHLC: {100-price_analysis['ohlc_consistency']:.1f}%")
            recommendations.append("Validar y limpiar precios anómalos")
        
        if completeness < 80:
            warnings.append(f"Completeness baja: {completeness:.1f}%")
            recommendations.append("Insuficientes datos para backtesting confiable")
        
        # Determinar si es apto para backtesting
        backtest_ready = (
            data_quality in [DataQuality.EXCELLENT, DataQuality.GOOD, DataQuality.FAIR] and
            completeness >= 75 and
            len(df) >= 1000  # Al menos 1000 puntos
        )
        
        if not backtest_ready:
            recommendations.append("NO recomendado para backtesting sin mejoras")
        
        # Crear reporte
        report = SymbolReport(
            symbol=symbol,
            file_path=str(file_path),
            total_points=len(df),
            date_range=(df['timestamp'].min(), df['timestamp'].max()),
            timeframe=file_info['timeframe'],
            data_quality=data_quality,
            completeness_pct=completeness,
            price_anomalies=price_analysis['price_anomalies'],
            volume_issues=price_analysis['volume_issues'],
            ohlc_consistency=price_analysis['ohlc_consistency'],
            total_gaps=len(gaps),
            significant_gaps=len(significant_gaps),
            largest_gap_hours=max([g.duration_minutes/60 for g in gaps], default=0),
            price_stats=price_stats,
            volume_stats=volume_stats,
            backtest_ready=backtest_ready,
            warnings=warnings,
            recommendations=recommendations
        )
        
        return report
    
    def analyze_all_csv(self, symbol_filter: Optional[str] = None, detailed: bool = False) -> Dict[str, SymbolReport]:
        """Analizar todos los archivos CSV"""
        csv_files = self.find_csv_files(symbol_filter)
        
        if not csv_files:
            logger.warning("⚠️ No se encontraron archivos CSV para analizar")
            return {}
        
        print(f"\n📊 ANALIZANDO {len(csv_files)} ARCHIVOS CSV")
        print("=" * 60)
        
        reports = {}
        
        for file_path in csv_files:
            report = self.generate_symbol_report(file_path, detailed)
            if report:
                reports[report.symbol] = report
        
        self.reports = reports
        return reports
    
    def print_summary_report(self):
        """Imprimir reporte resumen"""
        if not self.reports:
            print("❌ No hay reportes para mostrar")
            return
        
        print(f"\n📋 RESUMEN DE ANÁLISIS - {len(self.reports)} SÍMBOLOS")
        print("=" * 70)
        
        # Estadísticas generales
        total_points = sum(r.total_points for r in self.reports.values())
        backtest_ready = sum(1 for r in self.reports.values() if r.backtest_ready)
        
        print(f"📊 Total de puntos de datos: {total_points:,}")
        print(f"✅ Símbolos listos para backtesting: {backtest_ready}/{len(self.reports)}")
        
        # Por calidad
        quality_counts = {}
        for report in self.reports.values():
            quality = report.data_quality
            quality_counts[quality] = quality_counts.get(quality, 0) + 1
        
        print(f"\n🎯 DISTRIBUCIÓN POR CALIDAD:")
        quality_emojis = {
            DataQuality.EXCELLENT: "🟢",
            DataQuality.GOOD: "🔵", 
            DataQuality.FAIR: "🟡",
            DataQuality.POOR: "🟠",
            DataQuality.UNUSABLE: "🔴"
        }
        
        for quality, count in quality_counts.items():
            emoji = quality_emojis.get(quality, "❓")
            print(f"   {emoji} {quality.value}: {count} símbolos")
        
        print(f"\n📈 DETALLES POR SÍMBOLO:")
        print("-" * 70)
        
        for symbol, report in sorted(self.reports.items()):
            emoji = quality_emojis.get(report.data_quality, "❓")
            status = "✅" if report.backtest_ready else "❌"
            
            date_start = report.date_range[0].strftime('%Y-%m-%d')
            date_end = report.date_range[1].strftime('%Y-%m-%d')
            days_span = (report.date_range[1] - report.date_range[0]).days
            
            print(f"{status} {emoji} {symbol:6} | {report.total_points:5,} puntos | "
                  f"{report.completeness_pct:5.1f}% | {report.total_gaps:2} gaps | "
                  f"{date_start} a {date_end} ({days_span}d)")
            
            if report.warnings:
                for warning in report.warnings[:2]:  # Solo primeros 2
                    print(f"     ⚠️ {warning}")
        
        # Recomendaciones finales
        print(f"\n💡 RECOMENDACIONES GENERALES:")
        print("-" * 40)
        
        if backtest_ready >= len(self.reports) * 0.8:
            print("✅ Excelente calidad general - proceder con backtesting")
        elif backtest_ready >= len(self.reports) * 0.5:
            print("🟡 Calidad mixta - considerar filtrar símbolos problemáticos")
        else:
            print("🔴 Calidad insuficiente - re-descargar datos recomendado")
        
        poor_symbols = [s for s, r in self.reports.items() if not r.backtest_ready]
        if poor_symbols:
            print(f"\n❌ Símbolos NO aptos para backtesting: {', '.join(poor_symbols)}")
            print("   Recomendación: Re-descargar o excluir del backtesting")
        
        good_symbols = [s for s, r in self.reports.items() if r.backtest_ready]
        if good_symbols:
            print(f"\n✅ Símbolos APTOS para backtesting: {', '.join(good_symbols)}")
    
    def save_detailed_report(self, output_file: str = "csv_analysis_report.json"):
        """Guardar reporte detallado en JSON"""
        if not self.reports:
            logger.warning("No hay reportes para guardar")
            return False
        
        # Convertir reportes a dict serializable
        serializable_reports = {}
        
        for symbol, report in self.reports.items():
            serializable_reports[symbol] = {
                'symbol': report.symbol,
                'file_path': report.file_path,
                'total_points': report.total_points,
                'date_range': {
                    'start': report.date_range[0].isoformat(),
                    'end': report.date_range[1].isoformat()
                },
                'timeframe': report.timeframe,
                'data_quality': report.data_quality.value,
                'completeness_pct': report.completeness_pct,
                'price_anomalies': report.price_anomalies,
                'volume_issues': report.volume_issues,
                'ohlc_consistency': report.ohlc_consistency,
                'total_gaps': report.total_gaps,
                'significant_gaps': report.significant_gaps,
                'largest_gap_hours': report.largest_gap_hours,
                'price_stats': report.price_stats,
                'volume_stats': report.volume_stats,
                'backtest_ready': report.backtest_ready,
                'warnings': report.warnings,
                'recommendations': report.recommendations
            }
        
        # Añadir metadatos
        report_data = {
            'analysis_timestamp': datetime.now().isoformat(),
            'total_symbols': len(self.reports),
            'backtest_ready_count': sum(1 for r in self.reports.values() if r.backtest_ready),
            'symbols': serializable_reports
        }
        
        try:
            with open(output_file, 'w') as f:
                json.dump(report_data, f, indent=2)
            
            logger.info(f"✅ Reporte detallado guardado en: {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error guardando reporte: {e}")
            return False

def main():
    """Función principal"""
    parser = argparse.ArgumentParser(description='CSV Analyzer for Backtesting V1.0')
    parser.add_argument('--symbol', type=str, help='Analizar solo este símbolo')
    parser.add_argument('--detailed', action='store_true', help='Análisis detallado')
    parser.add_argument('--save-report', action='store_true', help='Guardar reporte JSON')
    parser.add_argument('--raw-data-dir', default='raw_data', help='Directorio de archivos CSV')
    
    args = parser.parse_args()
    
    # Crear analizador
    analyzer = CSVBacktestAnalyzer(args.raw_data_dir)
    
    try:
        # Ejecutar análisis
        reports = analyzer.analyze_all_csv(
            symbol_filter=args.symbol,
            detailed=args.detailed
        )
        
        if not reports:
            print("❌ No se pudieron analizar archivos CSV")
            sys.exit(1)
        
        # Mostrar reporte
        analyzer.print_summary_report()
        
        # Guardar reporte detallado si se solicita
        if args.save_report:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = f"csv_analysis_{timestamp}.json"
            analyzer.save_detailed_report(report_file)
        
        # Conclusión
        backtest_ready = sum(1 for r in reports.values() if r.backtest_ready)
        total = len(reports)
        
        print(f"\n🏁 CONCLUSIÓN FINAL")
        print("=" * 50)
        
        if backtest_ready == total:
            print("🎉 ¡TODOS los archivos están listos para backtesting!")
            print("📋 Próximo paso: python populate_db.py")
        elif backtest_ready >= total * 0.7:
            print(f"✅ {backtest_ready}/{total} archivos listos - calidad suficiente")
            print("📋 Próximo paso: proceder con populate_db.py")
        else:
            print(f"⚠️ Solo {backtest_ready}/{total} archivos aptos")
            print("📋 Recomendación: re-descargar datos problemáticos")
        
    except KeyboardInterrupt:
        print("\n⚠️ Análisis interrumpido por el usuario")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Error en análisis: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()