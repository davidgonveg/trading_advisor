#!/usr/bin/env python3
"""
🔧 FIX GAPS PERSISTENCE - Solución para gaps que se detectan repetidamente
===========================================================================

Este script soluciona dos problemas:
1. Gaps se detectan pero no se marcan como "rellenados" en DB
2. ExitManager no tiene método add_position_from_signal()

CAMBIOS NECESARIOS:
- Agregar funciones en database/connection.py para marcar gaps
- Modificar indicators.py para persistir gaps rellenados
- Agregar método en ExitManager para registrar posiciones
"""

import sqlite3
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# 🔧 FIX 1: FUNCIONES PARA DATABASE/CONNECTION.PY
# =============================================================================

def mark_gap_as_filled(symbol: str, gap_start: datetime, gap_end: datetime, 
                       fill_method: str = 'REAL_DATA', bars_added: int = 0) -> bool:
    """
    Marcar un gap como rellenado en la base de datos
    
    Esta función DEBE agregarse a database/connection.py
    
    Args:
        symbol: Símbolo del activo
        gap_start: Timestamp inicio del gap
        gap_end: Timestamp fin del gap
        fill_method: Método usado (REAL_DATA, WORST_CASE, PRESERVED)
        bars_added: Número de barras agregadas
        
    Returns:
        True si se marcó exitosamente
    """
    try:
        from database.connection import get_connection
        
        conn = get_connection()
        if not conn:
            logger.warning("⚠️ No hay conexión a DB, gap no se persistirá")
            return False
        
        cursor = conn.cursor()
        
        # Verificar si ya existe registro del gap
        cursor.execute('''
        SELECT id FROM gap_fills 
        WHERE symbol = ? AND gap_start = ? AND gap_end = ?
        ''', (symbol, gap_start.isoformat(), gap_end.isoformat()))
        
        existing = cursor.fetchone()
        
        if existing:
            # Actualizar registro existente
            cursor.execute('''
            UPDATE gap_fills 
            SET fill_method = ?, 
                bars_added = ?,
                last_updated = ?,
                fill_count = fill_count + 1
            WHERE id = ?
            ''', (fill_method, bars_added, datetime.now().isoformat(), existing[0]))
        else:
            # Crear nuevo registro
            cursor.execute('''
            INSERT INTO gap_fills (
                symbol, gap_start, gap_end, fill_method, 
                bars_added, filled_at, fill_count
            ) VALUES (?, ?, ?, ?, ?, ?, 1)
            ''', (
                symbol, 
                gap_start.isoformat(), 
                gap_end.isoformat(),
                fill_method,
                bars_added,
                datetime.now().isoformat()
            ))
        
        conn.commit()
        conn.close()
        
        logger.debug(f"✅ Gap marcado como rellenado: {symbol} ({gap_start} -> {gap_end})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error marcando gap como rellenado: {e}")
        return False


def get_filled_gaps(symbol: str, days_back: int = 30) -> list:
    """
    Obtener gaps ya rellenados para un símbolo
    
    Esta función DEBE agregarse a database/connection.py
    
    Args:
        symbol: Símbolo del activo
        days_back: Días hacia atrás a consultar
        
    Returns:
        Lista de diccionarios con gaps rellenados
    """
    try:
        from database.connection import get_connection
        
        conn = get_connection()
        if not conn:
            return []
        
        cursor = conn.cursor()
        
        # Obtener gaps rellenados en los últimos N días
        cutoff = datetime.now() - timedelta(days=days_back)
        
        cursor.execute('''
        SELECT symbol, gap_start, gap_end, fill_method, bars_added, 
               filled_at, fill_count, last_updated
        FROM gap_fills
        WHERE symbol = ? AND filled_at >= ?
        ORDER BY filled_at DESC
        ''', (symbol, cutoff.isoformat()))
        
        rows = cursor.fetchall()
        conn.close()
        
        # Convertir a lista de diccionarios
        filled_gaps = []
        for row in rows:
            filled_gaps.append({
                'symbol': row[0],
                'gap_start': datetime.fromisoformat(row[1]),
                'gap_end': datetime.fromisoformat(row[2]),
                'fill_method': row[3],
                'bars_added': row[4],
                'filled_at': datetime.fromisoformat(row[5]),
                'fill_count': row[6],
                'last_updated': datetime.fromisoformat(row[7]) if row[7] else None
            })
        
        return filled_gaps
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo gaps rellenados: {e}")
        return []


def create_gap_fills_table():
    """
    Crear tabla gap_fills si no existe
    
    Esta función DEBE agregarse a database/connection.py y 
    ejecutarse en init_database()
    """
    try:
        from database.connection import get_connection
        
        conn = get_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS gap_fills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            gap_start TIMESTAMP NOT NULL,
            gap_end TIMESTAMP NOT NULL,
            fill_method TEXT NOT NULL,
            bars_added INTEGER DEFAULT 0,
            filled_at TIMESTAMP NOT NULL,
            fill_count INTEGER DEFAULT 1,
            last_updated TIMESTAMP,
            UNIQUE(symbol, gap_start, gap_end)
        )
        ''')
        
        # Índice para búsquedas rápidas
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_gap_fills_symbol_date 
        ON gap_fills(symbol, filled_at)
        ''')
        
        conn.commit()
        conn.close()
        
        logger.info("✅ Tabla gap_fills creada/verificada")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error creando tabla gap_fills: {e}")
        return False


# =============================================================================
# 🔧 FIX 2: MODIFICACIÓN PARA INDICATORS.PY
# =============================================================================

def get_indicators_fix_code():
    """
    Código que debe agregarse en indicators.py después de rellenar cada gap
    """
    fix_code = '''
# En indicators.py, método _detect_and_fill_gaps_v32()
# Después de la línea: filled_data = pd.concat([filled_data, filled_rows]).sort_index()

# ✅ AGREGAR ESTO:
try:
    from database.connection import mark_gap_as_filled
    
    # Determinar método usado
    fill_method = 'REAL_DATA' if len(filled_rows) > 0 else 'PRESERVED'
    
    # Marcar gap como rellenado en DB
    mark_gap_as_filled(
        symbol=symbol,
        gap_start=gap['start'],
        gap_end=gap['end'],
        fill_method=fill_method,
        bars_added=len(filled_rows)
    )
    
    logger.debug(f"💾 {symbol}: Gap persistido en DB")
    
except ImportError:
    logger.warning("⚠️ mark_gap_as_filled no disponible")
except Exception as persist_error:
    logger.warning(f"⚠️ {symbol}: No se pudo persistir gap: {persist_error}")
'''
    return fix_code


# =============================================================================
# 🔧 FIX 3: MÉTODO PARA EXIT_MANAGER
# =============================================================================

def get_exit_manager_fix_code():
    """
    Código que debe agregarse a exit_manager.py
    """
    fix_code = '''
# En exit_manager.py, clase ExitManager

def add_position_from_signal(self, signal, plan) -> bool:
    """
    Registrar nueva posición desde señal del scanner
    
    Args:
        signal: TradingSignal del scanner
        plan: PositionPlan del position_calculator
        
    Returns:
        True si se registró exitosamente
    """
    try:
        # Crear registro de posición activa
        position_data = {
            'symbol': signal.symbol,
            'direction': signal.signal_type,  # LONG/SHORT
            'signal_strength': signal.signal_strength,
            'entry_price': plan.entries[0].price if plan.entries else signal.current_price,
            'stop_loss': plan.stop_loss.price,
            'opened_at': datetime.now(),
            'status': 'ACTIVE'
        }
        
        # Agregar a posiciones activas
        if signal.symbol not in self.active_positions:
            self.active_positions[signal.symbol] = position_data
            logger.info(f"✅ Posición registrada: {signal.symbol} {signal.signal_type}")
            return True
        else:
            logger.warning(f"⚠️ {signal.symbol} ya tiene posición activa")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error registrando posición: {e}")
        return False
'''
    return fix_code


# =============================================================================
# 🧪 SCRIPT DE MIGRACIÓN
# =============================================================================

def run_migration():
    """
    Ejecutar migración para agregar tabla gap_fills
    """
    print("🔧 MIGRACIÓN: Agregando tabla gap_fills")
    print("=" * 60)
    
    # Crear tabla
    if create_gap_fills_table():
        print("✅ Tabla gap_fills creada exitosamente")
        
        # Test básico
        print("\n🧪 Testing funcionalidad...")
        test_gap_start = datetime.now()
        test_gap_end = test_gap_start + timedelta(hours=4)
        
        if mark_gap_as_filled('TEST', test_gap_start, test_gap_end, 'REAL_DATA', 16):
            print("✅ Test mark_gap_as_filled: OK")
            
            filled = get_filled_gaps('TEST', 1)
            if len(filled) > 0:
                print(f"✅ Test get_filled_gaps: OK ({len(filled)} gaps)")
            else:
                print("❌ Test get_filled_gaps: FALLÓ")
        else:
            print("❌ Test mark_gap_as_filled: FALLÓ")
    else:
        print("❌ Error creando tabla gap_fills")
    
    print("\n" + "=" * 60)
    print("📋 PASOS SIGUIENTES:")
    print("1. Agregar las 3 funciones a database/connection.py:")
    print("   - mark_gap_as_filled()")
    print("   - get_filled_gaps()")
    print("   - create_gap_fills_table()")
    print("")
    print("2. En database/connection.py, en init_database() agregar:")
    print("   create_gap_fills_table()")
    print("")
    print("3. En indicators.py, después de rellenar cada gap agregar:")
    print("   mark_gap_as_filled(symbol, gap['start'], gap['end'], ...)")
    print("")
    print("4. En exit_manager.py agregar método:")
    print("   add_position_from_signal(signal, plan)")
    print("")
    print("5. Reiniciar el sistema")


if __name__ == "__main__":
    from datetime import timedelta
    run_migration()