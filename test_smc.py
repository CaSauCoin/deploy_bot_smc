from AdvancedSMC import AdvancedSMC
import sys

# Test script
if __name__ == "__main__":
    print("=== Testing SMC Analysis ===")
    
    try:
        smc = AdvancedSMC()
        
        # Test lấy dữ liệu
        print("Đang khởi tạo phân tích SMC...")
        result = smc.get_trading_signals('BTC/USDT', '4h')
        
        if result:
            print(f"\n✅ Thành công!")
            print(f"Symbol: {result['symbol']}")
            print(f"Current Price: ${result['current_price']:,.2f}")
            print(f"RSI: {result['indicators'].get('rsi', 'N/A')}")
            print(f"Order Blocks: {len(result['smc_analysis']['order_blocks'])}")
            print(f"Fair Value Gaps: {len(result['smc_analysis']['fair_value_gaps'])}")
            print(f"Break of Structure: {len(result['smc_analysis']['break_of_structure'])}")
            print(f"Liquidity Zones: {len(result['smc_analysis']['liquidity_zones'])}")
        else:
            print("❌ Không thể lấy dữ liệu")
            
    except Exception as e:
        print(f"❌ Lỗi: {e}")
        import traceback
        traceback.print_exc()