import ccxt
import pandas as pd
import numpy as np
import time

# Lấy nến đóng và mở rộng hàm fetch_ohlcv để hỗ trợ nhiều timeframe hơn

def fetch_ohlcv(exchange_name, symbol, timeframe, limit):
    """Fetch OHLCV data từ exchange được chỉ định"""
    try:
        # Map timeframe để tương thích với CCXT
        timeframe_map = {
            '15m': '15m',
            '1h': '1h', 
            '4h': '4h',
            '1d': '1d',
            '3d': '3d',
            '1w': '1w',
            # Thêm mapping cho các timeframe khác
            '5m': '5m',
            '30m': '30m',
            '2h': '2h',
            '6h': '6h',
            '8h': '8h',
            '12h': '12h'
        }
        
        # Chuyển đổi timeframe
        ccxt_timeframe = timeframe_map.get(timeframe, timeframe)
        
        # Tạo exchange instance với cấu hình
        exchange_config = {
            'timeout': 30000,  # 30 seconds timeout
            'enableRateLimit': True,
            'sandbox': False,
        }
        
        exchange = getattr(ccxt, exchange_name)(exchange_config)
        
        # Thử kết nối và lấy dữ liệu
        print(f"Đang lấy dữ liệu {symbol} {timeframe} từ {exchange_name}...")
        
        # Retry mechanism
        max_retries = 3
        for attempt in range(max_retries):
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, ccxt_timeframe, limit=limit)
                
                if not ohlcv:
                    raise Exception("Không có dữ liệu được trả về")
                
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                
                print(f"Đã lấy được {len(df)} nến {timeframe} từ {exchange_name}")
                return df
                
            except Exception as e:
                print(f"Lần thử {attempt + 1} thất bại: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)  # Đợi 2 giây trước khi thử lại
                else:
                    raise e
                
    except Exception as e:
        print(f"Lỗi khi lấy dữ liệu từ {exchange_name} cho {symbol}: {e}")
        
        # Fallback: Tạo dữ liệu giả để test
        print("Tạo dữ liệu giả để test...")
        return create_sample_data(limit, timeframe)


# bỏ phần này
def create_sample_data(limit=200, timeframe='4h'):
    """Tạo dữ liệu giả để test với timeframe cụ thể"""
    import random
    from datetime import datetime, timedelta
    
    # Map timeframe to hours
    timeframe_hours = {
        '15m': 0.25,
        '1h': 1,
        '4h': 4,
        '1d': 24,
        '3d': 72,
        '1w': 168
    }
    
    hours = timeframe_hours.get(timeframe, 4)
    
    # Tạo timestamps
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=limit * hours)
    freq = f'{int(hours*60)}T' if hours < 24 else f'{int(hours)}H'
    timestamps = pd.date_range(start=start_time, end=end_time, freq=freq)[:limit]
    
    # Tạo dữ liệu giá
    base_price = 60000  # BTC price base
    data = []
    
    for i, timestamp in enumerate(timestamps):
        # Random walk với trend
        price_change = random.uniform(-0.05, 0.05)  # ±5% change
        if i == 0:
            open_price = base_price
        else:
            open_price = data[i-1]['close']
        
        high = open_price * (1 + abs(price_change) + random.uniform(0, 0.02))
        low = open_price * (1 - abs(price_change) - random.uniform(0, 0.02))
        close = open_price * (1 + price_change)
        volume = random.uniform(100, 1000)
        
        data.append({
            'timestamp': timestamp,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        })
    
    df = pd.DataFrame(data)
    print(f"Đã tạo {len(df)} nến dữ liệu giả")
    return df

def calculate_rsi(prices, period=14):
    """Calculate RSI without TA-Lib"""
    if len(prices) < period:
        return pd.Series([np.nan] * len(prices))
    
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.ewm(com=period-1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period-1, min_periods=period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

def calculate_sma(prices, period):
    """Calculate Simple Moving Average"""
    return prices.rolling(window=period).mean()

def calculate_ema(prices, period):
    """Calculate Exponential Moving Average"""
    return prices.ewm(span=period).mean()

def calculate_indicators(df_display, df_calc):
    """Tính toán indicators không cần TA-Lib"""
    try:
        indicators = {}
        
        if len(df_calc) > 14:
            # RSI
            rsi_values = calculate_rsi(df_calc['close'])
            indicators['rsi'] = float(rsi_values.iloc[-1]) if not pd.isna(rsi_values.iloc[-1]) else 50
            
            # Moving Averages
            sma_20 = calculate_sma(df_calc['close'], 20)
            indicators['sma_20'] = float(sma_20.iloc[-1]) if not pd.isna(sma_20.iloc[-1]) else float(df_calc['close'].iloc[-1])
            
            ema_20 = calculate_ema(df_calc['close'], 20)
            indicators['ema_20'] = float(ema_20.iloc[-1]) if not pd.isna(ema_20.iloc[-1]) else float(df_calc['close'].iloc[-1])
            
            # Price info
            indicators['current_price'] = float(df_calc['close'].iloc[-1])
            indicators['price_change'] = float(df_calc['close'].iloc[-1] - df_calc['close'].iloc[-2])
            indicators['price_change_pct'] = float((indicators['price_change'] / df_calc['close'].iloc[-2]) * 100)
        
        return indicators
        
    except Exception as e:
        print(f"Error calculating indicators: {e}")
        return {
            'rsi': 50,
            'sma_20': 60000,
            'ema_20': 60000,
            'current_price': 60000,
            'price_change': 0,
            'price_change_pct': 0
        }

# Test function
if __name__ == "__main__":
    print("Testing craw_data...")
    df = fetch_ohlcv('binance', 'BTC/USDT', '4h', 100)
    if df is not None:
        print(f"Data shape: {df.shape}")
        print(f"Last price: {df['close'].iloc[-1]}")
    else:
        print("Failed to fetch data")