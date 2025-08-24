# backend/app.py
from flask import Flask, jsonify, request
from flask_cors import CORS
from craw_data import fetch_ohlcv, calculate_indicators
from AdvancedSMC import AdvancedSMC
import ccxt
import time

app = Flask(__name__)
CORS(app) # Cho phép truy cập từ domain khác (Frontend)

# Khởi tạo SMC analyzer
smc_analyzer = AdvancedSMC(exchange_name='binance')

# --- CẤU HÌNH ---
CANDLE_LIMIT_DISPLAY = 4000
CANDLE_LIMIT_CALC = 200

# Cache để lưu danh sách tokens (tránh gọi API quá nhiều)
tokens_cache = {}

def get_exchange_instance(exchange_name):
    """Tạo instance của exchange"""
    try:
        exchange_map = {
            'binance': ccxt.binance(),
            'bitget': ccxt.bitget(),
            'bybit': ccxt.bybit(),
            'mexc': ccxt.mexc(),
            'kucoin': ccxt.kucoin(),
            'okx': ccxt.okx(),
            'gate.io': ccxt.gateio(),
            'huobi': ccxt.huobi()
        }
        return exchange_map.get(exchange_name.lower())
    except Exception:
        return None

def fetch_exchange_tokens(exchange_name):
    """Lấy danh sách tokens từ exchange"""
    try:
        exchange = get_exchange_instance(exchange_name)
        if not exchange or not exchange.has['fetchMarkets']:
            return []

        markets = exchange.load_markets()
        
        usdt_pairs = [
            symbol for symbol, market in markets.items()
            if market.get('quote', '').upper() == 'USDT'
            and market.get('active', True)
            and market.get('spot', False) # Đảm bảo là cặp spot
            and ':' not in symbol # Loại bỏ các cặp futures/swap nếu có
        ]
        
        usdt_pairs.sort()
        
        popular_pairs = [
            'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT',
            'DOGE/USDT', 'ADA/USDT', 'AVAX/USDT', 'DOT/USDT', 'MATIC/USDT'
        ]
        
        final_pairs = [pair for pair in popular_pairs if pair in usdt_pairs]
        remaining_pairs = [pair for pair in usdt_pairs if pair not in popular_pairs]
        final_pairs.extend(remaining_pairs)
        
        print(f"Tìm thấy {len(final_pairs)} cặp USDT spot trên {exchange_name}")
        return final_pairs
        
    except Exception as e:
        print(f"Lỗi khi lấy danh sách tokens từ {exchange_name}: {e}")
        return ['BTC/USDT', 'ETH/USDT', 'BNB/USDT']

# --- API Endpoints ---

@app.route('/api/tokens', methods=['GET'])
def get_tokens():
    """Cung cấp danh sách các token từ exchange."""
    exchange = request.args.get('exchange', 'binance').lower()
    
    cache_key = f"{exchange}_tokens"
    if cache_key in tokens_cache and time.time() - tokens_cache[cache_key]['timestamp'] < 300:
        print(f"Trả về {len(tokens_cache[cache_key]['tokens'])} tokens từ cache cho {exchange}")
        return jsonify(tokens_cache[cache_key]['tokens'])
    
    tokens = fetch_exchange_tokens(exchange)
    
    tokens_cache[cache_key] = {'tokens': tokens, 'timestamp': time.time()}
    
    print(f"Trả về {len(tokens)} tokens mới cho exchange: {exchange}")
    return jsonify(tokens)

@app.route('/api/smc-analysis', methods=['GET'])
def get_smc_analysis():
    """API endpoint cho phân tích SMC"""
    try:
        symbol = request.args.get('symbol', 'BTC/USDT')
        timeframe = request.args.get('timeframe', '4h')
        
        # Lấy phân tích SMC
        analysis = smc_analyzer.get_trading_signals(symbol, timeframe)
        
        if analysis is None:
            return jsonify({'error': 'Không thể lấy dữ liệu'}), 200
        
        return jsonify(analysis)
        
    except Exception as e:
        print(f"Error in SMC analysis: {str(e)}")
        return jsonify({'error': str(e)}), 200

@app.route('/api/chart-data', methods=['GET'])
def get_chart_data():
    """API endpoint cho dữ liệu chart"""
    try:
        symbol = request.args.get('symbol', 'BTC/USDT')
        timeframe = request.args.get('timeframe', '4h')
        
        # Lấy dữ liệu OHLCV
        df = fetch_ohlcv('binance', symbol, timeframe, 200)
        if df is None:
            return jsonify({'error': 'Không thể lấy dữ liệu'}), 200

        # Chuyển đổi dữ liệu cho chart
        candles = []
        for _, row in df.iterrows():
            candles.append([
                int(row['timestamp'].timestamp() * 1000),  # timestamp in ms
                float(row['open']),
                float(row['high']),
                float(row['low']),
                float(row['close']),
                float(row['volume'])
            ])
        
        return jsonify({
            'candles': candles,
            'symbol': symbol,
            'timeframe': timeframe
        })
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 200

@app.route('/api/test', methods=['GET'])
def test_connection():
    """Test API connection"""
    return jsonify({"status": "success", "message": "API đang hoạt động"})

if __name__ == '__main__':
    print("Khởi động Flask server...")
    app.run(debug=True, port=5000)