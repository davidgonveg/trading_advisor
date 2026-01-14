import pandas as pd
from analysis.indicators import TechnicalIndicators # Reuse existing

class IndicatorCalculator:
    """
    Helper to run TA on the partial history DataFrame.
    """
    
    @staticmethod
    def calculate(df: pd.DataFrame):
        """
        Calculates all required indicators for the strategy using the project's standard library.
        """
        if len(df) < 50: # Minimum warm-up
            return df
            
        ti = TechnicalIndicators()
        # calculate_all returns a new DF with columns added: RSI, ADX, BB_*, ATR, VWAP
        # Note: analysis.indicators uses names like 'BB_Lower', 'BB_Upper' (Title Case)
        # My strategy expected 'BB_lower' (lowercase). I need to check mappings.
        df_new = ti.calculate_all(df)
        
        # Mapping for Strategy compatibility if needed
        # Strategy uses: BB_lower, ATR, RSI, ADX
        # TechnicalIndicators produces: BB_Lower, ATR, RSI, ADX
        # I should unify names. Let's map strict lower case for Strategy consistency
        if 'BB_Lower' in df_new.columns:
            df_new['BB_lower'] = df_new['BB_Lower']
            
        return df_new
