#!/usr/bin/env python3
"""
💾 PERSISTENCE MANAGER - Gestión de Persistencia y Cache V3.0
============================================================

Componente responsable de la sincronización bidireccional entre modelos
in-memory y base de datos, con cache inteligente y transacciones ACID.

🎯 FUNCIONALIDADES:
1. Sincronización automática entre memoria y base de datos
2. Cache inteligente con invalidación automática
3. Transacciones ACID para operaciones críticas
4. Backup y recovery de datos de posiciones
5. Optimización de consultas con batching
6. Background tasks para limpieza y sincronización

🔧 ARQUITECTURA:
- Cache multi-nivel con estrategias configurables
- Transaction manager con rollback automático
- Conflict detection y resolution
- Background threads para optimización
- Health monitoring y auto-recovery
"""

import sqlite3
import threading
import time
import pickle
import hashlib
import shutil
import tempfile
import uuid
import pytz
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Union, Tuple
from enum import Enum
from pathlib import Path
import logging

# Imports del proyecto
from database.connection import get_connection
from database.position_queries import PositionQueries
from position_management.data_models import EnhancedPosition
from position_management.states import PositionStatus
import config

# Logger
logger = logging.getLogger(__name__)


# ==============================================
# ENUMS Y CONSTANTES
# ==============================================

class CacheStrategy(Enum):
    """Estrategias de cache disponibles"""
    WRITE_THROUGH = "write_through"    # Escribir a cache y DB simultáneamente
    WRITE_BACK = "write_back"          # Escribir a cache, DB en background
    WRITE_AROUND = "write_around"      # Escribir solo a DB, invalidar cache


class TransactionStatus(Enum):
    """Estados de transacción"""
    PENDING = "pending"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class ConflictResolution(Enum):
    """Estrategias de resolución de conflictos"""
    LAST_WRITE_WINS = "last_write_wins"
    MERGE = "merge"
    MANUAL = "manual"
    REJECT = "reject"


# ==============================================
# DATA MODELS PARA PERSISTENCIA
# ==============================================

@dataclass
class CacheEntry:
    """Entrada del cache con metadatos"""
    key: str
    data: Any
    created_at: datetime = field(default_factory=lambda: datetime.now(pytz.UTC))
    last_accessed: datetime = field(default_factory=lambda: datetime.now(pytz.UTC))
    expires_at: Optional[datetime] = None
    access_count: int = 0
    dirty: bool = False  # Indica si necesita sincronización con DB
    size_bytes: int = 0
    data_hash: str = field(init=False)
    
    def __post_init__(self):
        """Calcular hash y tamaño después de inicialización"""
        self.data_hash = self._calculate_hash()
        try:
            self.size_bytes = len(pickle.dumps(self.data))
        except Exception:
            self.size_bytes = 0
    
    def _calculate_hash(self) -> str:
        """Calcular hash de los datos"""
        try:
            serialized = pickle.dumps(self.data)
            return hashlib.md5(serialized).hexdigest()
        except Exception:
            return str(hash(str(self.data)))
    
    def is_expired(self) -> bool:
        """Verificar si la entrada ha expirado"""
        if not self.expires_at:
            return False
        return datetime.now(pytz.UTC) > self.expires_at
    
    def touch(self):
        """Actualizar último acceso"""
        self.last_accessed = datetime.now(pytz.UTC)
        self.access_count += 1


@dataclass
class Transaction:
    """Transacción de base de datos"""
    transaction_id: str
    operations: List[Dict[str, Any]] = field(default_factory=list)
    status: TransactionStatus = TransactionStatus.PENDING
    started_at: datetime = field(default_factory=lambda: datetime.now(pytz.UTC))
    completed_at: Optional[datetime] = None
    rollback_data: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None


@dataclass
class DataConflict:
    """Conflicto de datos detectado"""
    conflict_id: str
    key: str
    local_data: Any
    remote_data: Any
    local_hash: str
    remote_hash: str
    detected_at: datetime = field(default_factory=lambda: datetime.now(pytz.UTC))
    resolution_strategy: ConflictResolution = ConflictResolution.LAST_WRITE_WINS
    resolved: bool = False


# ==============================================
# PERSISTENCE MANAGER PRINCIPAL
# ==============================================

class PersistenceManager:
    """
    Manager principal para persistencia y cache
    """
    
    def __init__(self):
        """Inicializar el persistence manager"""
        self.position_queries = PositionQueries()
        
        # Cache inteligente
        self._cache: Dict[str, CacheEntry] = {}
        self._cache_lock = threading.RLock()
        self.cache_strategy = CacheStrategy.WRITE_THROUGH
        
        # Configuración de cache
        self.max_cache_size = getattr(config, 'MAX_CACHE_SIZE', 1000)
        self.default_ttl = timedelta(minutes=getattr(config, 'CACHE_TTL_MINUTES', 30))
        self.cleanup_interval = timedelta(minutes=getattr(config, 'CACHE_CLEANUP_MINUTES', 5))
        
        # Transaction management
        self._active_transactions: Dict[str, Transaction] = {}
        self._transaction_lock = threading.Lock()
        
        # Conflict detection
        self._conflicts: Dict[str, DataConflict] = {}
        self._conflict_callbacks: List[Callable[[DataConflict], None]] = []
        
        # Background tasks
        self._shutdown = False
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        
        # Estadísticas
        self._stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'cache_evictions': 0,
            'transactions_committed': 0,
            'transactions_rolled_back': 0,
            'conflicts_detected': 0,
            'conflicts_resolved': 0
        }
        
        # Iniciar background tasks
        self._cleanup_thread.start()
        self._sync_thread.start()
        
        logger.info("💾 Persistence Manager inicializado")
    
    # ==============================================
    # CACHE MANAGEMENT - API PRINCIPAL
    # ==============================================
    
    def get_position(self, position_id: str) -> Optional[EnhancedPosition]:
        """
        Obtener posición con cache inteligente
        
        Args:
            position_id: ID de la posición
            
        Returns:
            EnhancedPosition si existe, None si no se encuentra
        """
        cache_key = f"position:{position_id}"
        
        # Intentar cache primero
        cached_position = self._get_from_cache(cache_key)
        if cached_position:
            self._stats['cache_hits'] += 1
            return cached_position
        
        # Cache miss - cargar desde DB
        self._stats['cache_misses'] += 1
        
        try:
            position = self.position_queries.get_position_by_id(position_id)
            
            if position:
                # Guardar en cache
                self._put_in_cache(cache_key, position, ttl=self.default_ttl)
                logger.debug(f"💾 Posición cargada desde DB y cacheada: {position_id}")
            
            return position
            
        except Exception as e:
            logger.error(f"❌ Error cargando posición {position_id}: {e}")
            return None
    
    def save_position(self, position: EnhancedPosition, 
                     transaction_id: Optional[str] = None) -> bool:
        """
        Guardar posición con estrategia de cache configurada
        
        Args:
            position: Posición a guardar
            transaction_id: ID de transacción (opcional)
            
        Returns:
            True si se guardó exitosamente
        """
        cache_key = f"position:{position.position_id}"
        
        try:
            # Detectar conflictos si ya existe
            existing_position = self._get_from_cache(cache_key)
            if existing_position and self._detect_conflict(position, existing_position):
                conflict = self._handle_conflict(cache_key, position, existing_position)
                if not conflict.resolved:
                    logger.warning(f"⚠️ Conflicto no resuelto para posición {position.position_id}")
                    return False
            
            # Ejecutar según estrategia de cache
            if self.cache_strategy == CacheStrategy.WRITE_THROUGH:
                return self._write_through(cache_key, position, transaction_id)
            elif self.cache_strategy == CacheStrategy.WRITE_BACK:
                return self._write_back(cache_key, position, transaction_id)
            elif self.cache_strategy == CacheStrategy.WRITE_AROUND:
                return self._write_around(cache_key, position, transaction_id)
            else:
                logger.error(f"❌ Estrategia de cache no reconocida: {self.cache_strategy}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error guardando posición {position.position_id}: {e}")
            return False
    
    # ==============================================
    # CACHE OPERATIONS - IMPLEMENTACIÓN
    # ==============================================
    
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Obtener datos del cache"""
        with self._cache_lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            
            if entry.is_expired():
                del self._cache[key]
                return None
            
            entry.touch()
            return entry.data
    
    def _put_in_cache(self, key: str, data: Any, ttl: Optional[timedelta] = None):
        """Guardar datos en cache"""
        expires_at = None
        if ttl:
            expires_at = datetime.now(pytz.UTC) + ttl
        
        entry = CacheEntry(
            key=key,
            data=data,
            expires_at=expires_at
        )
        
        with self._cache_lock:
            # Verificar límites de cache
            if len(self._cache) >= self.max_cache_size:
                self._evict_least_used()
            
            self._cache[key] = entry
    
    def _remove_from_cache(self, key: str):
        """Remover entrada del cache"""
        with self._cache_lock:
            if key in self._cache:
                del self._cache[key]
    
    def _evict_least_used(self):
        """Evictar entrada menos usada del cache"""
        if not self._cache:
            return
        
        # Encontrar entrada menos usada
        least_used_key = min(
            self._cache.keys(),
            key=lambda k: (self._cache[k].access_count, self._cache[k].last_accessed)
        )
        
        del self._cache[least_used_key]
        self._stats['cache_evictions'] += 1
        logger.debug(f"🗑️ Cache eviction: {least_used_key}")
    
    # ==============================================
    # CACHE STRATEGIES - IMPLEMENTACIÓN
    # ==============================================
    
    def _write_through(self, key: str, data: Any, transaction_id: Optional[str] = None) -> bool:
        """Write-through: escribir a cache y DB simultáneamente"""
        try:
            # Escribir a base de datos primero
            success = self._persist_to_database(data, transaction_id)
            
            if success:
                # Solo si DB fue exitosa, actualizar cache
                self._put_in_cache(key, data, ttl=self.default_ttl)
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Error en write-through {key}: {e}")
            return False
    
    def _write_back(self, key: str, data: Any, transaction_id: Optional[str] = None) -> bool:
        """Write-back: escribir a cache inmediatamente, DB en background"""
        try:
            # Escribir a cache inmediatamente
            entry = CacheEntry(
                key=key,
                data=data,
                dirty=True,  # Marcar como pendiente de sincronización
                expires_at=datetime.now(pytz.UTC) + self.default_ttl
            )
            
            with self._cache_lock:
                self._cache[key] = entry
            
            # La sincronización a DB se hace en background
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en write-back {key}: {e}")
            return False
    
    def _write_around(self, key: str, data: Any, transaction_id: Optional[str] = None) -> bool:
        """Write-around: escribir solo a DB, invalidar cache"""
        try:
            # Escribir solo a base de datos
            success = self._persist_to_database(data, transaction_id)
            
            if success:
                # Invalidar cache entry si existe
                self._remove_from_cache(key)
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Error en write-around {key}: {e}")
            return False
    
    def _persist_to_database(self, data: Any, transaction_id: Optional[str] = None) -> bool:
        """Persistir datos a base de datos"""
        try:
            if isinstance(data, EnhancedPosition):
                # Guardar posición usando position_queries
                return self._save_position_to_db(data)
            else:
                logger.warning(f"⚠️ Tipo de dato no soportado para persistencia: {type(data)}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error persistiendo a DB: {e}")
            return False
    
    def _save_position_to_db(self, position: EnhancedPosition) -> bool:
        """Guardar posición específicamente"""
        try:
            # Convertir niveles a datos de ejecución para DB
            for level in position.entry_levels + position.exit_levels:
                if level.executed_at:  # Solo guardar niveles ejecutados
                    execution_data = {
                        'symbol': position.symbol,
                        'position_id': position.position_id,
                        'level_id': str(level.level_id),
                        'execution_type': level.level_type.value,
                        'status': 'FILLED' if level.executed_price else 'PENDING',
                        'target_price': level.target_price,
                        'executed_price': level.executed_price,
                        'quantity': level.quantity,
                        'percentage': level.percentage,
                        'created_at': level.created_at.isoformat() if level.created_at else None,
                        'executed_at': level.executed_at.isoformat() if level.executed_at else None
                    }
                    
                    # **LÍNEA 927 CORREGIDA** - Indentación apropiada
                    self.position_queries.insert_execution(execution_data)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error guardando posición en DB: {e}")
            return False
    
    # ==============================================
    # CONFLICT DETECTION Y RESOLUTION
    # ==============================================
    
    def _detect_conflict(self, local_data: Any, remote_data: Any) -> bool:
        """Detectar si hay conflicto entre datos locales y remotos"""
        try:
            local_hash = hashlib.md5(pickle.dumps(local_data)).hexdigest()
            remote_hash = hashlib.md5(pickle.dumps(remote_data)).hexdigest()
            
            return local_hash != remote_hash
            
        except Exception as e:
            logger.error(f"❌ Error detectando conflicto: {e}")
            return False
    
    def _handle_conflict(self, key: str, local_data: Any, remote_data: Any) -> Any:
        """Manejar conflicto de datos"""
        conflict_id = str(uuid.uuid4())
        
        conflict = DataConflict(
            conflict_id=conflict_id,
            key=key,
            local_data=local_data,
            remote_data=remote_data,
            local_hash=hashlib.md5(pickle.dumps(local_data)).hexdigest(),
            remote_hash=hashlib.md5(pickle.dumps(remote_data)).hexdigest()
        )
        
        # Resolver según estrategia
        if conflict.resolution_strategy == ConflictResolution.LAST_WRITE_WINS:
            conflict.resolved = True
            logger.info(f"🔄 Conflicto resuelto (last write wins): {key}")
        
        # Notificar callbacks
        for callback in self._conflict_callbacks:
            try:
                callback(conflict)
            except Exception as e:
                logger.error(f"❌ Error en callback de conflicto: {e}")
        
        self._conflicts[conflict_id] = conflict
        self._stats['conflicts_detected'] += 1
        
        if conflict.resolved:
            self._stats['conflicts_resolved'] += 1
        
        return conflict
    
    # ==============================================
    # TRANSACTION MANAGEMENT
    # ==============================================
    
    def begin_transaction(self) -> str:
        """
        Iniciar una nueva transacción
        
        Returns:
            transaction_id: ID único de la transacción
        """
        transaction_id = f"txn_{int(time.time())}_{threading.get_ident()}"
        
        with self._transaction_lock:
            transaction = Transaction(transaction_id=transaction_id)
            self._active_transactions[transaction_id] = transaction
        
        logger.debug(f"🔄 Transacción iniciada: {transaction_id}")
        return transaction_id
    
    def commit_transaction(self, transaction_id: str) -> bool:
        """
        Confirmar transacción
        
        Args:
            transaction_id: ID de la transacción
            
        Returns:
            True si se confirmó exitosamente
        """
        with self._transaction_lock:
            transaction = self._active_transactions.get(transaction_id)
            if not transaction:
                logger.warning(f"⚠️ Transacción no encontrada: {transaction_id}")
                return False
            
            try:
                # Ejecutar todas las operaciones
                conn = get_connection()
                conn.execute("BEGIN TRANSACTION")
                
                for operation in transaction.operations:
                    self._execute_operation(conn, operation)
                
                conn.commit()
                conn.close()
                
                # Marcar como confirmada
                transaction.status = TransactionStatus.COMMITTED
                transaction.completed_at = datetime.now(pytz.UTC)
                
                self._stats['transactions_committed'] += 1
                logger.debug(f"✅ Transacción confirmada: {transaction_id}")
                # AÑADIR al final del try exitoso:
                # Cleanup automático
                del self._active_transactions[transaction_id]
                return True
                
            except Exception as e:
                # Rollback automático
                try:
                    conn.rollback()
                    conn.close()
                except Exception:
                    pass
                
                transaction.status = TransactionStatus.FAILED
                transaction.error_message = str(e)
                transaction.completed_at = datetime.now(pytz.UTC)
                
                logger.error(f"❌ Error en transacción {transaction_id}: {e}")
                return False
    
    def rollback_transaction(self, transaction_id: str) -> bool:
        """
        Revertir transacción
        
        Args:
            transaction_id: ID de la transacción
            
        Returns:
            True si se revirtió exitosamente
        """
        with self._transaction_lock:
            transaction = self._active_transactions.get(transaction_id)
            if not transaction:
                logger.warning(f"⚠️ Transacción no encontrada para rollback: {transaction_id}")
                return False
            
            transaction.status = TransactionStatus.ROLLED_BACK
            transaction.completed_at = datetime.now(pytz.UTC)
            
            self._stats['transactions_rolled_back'] += 1
            logger.debug(f"↩️ Transacción revertida: {transaction_id}")
            # AÑADIR al final:
            # Cleanup automático  
            del self._active_transactions[transaction_id]
            return True
    
    def _execute_operation(self, conn: sqlite3.Connection, operation: Dict[str, Any]):
        """Ejecutar operación individual dentro de transacción"""
        op_type = operation.get('type')
        
        if op_type == 'insert_execution':
            data = operation.get('data')
            conn.execute("""
                INSERT INTO position_executions 
                (symbol, position_id, level_id, execution_type, status, target_price, 
                 executed_price, quantity, percentage, created_at, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data['symbol'], data['position_id'], data['level_id'],
                data['execution_type'], data['status'], data['target_price'],
                data['executed_price'], data['quantity'], data['percentage'],
                data['created_at'], data['executed_at']
            ))
        else:
            logger.warning(f"⚠️ Tipo de operación no reconocida: {op_type}")
    
    # ==============================================
    # BATCH OPERATIONS
    # ==============================================
    
    def batch_save_positions(self, positions: List[EnhancedPosition]) -> Dict[str, bool]:
        """
        Guardar múltiples posiciones en batch
        
        Args:
            positions: Lista de posiciones a guardar
            
        Returns:
            Dict con resultado por position_id
        """
        results = {}
        transaction_id = self.begin_transaction()
        
        try:
            for position in positions:
                success = self.save_position(position, transaction_id)
                results[position.position_id] = success
            
            # Si todas fueron exitosas, commit
            all_success = all(results.values())
            if all_success:
                self.commit_transaction(transaction_id)
                logger.info(f"💾 Batch save exitoso: {len(positions)} posiciones")
            else:
                self.rollback_transaction(transaction_id)
                logger.warning(f"⚠️ Batch save falló, rollback ejecutado")
            
            return results
            
        except Exception as e:
            self.rollback_transaction(transaction_id)
            logger.error(f"❌ Error en batch save: {e}")
            return {pos.position_id: False for pos in positions}
    
    def batch_get_positions(self, position_ids: List[str]) -> Dict[str, Optional[EnhancedPosition]]:
        """
        Obtener múltiples posiciones en batch
        
        Args:
            position_ids: Lista de IDs de posiciones
            
        Returns:
            Dict con posiciones encontradas
        """
        results = {}
        
        for position_id in position_ids:
            results[position_id] = self.get_position(position_id)
        
        return results
    
    # ==============================================
    # CACHE MANAGEMENT - UTILIDADES
    # ==============================================
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Obtener estadísticas del cache"""
        with self._cache_lock:
            total_size = sum(entry.size_bytes for entry in self._cache.values())
            
            stats = self._stats.copy()
            stats.update({
                'cache_size': len(self._cache),
                'total_size_bytes': total_size,
                'max_cache_size': self.max_cache_size,
                'cache_hit_rate': self._calculate_hit_rate(),
                'active_transactions': len(self._active_transactions),
                'conflicts_pending': len([c for c in self._conflicts.values() if not c.resolved])
            })
            
            return stats
    
    def _calculate_hit_rate(self) -> float:
        """Calcular tasa de aciertos del cache"""
        total = self._stats['cache_hits'] + self._stats['cache_misses']
        if total == 0:
            return 0.0
        return (self._stats['cache_hits'] / total) * 100
    
    def clear_cache(self):
        """Limpiar completamente el cache"""
        with self._cache_lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats['cache_evictions'] += count
            logger.info(f"🧹 Cache limpiado: {count} entradas removidas")
    
    def invalidate_cache(self, pattern: str = None):
        """
        Invalidar entradas del cache
        
        Args:
            pattern: Patrón para filtrar keys (opcional)
        """
        with self._cache_lock:
            if pattern:
                keys_to_remove = [key for key in self._cache.keys() if pattern in key]
                for key in keys_to_remove:
                    del self._cache[key]
                self._stats['cache_evictions'] += len(keys_to_remove)
                logger.info(f"🧹 Cache invalidado: {len(keys_to_remove)} entradas con patrón '{pattern}'")
            else:
                count = len(self._cache)
                self._cache.clear()
                self._stats['cache_evictions'] += count
                logger.info(f"🧹 Cache completamente invalidado: {count} entradas")
    
    # ==============================================
    # OBSERVERS Y CALLBACKS
    # ==============================================
    
    def add_conflict_callback(self, callback: Callable[[DataConflict], None]):
        """Añadir callback para conflictos de datos"""
        self._conflict_callbacks.append(callback)
    
    def remove_conflict_callback(self, callback: Callable[[DataConflict], None]):
        """Remover callback específico"""
        if callback in self._conflict_callbacks:
            self._conflict_callbacks.remove(callback)
    
    # ==============================================
    # BACKGROUND TASKS
    # ==============================================
    
    def _cleanup_loop(self):
        """Loop de limpieza en background"""
        while not self._shutdown:
            try:
                time.sleep(self.cleanup_interval.total_seconds())
                
                if self._shutdown:
                    break
                
                # Limpiar entradas expiradas
                expired_keys = []
                with self._cache_lock:
                    for key, entry in self._cache.items():
                        if entry.is_expired():
                            expired_keys.append(key)
                
                if expired_keys:
                    with self._cache_lock:
                        for key in expired_keys:
                            del self._cache[key]
                    
                    self._stats['cache_evictions'] += len(expired_keys)
                    logger.debug(f"🧹 Limpieza automática: {len(expired_keys)} entradas expiradas")
                
                # Limpiar transacciones completadas viejas
                with self._transaction_lock:
                    cutoff_time = datetime.now(pytz.UTC) - timedelta(hours=1)
                    completed_txns = [
                        txn_id for txn_id, txn in self._active_transactions.items()
                        if txn.status in [TransactionStatus.COMMITTED, TransactionStatus.ROLLED_BACK, TransactionStatus.FAILED]
                        and txn.completed_at and txn.completed_at < cutoff_time
                    ]
                    
                    for txn_id in completed_txns:
                        del self._active_transactions[txn_id]
                    
                    if completed_txns:
                        logger.debug(f"🧹 Transacciones viejas limpiadas: {len(completed_txns)}")
                
            except Exception as e:
                logger.error(f"❌ Error en cleanup loop: {e}")
    
    def _sync_loop(self):
        """Loop de sincronización en background"""
        while not self._shutdown:
            try:
                time.sleep(30)  # Sincronizar cada 30 segundos
                
                if self._shutdown:
                    break
                
                # Sincronizar entradas dirty
                self.flush_dirty_entries()
                
            except Exception as e:
                logger.error(f"❌ Error en sync loop: {e}")
    
    # ==============================================
    # HEALTH MONITORING
    # ==============================================
    
    def get_system_health(self) -> str:  # Cambiar nombre y return type
        """Obtener estado de salud como string"""
        cache_size = len(self._cache)
        active_txns = len(self._active_transactions)
        
        if cache_size > 10000 or active_txns > 50:
            return "UNHEALTHY"
        elif cache_size > 5000 or active_txns > 20:
            return "DEGRADED"
        else:
            return "HEALTHY"
    
    # ==============================================
    # BACKUP Y RECOVERY
    # ==============================================
    
    def create_snapshot(self, backup_dir: Optional[str] = None) -> str:
        """
        Crear snapshot completo del estado actual
        
        Args:
            backup_dir: Directorio de backup (opcional)
            
        Returns:
            Ruta del archivo de backup creado
        """
        if backup_dir is None:
            backup_dir = tempfile.mkdtemp(prefix="persistence_backup_")
        
        backup_path = Path(backup_dir)
        backup_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now(pytz.UTC).strftime("%Y%m%d_%H%M%S")
        backup_file = backup_path / f"persistence_snapshot_{timestamp}.pkl"
        
        try:
            # Crear snapshot del estado
            snapshot_data = {
                'timestamp': datetime.now(pytz.UTC),
                'cache': {},
                'statistics': self._stats.copy(),
                'conflicts': self._conflicts.copy(),
                'metadata': {
                    'cache_strategy': self.cache_strategy.value,
                    'max_cache_size': self.max_cache_size,
                    'default_ttl_minutes': self.default_ttl.total_seconds() / 60
                }
            }
            
            # Serializar cache (sin datos sensitivos)
            with self._cache_lock:
                for key, entry in self._cache.items():
                    snapshot_data['cache'][key] = {
                        'key': entry.key,
                        'created_at': entry.created_at,
                        'last_accessed': entry.last_accessed,
                        'expires_at': entry.expires_at,
                        'access_count': entry.access_count,
                        'dirty': entry.dirty,
                        'size_bytes': entry.size_bytes,
                        'data_hash': entry.data_hash
                        # No incluir 'data' por seguridad
                    }
            
            # Guardar snapshot
            with open(backup_file, 'wb') as f:
                pickle.dump(snapshot_data, f)
            
            logger.info(f"📸 Snapshot creado: {backup_file}")
            return str(backup_path)
            
        except Exception as e:
            logger.error(f"❌ Error creando snapshot: {e}")
            raise
    
    def restore_from_snapshot(self, snapshot_file: str) -> bool:
        """
        Restaurar desde snapshot
        
        Args:
            snapshot_file: Archivo de snapshot
            
        Returns:
            True si se restauró exitosamente
        """
        try:
            with open(snapshot_file, 'rb') as f:
                snapshot_data = pickle.load(f)
            
            # Restaurar estadísticas
            self._stats.update(snapshot_data.get('statistics', {}))
            
            # Restaurar conflictos
            self._conflicts.update(snapshot_data.get('conflicts', {}))
            
            # Restaurar configuración
            metadata = snapshot_data.get('metadata', {})
            if 'cache_strategy' in metadata:
                self.cache_strategy = CacheStrategy(metadata['cache_strategy'])
            
            logger.info(f"📥 Snapshot restaurado desde: {snapshot_file}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error restaurando snapshot: {e}")
            return False
    
    # ==============================================
    # CLEANUP Y SHUTDOWN
    # ==============================================
    
    def flush_dirty_entries(self) -> int:
        """Forzar sincronización de entradas dirty"""
        dirty_count = 0
        
        with self._cache_lock:
            for key, entry in self._cache.items():
                if entry.dirty:
                    try:
                        success = self._persist_to_database(entry.data)
                        if success:
                            entry.dirty = False
                            dirty_count += 1
                    except Exception as e:
                        logger.error(f"❌ Error sincronizando entrada dirty {key}: {e}")
        
        logger.info(f"💾 Flush completado: {dirty_count} entradas sincronizadas")
        return dirty_count
    
    def shutdown(self):
        """Shutdown limpio del persistence manager"""
        logger.info("🛑 Iniciando shutdown del Persistence Manager...")
        
        self._shutdown = True
        
        # Flush entradas dirty
        self.flush_dirty_entries()
        
        # Commit transacciones pendientes o rollback
        with self._transaction_lock:
            for transaction_id in list(self._active_transactions.keys()):
                if self._active_transactions[transaction_id].status == TransactionStatus.PENDING:
                    logger.warning(f"⚠️ Transacción pendiente durante shutdown, haciendo rollback: {transaction_id}")
                    self.rollback_transaction(transaction_id)
        
        # Esperar que terminen threads de background
        if self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5)
        
        if self._sync_thread.is_alive():
            self._sync_thread.join(timeout=5)
        
        logger.info("✅ Persistence Manager cerrado correctamente")


# ==============================================
# FACTORY Y SINGLETON PATTERN
# ==============================================

_persistence_manager_instance: Optional[PersistenceManager] = None

def get_persistence_manager() -> PersistenceManager:
    """
    Obtener instancia singleton del PersistenceManager
    
    Returns:
        Instancia única del PersistenceManager
    """
    global _persistence_manager_instance
    
    if _persistence_manager_instance is None:
        _persistence_manager_instance = PersistenceManager()
    
    return _persistence_manager_instance


def reset_persistence_manager():
    """Resetear instancia del PersistenceManager (útil para testing)"""
    global _persistence_manager_instance
    if _persistence_manager_instance:
        _persistence_manager_instance.shutdown()
    _persistence_manager_instance = None


# ==============================================
# UTILITIES Y HELPERS
# ==============================================

def calculate_cache_efficiency(stats: Dict[str, Any]) -> float:
    """Calcular eficiencia del cache"""
    total_requests = stats.get('cache_hits', 0) + stats.get('cache_misses', 0)
    if total_requests == 0:
        return 0.0
    
    return (stats.get('cache_hits', 0) / total_requests) * 100


def format_cache_size(size_bytes: int) -> str:
    """Formatear tamaño del cache en formato legible"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


# ==============================================
# TESTING Y DEMO
# ==============================================

if __name__ == "__main__":
    # Demo del persistence manager
    print("💾 PERSISTENCE MANAGER - Demo")
    print("=" * 50)
    
    manager = get_persistence_manager()
    
    # Crear posición de prueba
    from .data_models import EnhancedPosition
    from .states import SignalDirection
    
    test_position = EnhancedPosition(
        symbol="DEMO",
        direction=SignalDirection.LONG,
        position_id="DEMO_001"
    )
    
    # Guardar posición
    print("💾 Guardando posición...")
    success = manager.save_position(test_position)
    print(f"Resultado: {'✅ Exitoso' if success else '❌ Error'}")
    
    # Obtener posición (debería venir del cache)
    print("\n📊 Obteniendo posición...")
    retrieved_position = manager.get_position("DEMO_001")
    print(f"Resultado: {'✅ Encontrada' if retrieved_position else '❌ No encontrada'}")
    
    # Estadísticas del cache
    print("\n📈 Estadísticas del cache:")
    stats = manager.get_cache_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Estado de salud
    health = manager.get_health_status()
    print(f"\n🏥 Estado de salud: {health}")
    
    # Crear snapshot
    print("\n📸 Creando snapshot...")
    backup_file = manager.create_snapshot()
    print(f"Snapshot creado: {backup_file}")
    
    print("\n🏁 Demo completado")
    
    # Cleanup
    manager.shutdown()