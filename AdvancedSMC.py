# --- Imports ---
import numpy as np
import pandas as pd
from datetime import datetime
import logging
from functools import reduce
from craw_data import fetch_ohlcv, calculate_indicators

logger = logging.getLogger(__name__)

def analyze_smc_features(df: pd.DataFrame, swing_lookback: int = 20) -> pd.DataFrame:
    """
    Hàm này phân tích và thêm các cột SMC vào DataFrame.
    
    Args:
        df (DataFrame): Bảng dữ liệu OHLCV.
        swing_lookback (int): Số nến để xác định đỉnh/đáy.

    Returns:
        DataFrame: Bảng dữ liệu đã được thêm các cột phân tích SMC.
    """
    
    # --- 1. Xác định Swing Highs & Swing Lows ---
    df['swing_high'] = df['high'].rolling(window=swing_lookback*2+1, center=True).max() == df['high']
    df['swing_low'] = df['low'].rolling(window=swing_lookback*2+1, center=True).min() == df['low']
    
    # --- 2. Xác định Break of Structure (BOS) và Change of Character (CHoCH) ---
    last_swing_high = np.nan
    last_swing_low = np.nan
    trend = 0  # 1 for bullish, -1 for bearish
    
    bos_choch = []
    
    for i in range(len(df)):
        is_swing_high = df['swing_high'].iloc[i]
        is_swing_low = df['swing_low'].iloc[i]
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]
        
        signal = 0 # 1: Bullish BOS, -1: Bearish BOS, 2: Bullish CHoCH, -2: Bearish CHoCH
        
        if is_swing_high:
            last_swing_high = current_high
        if is_swing_low:
            last_swing_low = current_low

        if trend == 1 and not np.isnan(last_swing_low) and current_low < last_swing_low:
            signal = -2 # Bearish CHoCH
            trend = -1
            last_swing_high = np.nan # Reset
        elif trend == -1 and not np.isnan(last_swing_high) and current_high > last_swing_high:
            signal = 2 # Bullish CHoCH
            trend = 1
            last_swing_low = np.nan # Reset
        elif not np.isnan(last_swing_high) and current_high > last_swing_high:
            signal = 1 # Bullish BOS
            trend = 1
            last_swing_low = np.nan # Reset
        elif not np.isnan(last_swing_low) and current_low < last_swing_low:
            signal = -1 # Bearish BOS
            trend = -1
            last_swing_high = np.nan # Reset
            
        bos_choch.append(signal)

    df['bos_choch_signal'] = bos_choch
    df['BOS'] = df['bos_choch_signal'].apply(lambda x: 1 if x == 1 else (-1 if x == -1 else 0))
    df['CHOCH'] = df['bos_choch_signal'].apply(lambda x: 1 if x == 2 else (-1 if x == -2 else 0))

    # --- 3. Xác định Order Blocks (OB) ---
    df['OB'] = 0
    df['Top_OB'] = np.nan
    df['Bottom_OB'] = np.nan

    for i in range(1, len(df)):
        # Nếu có tín hiệu tăng giá mạnh
        if df['bos_choch_signal'].iloc[i] in [1, 2]:
            # Tìm nến giảm gần nhất
            for j in range(i - 1, max(0, i - 10), -1):
                if df['close'].iloc[j] < df['open'].iloc[j]: # Nến giảm
                    df.loc[df.index[j], 'OB'] = 1 # Bullish OB
                    df.loc[df.index[j], 'Top_OB'] = df['high'].iloc[j]
                    df.loc[df.index[j], 'Bottom_OB'] = df['low'].iloc[j]
                    break
        # Nếu có tín hiệu giảm giá mạnh
        elif df['bos_choch_signal'].iloc[i] in [-1, -2]:
            # Tìm nến tăng gần nhất
            for j in range(i - 1, max(0, i - 10), -1):
                if df['close'].iloc[j] > df['open'].iloc[j]: # Nến tăng
                    df.loc[df.index[j], 'OB'] = -1 # Bearish OB
                    df.loc[df.index[j], 'Top_OB'] = df['high'].iloc[j]
                    df.loc[df.index[j], 'Bottom_OB'] = df['low'].iloc[j]
                    break
    
    # --- 4. Xác định Fair Value Gaps (FVG) ---
    df['FVG'] = 0
    df['Top_FVG'] = np.nan
    df['Bottom_FVG'] = np.nan

    for i in range(2, len(df)):
        # Bullish FVG: Đáy nến 1 > Đỉnh nến 3
        if df['low'].iloc[i-2] > df['high'].iloc[i]:
            df.loc[df.index[i-1], 'FVG'] = 1
            df.loc[df.index[i-1], 'Top_FVG'] = df['low'].iloc[i-2]
            df.loc[df.index[i-1], 'Bottom_FVG'] = df['high'].iloc[i]
        # Bearish FVG: Đỉnh nến 1 < Đáy nến 3
        elif df['high'].iloc[i-2] < df['low'].iloc[i]:
            df.loc[df.index[i-1], 'FVG'] = -1
            df.loc[df.index[i-1], 'Top_FVG'] = df['high'].iloc[i-2]
            df.loc[df.index[i-1], 'Bottom_FVG'] = df['low'].iloc[i]

    # --- 5. Xác định Liquidity Sweeps ---
    df['Swept'] = 0
    recent_high = df['high'].rolling(5).max().shift(1)
    recent_low = df['low'].rolling(5).min().shift(1)
    
    # Bearish sweep (quét đỉnh)
    df.loc[(df['high'] > recent_high) & (df['close'] < recent_high), 'Swept'] = -1
    # Bullish sweep (quét đáy)
    df.loc[(df['low'] < recent_low) & (df['close'] > recent_low), 'Swept'] = 1

    return df


class AdvancedSMC:
    """
    Phân tích Smart Money Concepts (SMC) với logic multi-timeframe từ SMC Original
    """
    
    def __init__(self, exchange_name='binance'):
        self.exchange_name = exchange_name
        self.informative_timeframes = ['15m', '1h', '4h', '1d']
        
    def get_market_data(self, symbol, timeframe='4h', limit=500):
        """Lấy dữ liệu thị trường từ craw_data"""
        try:
            df = fetch_ohlcv(self.exchange_name, symbol, timeframe, limit)
            if df is None:
                return None
            return df
        except Exception as e:
            print(f"Lỗi khi lấy dữ liệu: {e}")
            return None
    
    def analyze_smc_structure(self, df):
        """Phân tích cấu trúc thị trường SMC - METHOD BỊ THIẾU"""
        if df is None or len(df) < 50:
            return {
                'order_blocks': [],
                'liquidity_zones': [],
                'fair_value_gaps': [],
                'break_of_structure': [],
                'trading_signals': {
                    'entry_long': [],
                    'entry_short': [],
                    'exit_long': [],
                    'exit_short': []
                }
            }
            
        # Áp dụng phân tích SMC
        df_analyzed = analyze_smc_features(df.copy())
        
        # Áp dụng entry/exit logic (simplified version)
        df_analyzed = self.populate_entry_trend_simple(df_analyzed)
        df_analyzed = self.populate_exit_trend(df_analyzed)
        
        return {
            'order_blocks': self.extract_order_blocks(df_analyzed),
            'liquidity_zones': self.extract_liquidity_zones(df_analyzed),
            'fair_value_gaps': self.extract_fair_value_gaps(df_analyzed),
            'break_of_structure': self.extract_break_of_structure(df_analyzed),
            'trading_signals': self.extract_recent_signals(df_analyzed)
        }
    
    def populate_entry_trend_simple(self, dataframe):
        """Version đơn giản của populate_entry_trend cho single timeframe"""
        try:
            # Khởi tạo cột entry signals
            dataframe['enter_long'] = 0
            dataframe['enter_short'] = 0
            dataframe['enter_tag'] = ''
            
            # Điều kiện Long đơn giản
            long_conditions = (
                (dataframe['BOS'] == 1) &  # Bullish BOS
                (dataframe['Swept'] == 1) &  # Quét thanh khoản đáy
                (
                    # Trong Bullish Order Block
                    ((dataframe['low'] <= dataframe['Top_OB']) & 
                     (dataframe['high'] >= dataframe['Bottom_OB']) & 
                     (dataframe['OB'] == 1)) |
                    # Hoặc trong Bullish FVG
                    ((dataframe['low'] <= dataframe['Top_FVG']) & 
                     (dataframe['high'] >= dataframe['Bottom_FVG']) & 
                     (dataframe['FVG'] == 1))
                )
            )
            
            # Điều kiện Short đơn giản
            short_conditions = (
                (dataframe['BOS'] == -1) &  # Bearish BOS
                (dataframe['Swept'] == -1) &  # Quét thanh khoản đỉnh
                (
                    # Trong Bearish Order Block
                    ((dataframe['low'] <= dataframe['Top_OB']) & 
                     (dataframe['high'] >= dataframe['Bottom_OB']) & 
                     (dataframe['OB'] == -1)) |
                    # Hoặc trong Bearish FVG
                    ((dataframe['low'] <= dataframe['Top_FVG']) & 
                     (dataframe['high'] >= dataframe['Bottom_FVG']) & 
                     (dataframe['FVG'] == -1))
                )
            )
            
            # Gán signals
            dataframe.loc[long_conditions, 'enter_long'] = 1
            dataframe.loc[long_conditions, 'enter_tag'] = 'long_smc_simple'
            
            dataframe.loc[short_conditions, 'enter_short'] = 1
            dataframe.loc[short_conditions, 'enter_tag'] = 'short_smc_simple'
            
            return dataframe
            
        except Exception as e:
            logger.error(f"Error in populate_entry_trend_simple: {e}")
            return dataframe
    
    def get_multi_timeframe_data(self, symbol):
        """Lấy dữ liệu từ nhiều timeframe"""
        mtf_data = {}
        
        for tf in self.informative_timeframes:
            try:
                df = self.get_market_data(symbol, tf, 200)
                if df is not None:
                    # Phân tích SMC cho timeframe này
                    df_analyzed = analyze_smc_features(df.copy())
                    mtf_data[tf] = df_analyzed
                    print(f"Đã lấy dữ liệu {tf}: {len(df_analyzed)} nến")
                else:
                    print(f"Không thể lấy dữ liệu cho {tf}")
            except Exception as e:
                print(f"Lỗi khi lấy dữ liệu {tf}: {e}")
        
        return mtf_data
    
    def merge_htf_data(self, base_df, mtf_data):
        """Gộp dữ liệu từ các timeframe cao hơn vào base dataframe"""
        merged_df = base_df.copy()
        
        for htf in self.informative_timeframes:
            if htf in mtf_data:
                htf_df = mtf_data[htf].copy()
                
                # Rename columns với prefix htf_
                htf_df = htf_df.rename(columns={
                    'BOS': f'htf_bos_{htf}',
                    'CHOCH': f'htf_choch_{htf}',
                    'OB': f'htf_ob_{htf}',
                    'Top_OB': f'htf_ob_top_{htf}',
                    'Bottom_OB': f'htf_ob_bottom_{htf}',
                    'FVG': f'htf_fvg_{htf}',
                    'Top_FVG': f'htf_fvg_top_{htf}',
                    'Bottom_FVG': f'htf_fvg_bottom_{htf}'
                })
                
                # Merge dữ liệu (simplified merge based on timestamp)
                htf_cols = [col for col in htf_df.columns if col.startswith('htf_')]
                
                # Forward fill cho các giá trị HTF
                for col in htf_cols:
                    merged_df[col] = 0
                    merged_df[col] = merged_df[col].fillna(method='ffill')
        
        return merged_df
    
    def populate_entry_trend(self, dataframe):
        """
        Logic entry trend từ SMC Original - multi-timeframe
        """
        try:
            # Khởi tạo cột entry signals
            dataframe['enter_long'] = 0
            dataframe['enter_short'] = 0
            dataframe['enter_tag'] = ''
            
            # Lấy higher timeframes (loại bỏ 15m)
            higher_timeframes = [tf for tf in self.informative_timeframes if tf != '15m']
            
            # --- Điều kiện chung cho Lệnh Mua (Long) ---
            htf_bullish_bos = []
            htf_bullish_poi = []
            
            for htf in higher_timeframes:
                # Kiểm tra xem cột có tồn tại không
                bos_col = f'htf_bos_{htf}'
                if bos_col in dataframe.columns:
                    htf_bullish_bos.append(dataframe[bos_col] == 1)
                
                # Points of Interest (POI) - Order Blocks và FVG
                ob_conditions = []
                fvg_conditions = []
                
                if all(col in dataframe.columns for col in [f'htf_ob_top_{htf}', f'htf_ob_bottom_{htf}', f'htf_ob_{htf}']):
                    in_ob = (
                        (dataframe['low'] <= dataframe[f'htf_ob_top_{htf}']) & 
                        (dataframe['high'] >= dataframe[f'htf_ob_bottom_{htf}']) & 
                        (dataframe[f'htf_ob_{htf}'] == 1)
                    )
                    ob_conditions.append(in_ob)
                
                if all(col in dataframe.columns for col in [f'htf_fvg_top_{htf}', f'htf_fvg_bottom_{htf}', f'htf_fvg_{htf}']):
                    in_fvg = (
                        (dataframe['low'] <= dataframe[f'htf_fvg_top_{htf}']) & 
                        (dataframe['high'] >= dataframe[f'htf_fvg_bottom_{htf}']) & 
                        (dataframe[f'htf_fvg_{htf}'] == 1)
                    )
                    fvg_conditions.append(in_fvg)
                
                # Kết hợp OB và FVG conditions
                if ob_conditions or fvg_conditions:
                    all_poi_conditions = ob_conditions + fvg_conditions
                    htf_bullish_poi.append(reduce(lambda a, b: a | b, all_poi_conditions))

            # --- Điều kiện chung cho Lệnh Bán (Short) ---
            htf_bearish_bos = []
            htf_bearish_poi = []
            
            for htf in higher_timeframes:
                # Bearish BOS
                bos_col = f'htf_bos_{htf}'
                if bos_col in dataframe.columns:
                    htf_bearish_bos.append(dataframe[bos_col] == -1)
                
                # Bearish POI
                ob_conditions = []
                fvg_conditions = []
                
                if all(col in dataframe.columns for col in [f'htf_ob_top_{htf}', f'htf_ob_bottom_{htf}', f'htf_ob_{htf}']):
                    in_ob = (
                        (dataframe['low'] <= dataframe[f'htf_ob_top_{htf}']) & 
                        (dataframe['high'] >= dataframe[f'htf_ob_bottom_{htf}']) & 
                        (dataframe[f'htf_ob_{htf}'] == -1)
                    )
                    ob_conditions.append(in_ob)
                
                if all(col in dataframe.columns for col in [f'htf_fvg_top_{htf}', f'htf_fvg_bottom_{htf}', f'htf_fvg_{htf}']):
                    in_fvg = (
                        (dataframe['low'] <= dataframe[f'htf_fvg_top_{htf}']) & 
                        (dataframe['high'] >= dataframe[f'htf_fvg_bottom_{htf}']) & 
                        (dataframe[f'htf_fvg_{htf}'] == -1)
                    )
                    fvg_conditions.append(in_fvg)
                
                if ob_conditions or fvg_conditions:
                    all_poi_conditions = ob_conditions + fvg_conditions
                    htf_bearish_poi.append(reduce(lambda a, b: a | b, all_poi_conditions))

            # --- Kết hợp điều kiện và tạo tín hiệu ---
            if htf_bullish_bos and htf_bullish_poi:
                long_conditions = (
                    reduce(lambda a, b: a | b, htf_bullish_bos) &
                    reduce(lambda a, b: a | b, htf_bullish_poi) &
                    (dataframe['Swept'] == 1) &
                    (dataframe['CHOCH'].shift(1) == 1)
                )
                
                # Kiểm tra htf_choch_15m nếu có
                if 'htf_choch_15m' in dataframe.columns:
                    long_conditions = long_conditions & (dataframe['htf_choch_15m'] != -1)
                
                dataframe.loc[long_conditions, 'enter_long'] = 1
                dataframe.loc[long_conditions, 'enter_tag'] = 'long_smc_manual'
            
            if htf_bearish_bos and htf_bearish_poi:
                short_conditions = (
                    reduce(lambda a, b: a | b, htf_bearish_bos) &
                    reduce(lambda a, b: a | b, htf_bearish_poi) &
                    (dataframe['Swept'] == -1) &
                    (dataframe['CHOCH'].shift(1) == -1)
                )
                
                # Kiểm tra htf_choch_15m nếu có
                if 'htf_choch_15m' in dataframe.columns:
                    short_conditions = short_conditions & (dataframe['htf_choch_15m'] != 1)
                
                dataframe.loc[short_conditions, 'enter_short'] = 1
                dataframe.loc[short_conditions, 'enter_tag'] = 'short_smc_manual'

            return dataframe
            
        except Exception as e:
            logger.error(f"Error in populate_entry_trend: {e}")
            return dataframe
    
    def populate_exit_trend(self, dataframe):
        """
        Logic exit trend từ SMC Original
        """
        try:
            # Khởi tạo cột exit signals
            dataframe['exit_long'] = 0
            dataframe['exit_short'] = 0
            
            # Exit Long khi CHoCH bearish
            dataframe.loc[(dataframe['CHOCH'] == -1), 'exit_long'] = 1
            
            # Exit Short khi CHoCH bullish
            dataframe.loc[(dataframe['CHOCH'] == 1), 'exit_short'] = 1
            
            return dataframe
            
        except Exception as e:
            logger.error(f"Error in populate_exit_trend: {e}")
            return dataframe
    
    def get_trading_signals(self, symbol, timeframe='4h'):
        """METHOD CHÍNH - Lấy tín hiệu trading dựa trên SMC"""
        try:
            # Lấy dữ liệu
            df = self.get_market_data(symbol, timeframe)
            if df is None:
                return None
            
            # Phân tích SMC
            smc_analysis = self.analyze_smc_structure(df)
            
            # Tính indicators bổ sung
            df_calc = df.tail(200).copy()
            indicators = calculate_indicators(df, df_calc)
            
            # Kết hợp tất cả
            result = {
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': int(df.iloc[-1]['timestamp'].timestamp()),
                'current_price': float(df.iloc[-1]['close']),
                'smc_analysis': {
                    'order_blocks': smc_analysis['order_blocks'],
                    'liquidity_zones': smc_analysis['liquidity_zones'],
                    'fair_value_gaps': smc_analysis['fair_value_gaps'],
                    'break_of_structure': smc_analysis['break_of_structure']
                },
                'trading_signals': smc_analysis['trading_signals'],
                'indicators': indicators
            }
            
            return result
            
        except Exception as e:
            print(f"Lỗi khi phân tích SMC: {e}")
            return None
    
    def get_trading_signals_mtf(self, symbol, timeframe='15m'):
        """Lấy tín hiệu trading với multi-timeframe analysis"""
        try:
            # Lấy dữ liệu multi-timeframe
            print(f"Đang lấy dữ liệu multi-timeframe cho {symbol}...")
            mtf_data = self.get_multi_timeframe_data(symbol)
            
            if not mtf_data:
                print("Không thể lấy dữ liệu multi-timeframe")
                return None
            
            # Sử dụng timeframe thấp nhất làm base
            base_tf = timeframe
            if base_tf not in mtf_data:
                base_tf = list(mtf_data.keys())[0]
            
            base_df = mtf_data[base_tf].copy()
            
            # Merge HTF data
            print("Đang merge dữ liệu HTF...")
            merged_df = self.merge_htf_data(base_df, mtf_data)
            
            # Áp dụng entry/exit logic
            print("Đang áp dụng logic entry/exit...")
            merged_df = self.populate_entry_trend(merged_df)
            merged_df = self.populate_exit_trend(merged_df)
            
            # Tính indicators bổ sung
            df_calc = base_df.tail(200).copy()
            indicators = calculate_indicators(base_df, df_calc)
            
            # Lấy signals gần nhất
            recent_signals = self.extract_recent_signals(merged_df)
            
            # Kết hợp tất cả
            result = {
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': int(base_df.iloc[-1]['timestamp'].timestamp()),
                'current_price': float(base_df.iloc[-1]['close']),
                'smc_analysis': {
                    'order_blocks': self.extract_order_blocks(merged_df),
                    'liquidity_zones': self.extract_liquidity_zones(merged_df),
                    'fair_value_gaps': self.extract_fair_value_gaps(merged_df),
                    'break_of_structure': self.extract_break_of_structure(merged_df)
                },
                'trading_signals': recent_signals,
                'indicators': indicators
            }
            
            return result
            
        except Exception as e:
            print(f"Lỗi khi phân tích SMC: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ... existing extraction methods remain the same ...
    def extract_recent_signals(self, df):
        """Trích xuất các signals gần nhất"""
        signals = {
            'entry_long': [],
            'entry_short': [],
            'exit_long': [],
            'exit_short': []
        }
        
        # Lấy signals gần nhất
        recent_df = df.tail(50)
        
        for i, row in recent_df.iterrows():
            timestamp = int(row['timestamp'].timestamp())
            
            if row.get('enter_long', 0) == 1:
                signals['entry_long'].append({
                    'time': timestamp,
                    'price': row['close'],
                    'tag': row.get('enter_tag', 'long_smc')
                })
            
            if row.get('enter_short', 0) == 1:
                signals['entry_short'].append({
                    'time': timestamp,
                    'price': row['close'],
                    'tag': row.get('enter_tag', 'short_smc')
                })
            
            if row.get('exit_long', 0) == 1:
                signals['exit_long'].append({
                    'time': timestamp,
                    'price': row['close']
                })
            
            if row.get('exit_short', 0) == 1:
                signals['exit_short'].append({
                    'time': timestamp,
                    'price': row['close']
                })
        
        return signals

    def extract_order_blocks(self, df):
        """Trích xuất Order Blocks từ DataFrame đã phân tích"""
        order_blocks = []
        
        for i, row in df.iterrows():
            if row.get('OB', 0) != 0:
                order_blocks.append({
                    'type': 'bullish_ob' if row['OB'] == 1 else 'bearish_ob',
                    'high': row.get('Top_OB'),
                    'low': row.get('Bottom_OB'),
                    'time': int(row['timestamp'].timestamp()),
                    'strength': 'high'
                })
        
        return order_blocks[-10:]  # Trả về 10 OB gần nhất
    
    def extract_liquidity_zones(self, df):
        """Trích xuất Liquidity Zones"""
        liquidity_zones = []
        
        # Tìm các swing highs và lows
        swing_highs = df[df.get('swing_high', False) == True]
        swing_lows = df[df.get('swing_low', False) == True]
        
        for i, row in swing_highs.iterrows():
            liquidity_zones.append({
                'type': 'buy_side_liquidity',
                'price': row['high'],
                'time': int(row['timestamp'].timestamp()),
                'strength': 'high'
            })
        
        for i, row in swing_lows.iterrows():
            liquidity_zones.append({
                'type': 'sell_side_liquidity',
                'price': row['low'],
                'time': int(row['timestamp'].timestamp()),
                'strength': 'high'
            })
        
        return liquidity_zones[-10:]  # Trả về 10 zone gần nhất
    
    def extract_fair_value_gaps(self, df):
        """Trích xuất Fair Value Gaps"""
        fvgs = []
        
        for i, row in df.iterrows():
            if row.get('FVG', 0) != 0:
                fvgs.append({
                    'type': 'bullish_fvg' if row['FVG'] == 1 else 'bearish_fvg',
                    'top': row.get('Top_FVG'),
                    'bottom': row.get('Bottom_FVG'),
                    'time': int(row['timestamp'].timestamp()),
                    'filled': False
                })
        
        return fvgs[-20:]  # Trả về 20 FVG gần nhất
    
    def extract_break_of_structure(self, df):
        """Trích xuất Break of Structure"""
        bos_signals = []
        
        for i, row in df.iterrows():
            if row.get('BOS', 0) != 0:
                bos_signals.append({
                    'type': 'bullish_bos' if row['BOS'] == 1 else 'bearish_bos',
                    'price': row['close'],
                    'time': int(row['timestamp'].timestamp()),
                    'strength': 'confirmed'
                })
        
        return bos_signals[-10:]  # Trả về 10 BOS gần nhất
    
    def get_telegram_summary(self, symbol, timeframe='4h'):
        """Lấy tóm tắt ngắn gọn cho Telegram"""
        try:
            result = self.get_trading_signals(symbol, timeframe)
            if not result:
                return None
            
            smc = result['smc_analysis']
            indicators = result['indicators']
            
            # Tính toán signal strength
            signal_strength = self.calculate_signal_strength(smc, indicators)
            
            summary = {
                'symbol': symbol,
                'price': result['current_price'],
                'rsi': indicators.get('rsi', 50),
                'trend': self.determine_trend(smc),
                'signal_strength': signal_strength,
                'key_levels': self.get_key_levels(smc),
                'recommendation': self.get_recommendation(signal_strength, indicators.get('rsi', 50))
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting telegram summary: {e}")
            return None
    
    def calculate_signal_strength(self, smc, indicators):
        """Tính độ mạnh của signal"""
        strength = 0
        
        # BOS signals
        if smc['break_of_structure']:
            strength += len(smc['break_of_structure']) * 0.3
        
        # FVG signals
        if smc['fair_value_gaps']:
            strength += len(smc['fair_value_gaps']) * 0.2
        
        # Order blocks
        if smc['order_blocks']:
            strength += len(smc['order_blocks']) * 0.1
        
        # RSI confirmation
        rsi = indicators.get('rsi', 50)
        if rsi > 70 or rsi < 30:
            strength += 0.5
        
        return min(strength, 10)  # Cap tại 10
    
    def determine_trend(self, smc):
        """Xác định xu hướng từ SMC"""
        if not smc['break_of_structure']:
            return 'neutral'
        
        latest_bos = smc['break_of_structure'][-1]
        return 'bullish' if latest_bos['type'] == 'bullish_bos' else 'bearish'
    
    def get_key_levels(self, smc):
        """Lấy các mức giá quan trọng"""
        levels = []
        
        # From order blocks
        for ob in smc['order_blocks'][-3:]:  # 3 OB gần nhất
            levels.append({
                'type': 'order_block',
                'price': (ob['high'] + ob['low']) / 2,
                'direction': ob['type']
            })
        
        # From liquidity zones
        for lz in smc['liquidity_zones'][-3:]:  # 3 LZ gần nhất
            levels.append({
                'type': 'liquidity',
                'price': lz['price'],
                'direction': lz['type']
            })
        
        return levels
    
    def get_recommendation(self, signal_strength, rsi):
        """Đưa ra khuyến nghị đơn giản"""
        if signal_strength > 7 and rsi < 30:
            return "🚀 STRONG BUY"
        elif signal_strength > 5 and rsi < 40:
            return "📈 BUY"
        elif signal_strength > 7 and rsi > 70:
            return "🔴 STRONG SELL"
        elif signal_strength > 5 and rsi > 60:
            return "📉 SELL"
        else:
            return "⏸️ HOLD/WAIT"
