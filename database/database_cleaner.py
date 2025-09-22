#!/usr/bin/env python3
"""
🧹 DATABASE CLEANER V1.0 - LIMPIEZA COMPLETA PARA REINICIO
=========================================================

Script de limpieza para preparar la base de datos para un reinicio completo:

✅ ACCIONES DE LIMPIEZA:
1. Borrar archivos CSV en historical_data/raw_data/
2. Vaciar tabla ohlcv_data completamente
3. Borrar registros sin close_price en indicators_data
4. Mantener señales reales (signals_sent) intactas
5. Crear backup automático antes de limpiar
6. Mostrar estadísticas antes/después

🎯 RESULTADO FINAL:
- Base de datos limpia y consistente
- Solo señales reales preservadas
- Lista para descargas frescas de datos 15min
- Preparada para backtesting confiable

USO:
    python database_cleaner.py                    # Limpieza interactiva
    python database_cleaner.py --auto-confirm     # Sin confirmaciones
    python database_cleaner.py --backup-only      # Solo crear backup
    python database_cleaner.py --show-stats       # Solo mostrar estadísticas
"""

import os
import sys
import sqlite3
import shutil
import logging
import argparse
from datetime import datetime
from pathlib import Path
import glob

# Configurar paths - Este script debe estar en la carpeta database/
current_dir = Path(__file__).parent.absolute()
project_root = current_dir.parent if current_dir.name == 'database' else current_dir
sys.path.insert(0, str(project_root))

try:
    from database.connection import get_connection
    print("✅ Módulos del sistema importados correctamente")
except ImportError as e:
    print(f"❌ Error importando módulos: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

class DatabaseCleaner:
    """Limpiador de base de datos para reinicio completo"""
    
    def __init__(self, auto_confirm: bool = False):
        self.auto_confirm = auto_confirm
        self.stats_before = {}
        self.stats_after = {}
        self.backup_path = None
        
        # Paths importantes
        self.csv_dir = project_root / 'historical_data' / 'raw_data'
        self.db_path = self.find_database_path()
    
    def find_database_path(self):
        """Encontrar el path de la base de datos"""
        possible_paths = [
            project_root / 'database' / 'trading_data.db',
            project_root / 'trading_data.db',
            Path.cwd() / 'database' / 'trading_data.db'
        ]
        
        for path in possible_paths:
            if path.exists():
                logger.info(f"📍 Base de datos encontrada: {path}")
                return path
        
        logger.error("❌ No se encontró la base de datos")
        sys.exit(1)
    
    def collect_stats_before(self):
        """Recopilar estadísticas antes de la limpieza"""
        print("\n📊 ESTADÍSTICAS ANTES DE LA LIMPIEZA")
        print("=" * 50)
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Estadísticas de CSV files
            csv_files = list(self.csv_dir.glob("*.csv")) if self.csv_dir.exists() else []
            csv_size_mb = sum(f.stat().st_size for f in csv_files) / (1024 * 1024)
            
            print(f"📁 ARCHIVOS CSV:")
            print(f"   Archivos encontrados: {len(csv_files)}")
            print(f"   Tamaño total: {csv_size_mb:.2f} MB")
            
            if csv_files:
                print(f"   Algunos archivos: {[f.name for f in csv_files[:3]]}...")
            
            # Estadísticas de tablas
            tables_info = {}
            
            for table in ['ohlcv_data', 'indicators_data', 'signals_sent']:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    total_count = cursor.fetchone()[0]
                    tables_info[table] = {'total': total_count}
                    
                    if table == 'indicators_data':
                        # Contar con/sin close_price
                        cursor.execute("SELECT COUNT(*) FROM indicators_data WHERE close_price > 0")
                        with_price = cursor.fetchone()[0]
                        cursor.execute("SELECT COUNT(*) FROM indicators_data WHERE close_price IS NULL OR close_price = 0")
                        without_price = cursor.fetchone()[0]
                        tables_info[table]['with_price'] = with_price
                        tables_info[table]['without_price'] = without_price
                    
                    elif table == 'ohlcv_data':
                        # Símbolos y timeframes
                        cursor.execute("SELECT COUNT(DISTINCT symbol) FROM ohlcv_data")
                        symbols = cursor.fetchone()[0]
                        cursor.execute("SELECT COUNT(DISTINCT timeframe) FROM ohlcv_data WHERE timeframe IS NOT NULL")
                        timeframes = cursor.fetchone()[0]
                        tables_info[table]['symbols'] = symbols
                        tables_info[table]['timeframes'] = timeframes
                        
                        # Timeframes específicos
                        cursor.execute("SELECT timeframe, COUNT(*) FROM ohlcv_data WHERE timeframe IS NOT NULL GROUP BY timeframe")
                        timeframe_counts = dict(cursor.fetchall())
                        tables_info[table]['timeframe_breakdown'] = timeframe_counts
                
                except sqlite3.OperationalError:
                    tables_info[table] = {'error': 'Tabla no existe'}
            
            print(f"\n🗄️ TABLAS DE BASE DE DATOS:")
            
            # ohlcv_data
            ohlcv = tables_info.get('ohlcv_data', {})
            if 'error' not in ohlcv:
                print(f"   📊 ohlcv_data:")
                print(f"     Total registros: {ohlcv['total']:,}")
                print(f"     Símbolos únicos: {ohlcv.get('symbols', 0)}")
                print(f"     Timeframes: {ohlcv.get('timeframes', 0)}")
                
                timeframe_breakdown = ohlcv.get('timeframe_breakdown', {})
                if timeframe_breakdown:
                    print(f"     Breakdown por timeframe:")
                    for tf, count in timeframe_breakdown.items():
                        print(f"       • {tf}: {count:,} registros")
            else:
                print(f"   📊 ohlcv_data: {ohlcv['error']}")
            
            # indicators_data
            indicators = tables_info.get('indicators_data', {})
            if 'error' not in indicators:
                print(f"   📈 indicators_data:")
                print(f"     Total registros: {indicators['total']:,}")
                print(f"     Con precios: {indicators.get('with_price', 0):,}")
                print(f"     Sin precios: {indicators.get('without_price', 0):,}")
            else:
                print(f"   📈 indicators_data: {indicators['error']}")
            
            # signals_sent
            signals = tables_info.get('signals_sent', {})
            if 'error' not in signals:
                print(f"   📤 signals_sent:")
                print(f"     Total señales: {signals['total']:,}")
            else:
                print(f"   📤 signals_sent: {signals['error']}")
            
            conn.close()
            self.stats_before = {
                'csv_files': len(csv_files),
                'csv_size_mb': csv_size_mb,
                'tables': tables_info
            }
            
        except Exception as e:
            logger.error(f"❌ Error recopilando estadísticas: {e}")
    
    def create_backup(self):
        """Crear backup de la base de datos"""
        print(f"\n💾 CREANDO BACKUP DE SEGURIDAD")
        print("=" * 50)
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"trading_data_BEFORE_CLEANUP_{timestamp}.db"
            backup_path = self.db_path.parent / backup_name
            
            print(f"📁 Copiando base de datos...")
            shutil.copy2(self.db_path, backup_path)
            
            if backup_path.exists():
                backup_size = backup_path.stat().st_size / (1024 * 1024)
                print(f"✅ Backup creado exitosamente")
                print(f"   📍 Ubicación: {backup_path}")
                print(f"   📊 Tamaño: {backup_size:.2f} MB")
                self.backup_path = backup_path
                return str(backup_path)
            else:
                logger.error("❌ Error: Backup no se creó")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error creando backup: {e}")
            return None
    
    def clean_csv_files(self):
        """Borrar archivos CSV en raw_data/"""
        print(f"\n🧹 LIMPIANDO ARCHIVOS CSV")
        print("=" * 50)
        
        try:
            if not self.csv_dir.exists():
                print(f"📁 Directorio {self.csv_dir} no existe - nada que limpiar")
                return True
            
            csv_files = list(self.csv_dir.glob("*.csv"))
            
            if not csv_files:
                print(f"📁 No hay archivos CSV en {self.csv_dir}")
                return True
            
            print(f"🗑️ Encontrados {len(csv_files)} archivos CSV para borrar:")
            for i, csv_file in enumerate(csv_files[:5]):  # Mostrar solo primeros 5
                print(f"   {i+1}. {csv_file.name}")
            if len(csv_files) > 5:
                print(f"   ... y {len(csv_files) - 5} más")
            
            if not self.auto_confirm:
                confirm = input(f"\n⚠️ ¿Borrar {len(csv_files)} archivos CSV? (y/N): ").lower().strip()
                if confirm != 'y':
                    print("⏭️ Saltando limpieza de CSV")
                    return False
            
            deleted_count = 0
            for csv_file in csv_files:
                try:
                    csv_file.unlink()
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"⚠️ No se pudo borrar {csv_file.name}: {e}")
            
            print(f"✅ Borrados {deleted_count}/{len(csv_files)} archivos CSV")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error limpiando CSV: {e}")
            return False
    
    def clean_database_tables(self):
        """Limpiar tablas de la base de datos"""
        print(f"\n🧹 LIMPIANDO TABLAS DE BASE DE DATOS")
        print("=" * 50)
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 1. Vaciar ohlcv_data completamente
            print(f"🗑️ Vaciando tabla ohlcv_data...")
            cursor.execute("SELECT COUNT(*) FROM ohlcv_data")
            ohlcv_count = cursor.fetchone()[0]
            
            if ohlcv_count > 0:
                if not self.auto_confirm:
                    confirm = input(f"⚠️ ¿Borrar {ohlcv_count:,} registros de ohlcv_data? (y/N): ").lower().strip()
                    if confirm != 'y':
                        print("⏭️ Saltando limpieza de ohlcv_data")
                    else:
                        cursor.execute("DELETE FROM ohlcv_data")
                        print(f"✅ Borrados {ohlcv_count:,} registros de ohlcv_data")
                else:
                    cursor.execute("DELETE FROM ohlcv_data")
                    print(f"✅ Borrados {ohlcv_count:,} registros de ohlcv_data")
            else:
                print(f"📊 ohlcv_data ya está vacía")
            
            # 2. Borrar registros sin close_price en indicators_data
            print(f"\n🗑️ Limpiando indicators_data (registros sin close_price)...")
            cursor.execute("SELECT COUNT(*) FROM indicators_data WHERE close_price IS NULL OR close_price = 0")
            bad_indicators = cursor.fetchone()[0]
            
            if bad_indicators > 0:
                if not self.auto_confirm:
                    confirm = input(f"⚠️ ¿Borrar {bad_indicators:,} registros sin precios de indicators_data? (y/N): ").lower().strip()
                    if confirm != 'y':
                        print("⏭️ Saltando limpieza de indicators_data")
                    else:
                        cursor.execute("DELETE FROM indicators_data WHERE close_price IS NULL OR close_price = 0")
                        print(f"✅ Borrados {bad_indicators:,} registros sin precios")
                else:
                    cursor.execute("DELETE FROM indicators_data WHERE close_price IS NULL OR close_price = 0")
                    print(f"✅ Borrados {bad_indicators:,} registros sin precios")
            else:
                print(f"📊 No hay registros sin precios para borrar")
            
            # 3. Mantener signals_sent intacta
            cursor.execute("SELECT COUNT(*) FROM signals_sent")
            signals_count = cursor.fetchone()[0]
            print(f"\n✅ Manteniendo signals_sent intacta: {signals_count:,} señales preservadas")
            
            # Aplicar cambios
            conn.commit()
            
            # 4. Optimizar base de datos (recuperar espacio)
            print(f"\n🔧 Optimizando base de datos...")
            cursor.execute("VACUUM")
            conn.commit()
            print(f"✅ Base de datos optimizada")
            
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"❌ Error limpiando base de datos: {e}")
            return False
    
    def collect_stats_after(self):
        """Recopilar estadísticas después de la limpieza"""
        print("\n📊 ESTADÍSTICAS DESPUÉS DE LA LIMPIEZA")
        print("=" * 50)
        
        try:
            # CSV files
            csv_files = list(self.csv_dir.glob("*.csv")) if self.csv_dir.exists() else []
            print(f"📁 ARCHIVOS CSV:")
            print(f"   Archivos restantes: {len(csv_files)}")
            
            # Database tables
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            print(f"\n🗄️ TABLAS DE BASE DE DATOS:")
            
            for table in ['ohlcv_data', 'indicators_data', 'signals_sent']:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    print(f"   📊 {table}: {count:,} registros")
                    
                    if table == 'indicators_data' and count > 0:
                        cursor.execute("SELECT COUNT(*) FROM indicators_data WHERE close_price > 0")
                        with_price = cursor.fetchone()[0]
                        print(f"     (Con precios: {with_price:,})")
                        
                except sqlite3.OperationalError:
                    print(f"   📊 {table}: Tabla no existe")
            
            # Database size
            db_size = self.db_path.stat().st_size / (1024 * 1024)
            print(f"\n💾 Tamaño de base de datos: {db_size:.2f} MB")
            
            conn.close()
            
        except Exception as e:
            logger.error(f"❌ Error recopilando estadísticas finales: {e}")
    
    def run_complete_cleanup(self):
        """Ejecutar limpieza completa"""
        print("\n🧹 DATABASE CLEANER V1.0 - LIMPIEZA COMPLETA")
        print("=" * 70)
        print(f"🕐 Iniciando limpieza: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 1. Estadísticas iniciales
        self.collect_stats_before()
        
        # 2. Confirmación final
        if not self.auto_confirm:
            print(f"\n⚠️ ADVERTENCIA: Esta operación:")
            print(f"   • Borrará TODOS los archivos CSV en raw_data/")
            print(f"   • Vaciará COMPLETAMENTE la tabla ohlcv_data")
            print(f"   • Borrará registros sin precios de indicators_data")
            print(f"   • Mantendrá intacta la tabla signals_sent")
            
            confirm = input(f"\n🤔 ¿Continuar con la limpieza completa? (y/N): ").lower().strip()
            if confirm != 'y':
                print("❌ Limpieza cancelada por el usuario")
                return False
        
        # 3. Crear backup
        backup_created = self.create_backup()
        if not backup_created:
            if not self.auto_confirm:
                continue_anyway = input("⚠️ ¿Continuar sin backup? (y/N): ").lower().strip()
                if continue_anyway != 'y':
                    print("❌ Limpieza cancelada - no se pudo crear backup")
                    return False
        
        # 4. Limpiar archivos CSV
        csv_success = self.clean_csv_files()
        
        # 5. Limpiar base de datos
        db_success = self.clean_database_tables()
        
        # 6. Estadísticas finales
        self.collect_stats_after()
        
        # 7. Resumen final
        self.print_final_summary(csv_success, db_success)
        
        return csv_success and db_success
    
    def print_final_summary(self, csv_success: bool, db_success: bool):
        """Imprimir resumen final"""
        print(f"\n🏁 RESUMEN FINAL DE LIMPIEZA")
        print("=" * 50)
        
        print(f"📁 Archivos CSV: {'✅ Limpiados' if csv_success else '❌ Error'}")
        print(f"🗄️ Base de datos: {'✅ Limpiada' if db_success else '❌ Error'}")
        
        if self.backup_path:
            print(f"💾 Backup disponible: {self.backup_path.name}")
        
        if csv_success and db_success:
            print(f"\n🎉 ¡LIMPIEZA COMPLETADA EXITOSAMENTE!")
            print(f"\n📋 PRÓXIMOS PASOS RECOMENDADOS:")
            print(f"1. 📥 Descargar datos frescos (solo 15min):")
            print(f"   cd historical_data/")
            print(f"   python downloader.py --timeframe 15m")
            print(f"\n2. 💾 Poblar ohlcv_data:")
            print(f"   python populate_db.py")
            print(f"\n3. 📊 Calcular indicadores + precios:")
            print(f"   python historical_indicators_calc.py --force")
            print(f"\n4. 🧪 Crear backtesting engine")
        else:
            print(f"\n⚠️ Limpieza incompleta - revisar errores arriba")

def main():
    """Función principal"""
    parser = argparse.ArgumentParser(description='Database Cleaner V1.0 - Limpieza completa')
    parser.add_argument('--auto-confirm', action='store_true', 
                       help='Auto confirmar todas las acciones (no interactivo)')
    parser.add_argument('--backup-only', action='store_true', 
                       help='Solo crear backup, no limpiar')
    parser.add_argument('--show-stats', action='store_true', 
                       help='Solo mostrar estadísticas actuales')
    
    args = parser.parse_args()
    
    cleaner = DatabaseCleaner(auto_confirm=args.auto_confirm)
    
    if args.backup_only:
        backup_path = cleaner.create_backup()
        if backup_path:
            print(f"✅ Backup creado: {backup_path}")
        sys.exit(0)
    
    if args.show_stats:
        cleaner.collect_stats_before()
        sys.exit(0)
    
    # Ejecutar limpieza completa
    try:
        success = cleaner.run_complete_cleanup()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print(f"\n⚠️ Limpieza interrumpida por el usuario")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Error fatal en limpieza: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()