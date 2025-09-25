#!/usr/bin/env python3
"""
📊 DATABASE POSITION QUERIES - Consultas para Position Tracking
===============================================================

Consultas específicas para la tabla position_executions y análisis
del sistema de tracking granular de posiciones.

Funciones principales:
- CRUD de executions
- Consultas de estado de posiciones
- Análisis de performance por nivel
- Reporting y estadísticas
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import json
import os
import sys
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
        

class PositionQueries:
    """Clase para manejar consultas de position tracking"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def insert_execution(self, execution_data: Dict[str, Any]) -> bool:
        """
        Insertar nueva ejecución en la base de datos
        
        Args:
            execution_data: Diccionario con datos de la ejecución
            
        Returns:
            bool: True si la inserción fue exitosa
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # SQL de inserción
            insert_sql = """
            INSERT INTO position_executions 
            (symbol, position_id, level_id, execution_type, status,
             target_price, executed_price, quantity, percentage,
             created_at, executed_at, cancelled_at, description, 
             trigger_condition, notes, signal_strength, original_signal_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            values = (
                execution_data.get('symbol'),
                execution_data.get('position_id'),
                execution_data.get('level_id'),
                execution_data.get('execution_type'),
                execution_data.get('status'),
                execution_data.get('target_price'),
                execution_data.get('executed_price'),
                execution_data.get('quantity'),
                execution_data.get('percentage'),
                execution_data.get('created_at'),
                execution_data.get('executed_at'),
                execution_data.get('cancelled_at'),
                execution_data.get('description', ''),
                execution_data.get('trigger_condition', ''),
                execution_data.get('notes', ''),
                execution_data.get('signal_strength', 0),
                execution_data.get('original_signal_timestamp')
            )
            
            cursor.execute(insert_sql, values)
            conn.commit()
            
            execution_id = cursor.lastrowid
            conn.close()
            
            self.logger.info(f"✅ Ejecución insertada: ID {execution_id}, {execution_data.get('symbol')} {execution_data.get('execution_type')}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error insertando ejecución: {e}")
            return False
    
    def update_execution_status(self, execution_id: int, 
                               new_status: str, 
                               executed_price: Optional[float] = None,
                               executed_at: Optional[str] = None) -> bool:
        """
        Actualizar estado de una ejecución
        
        Args:
            execution_id: ID de la ejecución
            new_status: Nuevo estado
            executed_price: Precio de ejecución (opcional)
            executed_at: Timestamp de ejecución (opcional)
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Construir UPDATE dinámico
            update_fields = ['status = ?']
            values = [new_status]
            
            if executed_price is not None:
                update_fields.append('executed_price = ?')
                values.append(executed_price)
            
            if executed_at is not None:
                update_fields.append('executed_at = ?') 
                values.append(executed_at)
            
            values.append(execution_id)  # Para WHERE
            
            update_sql = f"""
            UPDATE position_executions 
            SET {', '.join(update_fields)}
            WHERE id = ?
            """
            
            cursor.execute(update_sql, values)
            rows_affected = cursor.rowcount
            conn.commit()
            conn.close()
            
            if rows_affected > 0:
                self.logger.info(f"✅ Ejecución {execution_id} actualizada: {new_status}")
                return True
            else:
                self.logger.warning(f"⚠️ Ejecución {execution_id} no encontrada")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Error actualizando ejecución {execution_id}: {e}")
            return False
    
    def get_position_executions(self, symbol: str, position_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Obtener todas las ejecuciones para una posición
        
        Args:
            symbol: Símbolo de la posición
            position_id: ID específico de posición (opcional)
        """
        try:
            conn = get_connection()
            conn.row_factory = sqlite3.Row  # Para acceso por nombre
            cursor = conn.cursor()
            
            if position_id:
                query = """
                SELECT * FROM position_executions 
                WHERE symbol = ? AND position_id = ?
                ORDER BY level_id ASC, created_at ASC
                """
                cursor.execute(query, (symbol, position_id))
            else:
                query = """
                SELECT * FROM position_executions 
                WHERE symbol = ?
                ORDER BY created_at DESC, level_id ASC
                """
                cursor.execute(query, (symbol,))
            
            rows = cursor.fetchall()
            conn.close()
            
            # Convertir a lista de diccionarios
            executions = []
            for row in rows:
                executions.append(dict(row))
            
            self.logger.debug(f"📊 Encontradas {len(executions)} ejecuciones para {symbol}")
            return executions
            
        except Exception as e:
            self.logger.error(f"❌ Error obteniendo ejecuciones {symbol}: {e}")
            return []
    
    def get_position_summary(self, symbol: str, position_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Obtener resumen calculado de una posición
        
        Args:
            symbol: Símbolo de la posición
            position_id: ID específico de posición (opcional)
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Query base
            base_where = "symbol = ?"
            params = [symbol]
            
            if position_id:
                base_where += " AND position_id = ?"
                params.append(position_id)
            
            # 1. Resumen de entradas
            entries_query = f"""
            SELECT 
                COUNT(*) as total_levels,
                COUNT(CASE WHEN status = 'FILLED' THEN 1 END) as filled_levels,
                COUNT(CASE WHEN status = 'PENDING' THEN 1 END) as pending_levels,
                COUNT(CASE WHEN status = 'CANCELLED' THEN 1 END) as cancelled_levels,
                SUM(CASE WHEN status = 'FILLED' THEN quantity ELSE 0 END) as total_shares,
                SUM(CASE WHEN status = 'FILLED' THEN executed_price * quantity ELSE 0 END) as total_invested,
                AVG(CASE WHEN status = 'FILLED' THEN executed_price END) as avg_entry_price
            FROM position_executions 
            WHERE {base_where} AND execution_type = 'ENTRY'
            """
            
            cursor.execute(entries_query, params)
            entry_stats = cursor.fetchone()
            
            # 2. Resumen de salidas
            exits_query = f"""
            SELECT 
                COUNT(*) as total_exit_levels,
                COUNT(CASE WHEN status = 'FILLED' THEN 1 END) as filled_exit_levels,
                SUM(CASE WHEN status = 'FILLED' THEN quantity ELSE 0 END) as shares_exited,
                SUM(CASE WHEN status = 'FILLED' THEN executed_price * quantity ELSE 0 END) as total_proceeds
            FROM position_executions 
            WHERE {base_where} AND execution_type IN ('EXIT', 'STOP_LOSS')
            """
            
            cursor.execute(exits_query, params)
            exit_stats = cursor.fetchone()
            
            # 3. Timing
            timing_query = f"""
            SELECT 
                MIN(created_at) as first_created,
                MAX(executed_at) as last_execution,
                COUNT(CASE WHEN executed_at IS NOT NULL THEN 1 END) as total_executions
            FROM position_executions 
            WHERE {base_where}
            """
            
            cursor.execute(timing_query, params)
            timing_stats = cursor.fetchone()
            
            # ✅ REMOVIDO: conn.close() - Se movió al final
            
            # Construir resumen
            total_shares = entry_stats[4] or 0
            shares_exited = exit_stats[2] or 0
            current_shares = total_shares - shares_exited
            
            total_invested = entry_stats[5] or 0.0
            avg_entry_price = entry_stats[6] or 0.0
            
            # Calcular progreso - CONSISTENTE con modelo de datos
            filled_levels = entry_stats[1] or 0
            total_levels = entry_stats[0] or 1
            
            # Progreso por shares (no por niveles) para consistencia
            all_entries_query = f"""
            SELECT SUM(quantity) as total_planned_shares
            FROM position_executions 
            WHERE {base_where} AND execution_type = 'ENTRY'
            """
            cursor.execute(all_entries_query, params)
            total_planned_result = cursor.fetchone()
            total_planned_shares = total_planned_result[0] if total_planned_result and total_planned_result[0] else 1
            
            cursor.execute(all_entries_query, params)
            total_planned_result = cursor.fetchone()
            total_planned_shares = total_planned_result[0] if total_planned_result and total_planned_result[0] else 1
            
            progress_pct = (total_shares / total_planned_shares * 100) if total_planned_shares > 0 else 0
            
            conn.close()  # ✅ MOVER AQUÍ - Cerrar conexión después de todas las queries
            
            summary = {
                'symbol': symbol,
                'position_id': position_id,
                
                # Entradas
                'entry_levels': {
                    'total': entry_stats[0],
                    'filled': entry_stats[1], 
                    'pending': entry_stats[2],
                    'cancelled': entry_stats[3]
                },
                
                # Shares y precios
                'shares': {
                    'total_acquired': total_shares,
                    'current_position': current_shares,
                    'exited': shares_exited
                },
                
                'prices': {
                    'average_entry': avg_entry_price,
                    'total_invested': total_invested
                },
                
                # Salidas
                'exit_levels': {
                    'total': exit_stats[0],
                    'filled': exit_stats[1],
                    'total_proceeds': exit_stats[3] or 0.0
                },
                
                # Progreso y timing
                'progress': {
                    'fill_percentage': progress_pct,
                    'levels_progress': f"{filled_levels}/{entry_stats[0] or 0}"
                },
                
                'timing': {
                    'first_created': timing_stats[0],
                    'last_execution': timing_stats[1], 
                    'total_executions': timing_stats[2]
                },
                
                'generated_at': datetime.now().isoformat()
            }
            
            return summary
            
        except Exception as e:
            self.logger.error(f"❌ Error obteniendo resumen {symbol}: {e}")
            return {}
    
    def get_active_positions(self) -> List[Dict[str, Any]]:
        """
        Obtener todas las posiciones activas (con ejecuciones pero no completamente cerradas)
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Query para encontrar posiciones con entradas pero no completamente salidas
            query = """
            SELECT DISTINCT symbol, position_id
            FROM position_executions 
            WHERE execution_type = 'ENTRY' AND status = 'FILLED'
            AND symbol NOT IN (
                SELECT DISTINCT symbol 
                FROM position_executions 
                WHERE execution_type IN ('EXIT', 'STOP_LOSS') 
                AND status = 'FILLED'
                GROUP BY symbol
                HAVING SUM(quantity) >= (
                    SELECT SUM(quantity) 
                    FROM position_executions e2 
                    WHERE e2.symbol = position_executions.symbol 
                    AND e2.execution_type = 'ENTRY' 
                    AND e2.status = 'FILLED'
                )
            )
            ORDER BY symbol
            """
            
            cursor.execute(query)
            active_positions = cursor.fetchall()
            conn.close()
            
            # Obtener resumen para cada posición activa
            results = []
            for symbol, position_id in active_positions:
                summary = self.get_position_summary(symbol, position_id)
                if summary:
                    results.append(summary)
            
            self.logger.info(f"📊 Encontradas {len(results)} posiciones activas")
            return results
            
        except Exception as e:
            self.logger.error(f"❌ Error obteniendo posiciones activas: {e}")
            return []
    
    def get_execution_statistics(self, days: int = 30) -> Dict[str, Any]:
        """
        Obtener estadísticas de ejecuciones de los últimos N días
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            # Estadísticas generales
            stats_query = """
            SELECT 
                COUNT(*) as total_executions,
                COUNT(DISTINCT symbol) as unique_symbols,
                COUNT(CASE WHEN status = 'FILLED' THEN 1 END) as filled_executions,
                COUNT(CASE WHEN status = 'PENDING' THEN 1 END) as pending_executions,
                COUNT(CASE WHEN status = 'CANCELLED' THEN 1 END) as cancelled_executions,
                COUNT(CASE WHEN execution_type = 'ENTRY' THEN 1 END) as entry_executions,
                COUNT(CASE WHEN execution_type = 'EXIT' THEN 1 END) as exit_executions
            FROM position_executions 
            WHERE created_at >= ?
            """
            
            cursor.execute(stats_query, (cutoff_date,))
            general_stats = cursor.fetchone()
            
            # Por símbolo
            symbol_query = """
            SELECT 
                symbol,
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'FILLED' THEN 1 END) as filled,
                AVG(CASE WHEN status = 'FILLED' AND executed_price IS NOT NULL THEN executed_price END) as avg_price
            FROM position_executions 
            WHERE created_at >= ?
            GROUP BY symbol
            ORDER BY total DESC
            LIMIT 10
            """
            
            cursor.execute(symbol_query, (cutoff_date,))
            by_symbol = cursor.fetchall()
            
            conn.close()
            
            # Calcular métricas
            total = general_stats[0]
            filled = general_stats[2]
            fill_rate = (filled / total * 100) if total > 0 else 0
            
            return {
                'period_days': days,
                'cutoff_date': cutoff_date,
                
                'totals': {
                    'executions': total,
                    'symbols': general_stats[1],
                    'filled': filled,
                    'pending': general_stats[3],
                    'cancelled': general_stats[4],
                    'entries': general_stats[5],
                    'exits': general_stats[6]
                },
                
                'rates': {
                    'fill_rate': round(fill_rate, 1),
                    'cancel_rate': round((general_stats[4] / total * 100) if total > 0 else 0, 1)
                },
                
                'by_symbol': [
                    {
                        'symbol': row[0],
                        'total_executions': row[1], 
                        'filled_executions': row[2],
                        'avg_price': round(row[3], 2) if row[3] else None
                    }
                    for row in by_symbol
                ],
                
                'generated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"❌ Error obteniendo estadísticas: {e}")
            return {}
    
    def cleanup_old_executions(self, days: int = 90) -> int:
        """
        Limpiar ejecuciones antiguas (solo las canceladas y completadas)
        
        Returns:
            int: Número de registros eliminados
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            # Solo eliminar registros completamente cerrados o cancelados
            cleanup_query = """
            DELETE FROM position_executions 
            WHERE created_at < ? 
            AND status IN ('CANCELLED')
            AND symbol NOT IN (
                SELECT DISTINCT symbol FROM position_executions 
                WHERE status = 'PENDING' OR status = 'FILLED'
            )
            """
            
            cursor.execute(cleanup_query, (cutoff_date,))
            deleted_count = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"🧹 Eliminados {deleted_count} registros antiguos")
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"❌ Error en cleanup: {e}")
            return 0


# Instancia global para fácil acceso
position_queries = PositionQueries()


if __name__ == "__main__":
    # Demo de uso
    print("📊 POSITION QUERIES - Demo")
    print("=" * 40)
    
    pq = PositionQueries()
    
    # Test 1: Insertar ejecución de prueba
    test_execution = {
        'symbol': 'DEMO',
        'position_id': 'DEMO_001',
        'level_id': 1,
        'execution_type': 'ENTRY',
        'status': 'PENDING',
        'target_price': 150.0,
        'quantity': 100,
        'percentage': 50.0,
        'created_at': datetime.now().isoformat(),
        'description': 'Demo entry level 1'
    }
    
    print("📥 Insertando ejecución de prueba...")
    success = pq.insert_execution(test_execution)
    print(f"   Resultado: {'✅ Exitoso' if success else '❌ Error'}")
    
    # Test 2: Obtener ejecuciones
    print(f"\n📊 Obteniendo ejecuciones para DEMO...")
    executions = pq.get_position_executions('DEMO')
    print(f"   Encontradas: {len(executions)} ejecuciones")
    
    if executions:
        exec_data = executions[0]
        print(f"   Primera: ID {exec_data['id']}, {exec_data['status']}")
    
    # Test 3: Actualizar estado
    if executions:
        exec_id = executions[0]['id']
        print(f"\n🔄 Actualizando ejecución {exec_id} a FILLED...")
        success = pq.update_execution_status(exec_id, 'FILLED', 150.05, datetime.now().isoformat())
        print(f"   Resultado: {'✅ Exitoso' if success else '❌ Error'}")
    
    # Test 4: Resumen de posición
    print(f"\n📈 Obteniendo resumen de posición DEMO...")
    summary = pq.get_position_summary('DEMO')
    
    if summary:
        print(f"   Shares totales: {summary['shares']['total_acquired']}")
        print(f"   Precio promedio: ${summary['prices']['average_entry']:.2f}")
        print(f"   Progreso: {summary['progress']['fill_percentage']:.1f}%")
    
    # Test 5: Estadísticas
    print(f"\n📊 Estadísticas generales...")
    stats = pq.get_execution_statistics(30)
    
    if stats:
        print(f"   Total ejecuciones (30d): {stats['totals']['executions']}")
        print(f"   Tasa de ejecución: {stats['rates']['fill_rate']}%")
        print(f"   Símbolos únicos: {stats['totals']['symbols']}")
    
    # Cleanup del test
    print(f"\n🧹 Limpiando datos de prueba...")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM position_executions WHERE symbol = 'DEMO'")
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        print(f"   Eliminados: {deleted} registros de prueba")
    except Exception as e:
        print(f"   Error cleanup: {e}")