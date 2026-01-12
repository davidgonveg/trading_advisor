import pandas as pd
import numpy as np
import logging
from typing import List, Optional
from data.quality.detector import Gap, GapType, GapSeverity

logger = logging.getLogger("core.data.quality.repair")

class GapRepair:
    """
    Handles filling of data gaps.
    """
    
    def fill_gaps(self, data: pd.DataFrame, gaps: List[Gap], freq: str = None) -> pd.DataFrame:
        """
        Fill gaps in the DataFrame.
        Returns a NEW DataFrame with filled gaps.
        freq: Optional frequency string (e.g. '1h', '1d'). If None, inferred or defaults to '15T'.
        """
        if not gaps:
            return data.copy()
            
        df = data.copy()
        
        # Sort gaps to handle earliest first
        gaps.sort(key=lambda x: x.start_time)
        
        # Determine frequency
        if freq is None:
            try:
                freq = pd.infer_freq(df.index)
            except ValueError:
                freq = None
            if freq is None:
                # Fallback to 15T if inference fails
                freq = '15min' 
        
        logger.info(f"Filling gaps using frequency: {freq}")
            
        # Create full index
        full_idx = pd.date_range(start=df.index.min(), end=df.index.max(), freq=freq)
        df_filled = df.reindex(full_idx)
        
        # Now fill based on strategies
        for gap in gaps:
            if not gap.is_fillable:
                logger.warning(f"Skipping unfillable gap: {gap.gap_type.value} at {gap.start_time}")
                continue
                
            # Define slice based on gap start/end
            slice_mask = (df_filled.index >= gap.start_time) & (df_filled.index <= gap.end_time)
            subset = df_filled.loc[slice_mask].copy()
            
            # Strategy selection
            if gap.gap_type == GapType.SMALL_GAP:
                # Linear Interpolation
                logger.debug(f"Interpolating small gap {gap.start_time} -> {gap.end_time}")
                subset = subset.interpolate(method='time')
            else:
                # Forward Fill
                logger.debug(f"Forward filling gap {gap.start_time} -> {gap.end_time}")
                subset = subset.ffill()
            
            # Assign back filled values
            # Using update or loc assignment
            df_filled.loc[slice_mask, ['Close', 'Open', 'High', 'Low']] = subset[['Close', 'Open', 'High', 'Low']]
            # Volume usually 0 or filled
            df_filled.loc[slice_mask, 'Volume'] = subset['Volume'].fillna(0) 
        
        # Final pass to ensure continuity
        df_filled['Close'] = df_filled['Close'].ffill()
        df_filled['Open'] = df_filled['Open'].fillna(df_filled['Close'])
        df_filled['High'] = df_filled['High'].fillna(df_filled['Close'])
        df_filled['Low'] = df_filled['Low'].fillna(df_filled['Close'])
        df_filled['Volume'] = df_filled['Volume'].fillna(0)
        
        return df_filled
