#!/usr/bin/env python3
"""
🗄️ DATABASE MIGRATION - Position Tracking V3.0
===============================================

Migración para agregar tracking granular de ejecuciones de posiciones.

Agrega tabla 'position_executions' para tracking detallado de:
- Entradas escalonadas (nivel por nivel)
- Salidas escalonadas (nivel por nivel)  
- Estados de cada nivel (PENDING, FILLED, CANCELLED)
- Precios de ejecución reales vs objetivos
- Timestamps de ejecución
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime
from pathlib import Path

# Configurar paths
current_dir = Path(__file__).parent.absolute()
project_root = current_dir.parent
sys.path.insert(0, str(project_root))

try:
    from database.connection import get_connection, DB_PATH
    logger = logging.getLogger(__name__)
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    DB_PATH = "database/trading_data.db"
    
    def get_connection():
        """Función de respaldo para conexión"""
        return sqlite3.connect(DB_PATH)


class PositionTrackingMigration:
    """Clase para manejar la migración de position tracking"""
    
    def __init__(self):
        self.migration_version = "3.0"
        self.migration_name = "position_tracking"
        self.backup_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def check_current_schema(self) -> dict:
        """Verificar el estado actual de la base de datos"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Listar todas las tablas
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            
            # Verificar si la tabla position_executions ya existe
            has_position_executions = 'position_executions' in tables
            
            # Contar registros en tablas existentes
            table_counts = {}
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                table_counts[table] = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'tables': tables,
                'has_position_executions': has_position_executions,
                'table_counts': table_counts,
                'needs_migration': not has_position_executions
            }
            
        except Exception as e:
            logger.error(f"❌ Error verificando schema: {e}")
            return {'error': str(e)}
    
    def backup_database(self) -> str:
        """Crear backup de la base de datos antes de migrar"""
        try:
            if not os.path.exists(DB_PATH):
                logger.warning("⚠️ Base de datos no existe, no se puede hacer backup")
                return ""
            
            backup_path = f"{DB_PATH}.backup_{self.backup_suffix}"
            
            # Copiar archivo
            import shutil
            shutil.copy2(DB_PATH, backup_path)
            
            backup_size = os.path.getsize(backup_path)
            logger.info(f"💾 Backup creado: {backup_path} ({backup_size} bytes)")
            
            return backup_path
            
        except Exception as e:
            logger.error(f"❌ Error creando backup: {e}")
            return ""
    
    def create_position_executions_table(self) -> bool:
        """Crear tabla position_executions"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # SQL para crear la tabla
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS position_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                
                -- Identificación
                symbol TEXT NOT NULL,
                position_id TEXT,
                level_id INTEGER NOT NULL,
                
                -- Tipo y estado
                execution_type TEXT NOT NULL, -- 'ENTRY', 'EXIT', 'STOP_LOSS', 'TRAILING_STOP'
                status TEXT NOT NULL,         -- 'PENDING', 'FILLED', 'PARTIALLY_FILLED', 'CANCELLED'
                
                -- Precios y cantidades
                target_price REAL NOT NULL,
                executed_price REAL,
                quantity INTEGER NOT NULL,
                percentage REAL NOT NULL,     -- % del total de la posición
                
                -- Timing
                created_at TEXT NOT NULL,
                executed_at TEXT,
                cancelled_at TEXT,
                
                -- Metadatos
                description TEXT DEFAULT '',
                trigger_condition TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                
                -- Referencias adicionales
                signal_strength INTEGER DEFAULT 0,
                original_signal_timestamp TEXT,
                
                created_at_db TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at_db TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
            
            cursor.execute(create_table_sql)
            
            # Crear índices para optimizar consultas
            indices = [
                "CREATE INDEX IF NOT EXISTS idx_position_executions_symbol ON position_executions(symbol)",
                "CREATE INDEX IF NOT EXISTS idx_position_executions_position_id ON position_executions(position_id)",
                "CREATE INDEX IF NOT EXISTS idx_position_executions_status ON position_executions(status)",
                "CREATE INDEX IF NOT EXISTS idx_position_executions_type ON position_executions(execution_type)",
                "CREATE INDEX IF NOT EXISTS idx_position_executions_symbol_status ON position_executions(symbol, status)",
                "CREATE INDEX IF NOT EXISTS idx_position_executions_created_at ON position_executions(created_at)"
            ]
            
            for index_sql in indices:
                cursor.execute(index_sql)
            
            # Crear trigger para updated_at automático
            trigger_sql = """
            CREATE TRIGGER IF NOT EXISTS update_position_executions_timestamp 
            AFTER UPDATE ON position_executions
            FOR EACH ROW
            BEGIN
                UPDATE position_executions 
                SET updated_at_db = CURRENT_TIMESTAMP 
                WHERE id = NEW.id;
            END
            """
            
            cursor.execute(trigger_sql)
            
            conn.commit()
            conn.close()
            
            logger.info("✅ Tabla position_executions creada exitosamente")
            logger.info("📑 6 índices creados para optimizar consultas")
            logger.info("⚡ Trigger de timestamp automático configurado")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error creando tabla position_executions: {e}")
            return False
    
    def verify_migration(self) -> bool:
        """Verificar que la migración fue exitosa"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # 1. Verificar que la tabla existe
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='position_executions'
            """)
            
            if not cursor.fetchone():
                logger.error("❌ Tabla position_executions no fue creada")
                return False
            
            # 2. Verificar estructura de la tabla
            cursor.execute("PRAGMA table_info(position_executions)")
            columns = cursor.fetchall()
            
            expected_columns = {
                'id', 'symbol', 'position_id', 'level_id', 'execution_type', 
                'status', 'target_price', 'executed_price', 'quantity', 
                'percentage', 'created_at', 'executed_at', 'cancelled_at',
                'description', 'trigger_condition', 'notes', 'signal_strength',
                'original_signal_timestamp', 'created_at_db', 'updated_at_db'
            }
            
            actual_columns = {col[1] for col in columns}
            
            if not expected_columns.issubset(actual_columns):
                missing_columns = expected_columns - actual_columns
                logger.error(f"❌ Columnas faltantes: {missing_columns}")
                return False
            
            # 3. Verificar índices
            cursor.execute("PRAGMA index_list(position_executions)")
            indices = cursor.fetchall()
            
            # 4. Test de inserción básica
            test_data = {
                'symbol': 'TEST',
                'position_id': 'TEST_001',
                'level_id': 1,
                'execution_type': 'ENTRY',
                'status': 'PENDING',
                'target_price': 100.0,
                'quantity': 100,
                'percentage': 50.0,
                'created_at': datetime.now().isoformat(),
                'description': 'Migration test entry'
            }
            
            cursor.execute("""
                INSERT INTO position_executions 
                (symbol, position_id, level_id, execution_type, status, 
                 target_price, quantity, percentage, created_at, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, tuple(test_data.values()))
            
            # Verificar inserción
            cursor.execute("SELECT COUNT(*) FROM position_executions WHERE symbol = 'TEST'")
            test_count = cursor.fetchone()[0]
            
            # Limpiar test data
            cursor.execute("DELETE FROM position_executions WHERE symbol = 'TEST'")
            
            conn.commit()
            conn.close()
            
            if test_count == 1:
                logger.info("✅ Migración verificada exitosamente")
                logger.info(f"📊 Tabla tiene {len(actual_columns)} columnas")
                logger.info(f"📑 {len(indices)} índices configurados")
                return True
            else:
                logger.error("❌ Error en test de inserción")
                return False
            
        except Exception as e:
            logger.error(f"❌ Error verificando migración: {e}")
            return False
    
    def run_migration(self, force: bool = False) -> bool:
        """Ejecutar migración completa"""
        try:
            logger.info(f"🚀 Iniciando migración: {self.migration_name} v{self.migration_version}")
            
            # 1. Verificar estado actual
            current_schema = self.check_current_schema()
            
            if 'error' in current_schema:
                logger.error(f"❌ Error verificando schema: {current_schema['error']}")
                return False
            
            if current_schema['has_position_executions'] and not force:
                logger.warning("⚠️ Tabla position_executions ya existe")
                response = input("¿Continuar anyway? (y/N): ").lower().strip()
                if response != 'y':
                    logger.info("🛑 Migración cancelada")
                    return False
            
            # 2. Crear backup
            backup_path = self.backup_database()
            if not backup_path and os.path.exists(DB_PATH):
                logger.warning("⚠️ No se pudo crear backup, pero continuando...")
            
            # 3. Ejecutar migración
            logger.info("📊 Creando tabla position_executions...")
            if not self.create_position_executions_table():
                logger.error("❌ Fallo la creación de tabla")
                return False
            
            # 4. Verificar migración
            logger.info("🔍 Verificando migración...")
            if not self.verify_migration():
                logger.error("❌ Verificación de migración falló")
                return False
            
            logger.info("🎉 ¡MIGRACIÓN COMPLETADA EXITOSAMENTE!")
            
            if backup_path:
                logger.info(f"💾 Backup disponible en: {backup_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"💥 Error crítico en migración: {e}")
            return False


def main():
    """Función principal para ejecutar migración"""
    print("🗄️ DATABASE MIGRATION - Position Tracking V3.0")
    print("=" * 60)
    
    migration = PositionTrackingMigration()
    
    # Modo interactivo
    if len(sys.argv) == 1:
        print("\n📋 OPCIONES:")
        print("1. Verificar estado actual")
        print("2. Ejecutar migración")
        print("3. Solo verificar (después de migración)")
        
        choice = input("\nElige opción (1-3): ").strip()
        
        if choice == "1":
            schema = migration.check_current_schema()
            print(f"\n📊 ESTADO ACTUAL:")
            print(f"   Tablas: {len(schema.get('tables', []))}")
            print(f"   Tiene position_executions: {schema.get('has_position_executions', False)}")
            print(f"   Necesita migración: {schema.get('needs_migration', True)}")
            
        elif choice == "2":
            success = migration.run_migration()
            if success:
                print("\n✅ ¡Migración exitosa!")
            else:
                print("\n❌ Migración falló")
                
        elif choice == "3":
            success = migration.verify_migration()
            if success:
                print("\n✅ Verificación exitosa")
            else:
                print("\n❌ Verificación falló")
    
    # Modo comando
    elif len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command in ['migrate', 'run']:
            force = '--force' in sys.argv
            success = migration.run_migration(force=force)
            return 0 if success else 1
            
        elif command in ['verify', 'check']:
            success = migration.verify_migration()
            return 0 if success else 1
            
        elif command in ['status', 'info']:
            schema = migration.check_current_schema()
            print(schema)
            return 0
            
        else:
            print("❌ Comando no reconocido")
            print("Uso: python migration_position_tracking.py [migrate|verify|status]")
            return 1


if __name__ == "__main__":
    if len(sys.argv) > 1:
        exit_code = main()
        sys.exit(exit_code)
    else:
        main()