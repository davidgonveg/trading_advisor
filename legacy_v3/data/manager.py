import pandas as pd
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import pytz

# Internal imports (Absolute imports assuming root is in pythonpath)
from .providers.factory import ProviderFactory
from database.connection import get_connection, save_continuous_data, get_continuous_data_as_df
from analysis.gap_detector import GapDetector

logger = logging.getLogger(__name__)

class DataManager:
    """
    CENTRALIZED DATA MANAGER (V3.2)
    ===============================
    Single source of truth for market data.
    Handles:
    1. Fetching (Multi-provider failover)
    2. Local Storage (SQLite)
    3. Hybrid Merging (Overlay DB on API)
    4. Gap Detection & Filling & Persistence
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.provider_factory = ProviderFactory(config)
        self.gap_detector = GapDetector() # Assumes GapDetector is self-contained
        
        # Config shortcuts
        self.max_gap_hours = config.get('GAP_DETECTION_CONFIG', {}).get('REAL_DATA_CONFIG', {}).get('MAX_GAP_TO_FILL_HOURS', 168)
    
    def get_data(self, symbol: str, timeframe: str, days: int = 30) -> Optional[pd.DataFrame]:
        """
        Main Entry Point.
        Returns a clean, gap-filled, persistent DataFrame.
        """
        logger.info(f"📥 DataManager request: {symbol} ({timeframe}, {days}d)")
        
        # 1. Load Local Data (The "Memory")
        local_df = self._load_local_data(symbol, days)
        
        # 2. Fetch Fresh Data (The "Reality")
        # Ensure we fetch enough to overlap and verify
        api_df = self.provider_factory.fetch_data_with_failover(symbol, timeframe, days=days)
        
        if api_df is None:
             # If API fails completely, fallback to Local only?
             if not local_df.empty:
                 logger.warning(f"⚠️ API failed, running on PURE LOCAL MEMORY for {symbol}")
                 return local_df
             else:
                 logger.error(f"❌ critical failure: No API data and no Local data for {symbol}")
                 return None

        # 3. Hybrid Merge (The "Overlay")
        merged_df = self._merge_and_sync(api_df, local_df, symbol)
        
        # 4. Gap Detection & Filling (The "Repair")
        # Only run if newer data was fetched or merged, checking for gaps in the *result*
        # Actually, we should check gaps in the merged result to ensure continuity
        final_df = self._handle_gaps(merged_df, symbol, timeframe)
        
        return final_df

    def _load_local_data(self, symbol: str, days: int) -> pd.DataFrame:
        """Fetch historical data from SQLite"""
        try:
            df = get_continuous_data_as_df(symbol, days)
            if not df.empty:
                # Ensure timezone aware (US/Eastern) if stored naive
                if df.index.tz is None:
                    df.index = df.index.tz_localize("US/Eastern")
                logger.debug(f"💾 Loaded {len(df)} rows from Local DB for {symbol}")
            return df
        except Exception as e:
            logger.error(f"⚠️ Error loading local data: {e}")
            return pd.DataFrame()

    def _merge_and_sync(self, api_df: pd.DataFrame, local_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """
        Merge rules:
        - API is the baseline (latest truth).
        - Local contains "Gap Fills" that API might be missing (e.g. synthetic fills).
        - We prioritize Local 'Filled' rows over API 'Missing' rows.
        - But we prioritize API 'Real' rows over Local 'Old' rows? 
        
        Actually, previous logic was:
        1. Start with API.
        2. Update with Local (Implicitly overwrites API with Local if index matches).
        3. Append missing Local rows.
        """
        if local_df.empty:
            return api_df

        # Align Timezones
        if api_df.index.tz != local_df.index.tz:
            # Normalize to API tz
            local_df.index = local_df.index.tz_convert(api_df.index.tz)

        # 1. Update existing indices
        # If DB has a row for time T, overwrite API's row for time T?
        # NO. API data is usually "better" unless DB row is a "Fixed Gap".
        # But for now, let's stick to the verified logic: Update API with Local.
        # Wait, if API corrects a bad data point, we want API.
        # Only overwrite if local is "GAP_FILL" and API is "NaN"? API won't have NaN rows usually.
        
        # Verified Logic from Phase 2:
        # raw_data.update(local_data) -> Overwrites raw with local.
        # This assumes Local > API.
        # Pro: Keeps manual edits or filled gaps.
        # Con: If API adds real data later, we ignore it?
        # Check: `is_gap_filled` column in local_df? `get_continuous_data_as_df` doesn't currently return that metadata to DF columns I think?
        # Check `connection.py`:
        # `columns = ['Open', 'High', 'Low', 'Close', 'Volume']` -> No metadata in DF.
        # We need metadata to make smart decisions.
        
        # For Phase 3, let's Stick to the "Append Missing" logic which was the fix.
        # We assume API data is good. We only add what API is MISSING.
        
        missing_indices = local_df.index.difference(api_df.index)
        
        if len(missing_indices) > 0:
            logger.info(f"🧠 {symbol}: Restoring {len(missing_indices)} persistent bars from DB")
            # Concat
            combined = pd.concat([api_df, local_df.loc[missing_indices]])
            combined.sort_index(inplace=True)
            return combined
        
        return api_df

    def _handle_gaps(self, df: pd.DataFrame, symbol: str, timeframe: str) -> pd.DataFrame:
        """
        Detect gaps -> Fill them -> Save them.
        """
        if df.empty:
            return df

        try:
            # 1. Detectar gaps
            gaps = self.gap_detector.detect_gaps_in_dataframe(df, symbol, 15)
            
            if not gaps:
                return df
                
            logger.info(f"🔧 {symbol}: Procesando {len(gaps)} gaps detectados")
            
            # 2. Rellenar Gaps (Solo si AUTO_FILL está habilitado)
            # Por ahora, usamos una estrategia simple de Forward Fill para mantener continuidad
            # ya que la lógica compleja de 'Extended Data API' se movió.
            
            df_filled = df.copy()
            if 'is_gap_filled' not in df_filled.columns:
                df_filled['is_gap_filled'] = False
                df_filled['data_source'] = 'API' # Default
            
            gaps_filled_count = 0
            
            # Reindexar para exponer los huecos físicos en el DF
            full_idx = pd.date_range(start=df.index.min(), end=df.index.max(), freq='15min')
            # Filtrar horario de mercado (simple)
            # TODO: Usar calendario de mercado real si es necesario, pero 24/5 simplifica
            
            # Hack: Reindexar todo y luego forward fill solo en los rangos de gaps detectados?
            # Mejor: Reindexar todo el rango.
            df_reindexed = df_filled.reindex(full_idx)
            
            # Marcar filas nuevas como gaps (son NaNs ahora)
            # Pero solo queremos llenar los que GapDetector identificó como 'fillable'
            
            for gap in gaps:
                if not gap.is_fillable:
                    continue
                    
                # Rango del gap
                gap_start = gap.start_time
                gap_end = gap.end_time
                
                # Seleccionar filas en este rango (que ahora son NaN tras reindex si faltaban)
                # Ojo: GapDetector dice start->end.
                # Si reindexamos, tenemos filas NaN entre start y end.
                
                # Estrategia: FORWARD FILL por defecto para continuidad
                mask = (df_reindexed.index > gap_start) & (df_reindexed.index < gap_end)
                
                if mask.any():
                    # Rellenar
                    df_reindexed.loc[mask] = df_reindexed.loc[mask].ffill() # Primero ffill interno? No, necesitamos valor de before_gap
                    
                    # Tomar valor previo al gap
                    # Como es forward fill, podemos simplemente hacer ffill sobre todo el segmento
                    # pero necesitamos conectar con el dato PREVIO al gap.
                    
                    # Forward fill simple sobre el rango, tomando el último valor válido
                    # Pandas ffill limit is helpful
                    
                    # Simplemente aplicar ffill limita al rango?
                    # df_reindexed.loc[gap_start:gap_end] = df_reindexed.loc[gap_start:gap_end].ffill()
                    # Pero start y end existen. Los del medio son NaNs.
                    
                    sub_slice = df_reindexed.loc[gap_start:gap_end]
                    sub_slice_filled = sub_slice.ffill()
                    
                    # Actualizar DF principal
                    df_reindexed.loc[gap_start:gap_end] = sub_slice_filled
                    
                    # Marcar metadatos
                    df_reindexed.loc[mask, 'is_gap_filled'] = True
                    df_reindexed.loc[mask, 'data_source'] = f"FILL_{gap.suggested_strategy}"
                    
                    gaps_filled_count += 1
            
            # Limpiar NaNs remanentes (fines de semana o gaps no rellenables que reindex expuso)
            # Si no queremos ensuciar el DF con NaNs de fin de semana, deberíamos filtrar?
            # O simplemente dropna() de lo que no se rellenó.
            
            final_df = df_reindexed.dropna(subset=['Close'])
            final_df.index.name = 'timestamp' # Restaurar nombre
            
            if gaps_filled_count > 0:
                logger.info(f"✅ {symbol}: Rellenados {gaps_filled_count} gaps dinámicamente")
                
                # 3. Persistir cambios
                # Solo guardar los que acabamos de rellenar (is_gap_filled=True y source empieza con FILL)
                self._persist_changes(symbol, timeframe, final_df)
            
            return final_df

        except Exception as e:
            logger.error(f"❌ Error handling gaps for {symbol}: {e}")
            return df


    def _persist_changes(self, symbol: str, timeframe: str, new_data: pd.DataFrame):
        """
        Save data to DB.
        """
        # Convert DataFrame to list of dicts for `save_continuous_data`
        # This checks for 'is_gap_filled' column.
        
        if 'is_gap_filled' not in new_data.columns:
            return 
            
        # Filter only filled rows to save? Or save all?
        # Creating a massive write might be slow.
        # Usually we only want to save specific filled rows or the latest data.
        
        # In the context of "Stateless to Stateful", we want to save FILLED gaps.
        filled_rows = new_data[new_data['is_gap_filled'] == True]
        
        if filled_rows.empty:
            return

        data_points = []
        for ts, row in filled_rows.iterrows():
            data_points.append({
                'timestamp': ts.isoformat(),
                'open': row['Open'],
                'high': row['High'],
                'low': row['Low'],
                'close': row['Close'],
                'volume': row['Volume'],
                'is_gap_filled': True,
                'data_source': row.get('data_source', 'UNKNOWN_FILL')
            })
            
        save_continuous_data(
            symbol=symbol, 
            timeframe=timeframe, 
            data_points=data_points, 
            session_type="GAP_FILL"
        )
        logger.info(f"💾 Persisted {len(filled_rows)} filled gaps for {symbol}")
