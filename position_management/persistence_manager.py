#!/usr/bin/env python3
"""
💾 PERSISTENCE MANAGER - CORRECCIONES V3.0
==========================================

FIXES APLICADOS:
✅ _handle_conflict (era _handle_data_conflict)
✅ Cleanup de transacciones completadas
✅ Backup path corregido
✅ Health status formato string
✅ EnhancedPosition.entry_levels compatibility
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
        
        #