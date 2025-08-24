import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from AdvancedSMC import AdvancedSMC
import json
import os
import time

# Cấu hình logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self, token):
        self.token = token
        self.smc_analyzer = AdvancedSMC()
        self.application = None
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler cho command /start"""
        keyboard = [
            [InlineKeyboardButton("📊 Phân tích BTC/USDT", callback_data='analyze_BTC/USDT')],
            [InlineKeyboardButton("📈 Phân tích ETH/USDT", callback_data='analyze_ETH/USDT')],
            [InlineKeyboardButton("🔍 Chọn cặp khác", callback_data='select_pair')],
            [InlineKeyboardButton("ℹ️ Hướng dẫn", callback_data='help')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = """
🚀 **Trading Bot SMC!**

Chọn một tùy chọn bên dưới để bắt đầu:
        """
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler cho các nút inline"""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith('analyze_'):
            symbol = query.data.replace('analyze_', '')
            await self.send_analysis(query, symbol, '4h')  # Default timeframe
        elif query.data == 'select_pair':
            await self.show_pair_selection(query)
        elif query.data == 'help':
            await self.show_help(query)
        elif query.data == 'start':
            await self.show_main_menu(query)
        elif query.data.startswith('pair_'):
            symbol = query.data.replace('pair_', '')
            await self.send_analysis(query, symbol, '4h')
        elif query.data.startswith('tf_'):
            # Xử lý timeframe: tf_SYMBOL_TIMEFRAME
            parts = query.data.replace('tf_', '').split('_')
            if len(parts) >= 2:
                symbol = '_'.join(parts[:-1])  # Ghép lại symbol (có thể chứa dấu /)
                symbol = symbol.replace('_', '/')  # Convert back to BTC/USDT format
                timeframe = parts[-1]
                await self.send_analysis(query, symbol, timeframe)

    async def send_analysis(self, query, symbol, timeframe='4h'):
        """Gửi phân tích SMC cho symbol với timeframe cụ thể"""
        await query.edit_message_text("🔄 Đang phân tích... Vui lòng đợi...")
        
        try:
            # Lấy phân tích từ SMC
            result = self.smc_analyzer.get_trading_signals(symbol, timeframe)
            
            if result is None:
                await query.edit_message_text("❌ Không thể lấy dữ liệu. Vui lòng thử lại sau.")
                return
            
            # Format message với error handling
            try:
                message = self.format_analysis_message(result)
            except Exception as e:
                logger.error(f"Error formatting message: {e}")
                message = f"❌ Lỗi khi format message cho {symbol}\nVui lòng thử lại sau."
                await query.edit_message_text(message)
                return
            
            # Tạo keyboard với nhiều timeframe hơn
            symbol_encoded = symbol.replace('/', '_')  # BTC/USDT -> BTC_USDT for callback
            keyboard = [
                [InlineKeyboardButton("📊 15m", callback_data=f'tf_{symbol_encoded}_15m'),
                 InlineKeyboardButton("📊 1h", callback_data=f'tf_{symbol_encoded}_1h'),
                 InlineKeyboardButton("📊 4h", callback_data=f'tf_{symbol_encoded}_4h')],
                [InlineKeyboardButton("📊 1d", callback_data=f'tf_{symbol_encoded}_1d'),
                 InlineKeyboardButton("📊 3d", callback_data=f'tf_{symbol_encoded}_3d'),
                 InlineKeyboardButton("📊 1w", callback_data=f'tf_{symbol_encoded}_1w')],
                [InlineKeyboardButton("🔄 Refresh", callback_data=f'tf_{symbol_encoded}_{timeframe}'),
                 InlineKeyboardButton("🏠 Menu", callback_data='start')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Gửi message với error handling cho markdown
            try:
                await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Markdown parse error: {e}")
                # Fallback: gửi message không có markdown
                plain_message = message.replace('*', '').replace('_', '')
                await query.edit_message_text(plain_message, reply_markup=reply_markup)
        
        except Exception as e:
            logger.error(f"Error in analysis: {e}")
            error_msg = f"❌ Lỗi khi phân tích {symbol}:\n{str(e)[:100]}..."
            await query.edit_message_text(error_msg)
    
    def format_analysis_message(self, result):
        """Format kết quả phân tích thành message Telegram với thông tin chi tiết"""
        smc = result['smc_analysis']
        indicators = result['indicators']
        trading_signals = result.get('trading_signals', {})
        # entry = result.get('entry', None)
        # exit = result.get('exit', None)

        # Header
        message = f"📊 *Phân tích {result['symbol']} - {result['timeframe']}*\n\n"
        
        # Price info
        message += f"💰 *Giá hiện tại:* ${result['current_price']:,.2f}\n"
        
        # Indicators
        rsi = indicators.get('rsi', 50)
        rsi_emoji = "🟢" if rsi < 30 else ("🔴" if rsi > 70 else "🟡")
        message += f"📈 *RSI:* {rsi_emoji} {rsi:.1f}\n"
        message += f"📊 *Giá sát:* ${indicators.get('sma_20', 0):,.2f}\n"
        message += f"📉 *Giá dự tốt:* ${indicators.get('ema_20', 0):,.2f}\n\n"
        
        # Price change
        price_change = indicators.get('price_change_pct', 0)
        change_emoji = "📈" if price_change > 0 else "📉"
        message += f"{change_emoji} *Thay đổi:* {price_change:+.2f}%\n\n"
        
        # SMC Analysis - Detailed
        message += "🔍 *ANALYSIS:*\n"
        
        # Order Blocks
        ob_count = len(smc['order_blocks'])
        message += f"📦 *Order Blocks:* {ob_count}\n"
        if ob_count > 0:
            try:
                latest_ob = smc['order_blocks'][-1]
                ob_emoji = "🟢" if latest_ob['type'] == 'bullish_ob' else "🔴"
                ob_type = latest_ob['type'].replace('_', ' ').upper()
                # message += f"   {ob_emoji} Gần nhất: {ob_type}\n"
                
                # Kiểm tra giá trị không phải None
                if latest_ob.get('low') is not None and latest_ob.get('high') is not None:
                    # message += f"   📍 Level: ${latest_ob['low']:,.0f} - ${latest_ob['high']:,.0f}\n"
                    print(f"Order Block: {latest_ob}")  # Debug log
            except (KeyError, TypeError, IndexError):
                print("Dữ liệu OB không đầy đủ")
    
        # Fair Value Gaps
        fvg_count = len(smc['fair_value_gaps'])
        # message += f"🎯 *Fair Value Gaps:* {fvg_count}\n"
        if fvg_count > 0:
            try:
                latest_fvg = smc['fair_value_gaps'][-1]
                fvg_emoji = "🟢" if latest_fvg['type'] == 'bullish_fvg' else "🔴"
                fvg_type = latest_fvg['type'].replace('_', ' ').upper()
                # message += f"   {fvg_emoji} Gần nhất: {fvg_type}\n"
                
                # Kiểm tra giá trị không phải None
                if latest_fvg.get('top') is not None and latest_fvg.get('bottom') is not None:
                    print(f"Fair Value Gap: {latest_fvg}")  # Debug log
                    # message += f"   📍 Gap: ${latest_fvg['bottom']:,.0f} - ${latest_fvg['top']:,.0f}\n"
            except (KeyError, TypeError, IndexError):
                print("Dữ liệu FVG không đầy đủ")
                # message += "   ⚠️ Dữ liệu FVG không đầy đủ\n"
    
        # Break of Structure
        bos_count = len(smc['break_of_structure'])
        message += f"🔄 *Structure:* {bos_count}\n"
        if bos_count > 0:
            try:
                latest_bos = smc['break_of_structure'][-1]
                bos_emoji = "🟢" if latest_bos['type'] == 'bullish_bos' else "🔴"
                bos_type = latest_bos['type'].replace('_', ' ').upper()
                message += f"   {bos_emoji} Gần nhất: {bos_type}\n"
                message += f"   📍 Price: ${latest_bos['price']:,.2f}\n"
            except (KeyError, TypeError, IndexError):
                print("Dữ liệu BOS không đầy đủ")
                # message += "   ⚠️ Dữ liệu BOS không đầy đủ\n"
    
        # Liquidity Zones
        lz_count = len(smc['liquidity_zones'])
        message += f"💧 *Liquidity Zones:* {lz_count}\n"
        if lz_count > 0:
            try:
                latest_lz = smc['liquidity_zones'][-1]
                lz_emoji = "🔵" if latest_lz['type'] == 'buy_side_liquidity' else "🟠"
                lz_type = latest_lz['type'].replace('_', ' ').title()
                message += f"   {lz_emoji} Gần nhất: {lz_type}\n"
                message += f"   📍 Level: ${latest_lz['price']:,.2f}\n"
            except (KeyError, TypeError, IndexError):
                print("Dữ liệu LZ không đầy đủ")

        message += "\n"
        
        # Trading Signals
        if trading_signals:
            message += "🔔 *TRADING SIGNALS:*\n"
            
            # Entry signals
            entry_long = trading_signals.get('entry_long', [])
            entry_short = trading_signals.get('entry_short', [])
            exit_long = trading_signals.get('exit_long', [])
            exit_short = trading_signals.get('exit_short', [])
            
            try:
                if entry_long:
                    latest_long = entry_long[-1]
                    message += f"🟢 *Long Signal:* ${latest_long['price']:,.2f}\n"
                    message += f"   🏷️ Tag: {latest_long.get('tag', 'N/A')}\n"
                
                if entry_short:
                    latest_short = entry_short[-1]
                    message += f"🔴 *Short Signal:* ${latest_short['price']:,.2f}\n"
                    message += f"   🏷️ Tag: {latest_short.get('tag', 'N/A')}\n"
                
                if exit_long:
                    message += f"❌ *Exit Long:* {len(exit_long)} signals\n"
                
                if exit_short:
                    message += f"❌ *Exit Short:* {len(exit_short)} signals\n"
                
                if not any([entry_long, entry_short, exit_long, exit_short]):
                    message += "⏸️ Không có signal nào\n"
                    
            except (KeyError, TypeError, IndexError):
                message += "⚠️ Dữ liệu signals không đầy đủ\n"
            
            message += "\n"
        
        # Trading suggestion (advanced)
        try:
            suggestion = self.get_trading_suggestion(smc, indicators, trading_signals)
            message += f"💡 *Gợi ý Trading:*\n{suggestion}\n\n"
        except Exception as e:
            message += "💡 *Gợi ý Trading:* Không thể tạo gợi ý\n\n"
        
        # Timestamp
        try:
            from datetime import datetime
            timestamp = datetime.fromtimestamp(result['timestamp'])
            message += f"🕐 *Cập nhật:* {timestamp.strftime('%H:%M:%S %d/%m/%Y')}"
        except:
            message += f"🕐 *Cập nhật:* {result.get('timestamp', 'N/A')}"
        
        return message
    
    def get_trading_suggestion(self, smc, indicators, trading_signals):
        """Đưa ra gợi ý trading chi tiết - với error handling"""
        suggestions = []
        
        try:
            rsi = indicators.get('rsi', 50)
            
            # RSI analysis
            if rsi > 70:
                suggestions.append("⚠️ Cân nhắc bán")
            elif rsi < 30:
                suggestions.append("🚀 Cân nhắc mua")

            # SMC analysis
            if smc.get('break_of_structure') and len(smc['break_of_structure']) > 0:
                latest_bos = smc['break_of_structure'][-1]
                if latest_bos.get('type') == 'bullish_bos':
                    suggestions.append("📈 Xu hướng tăng")
                elif latest_bos.get('type') == 'bearish_bos':
                    suggestions.append("📉 Xu hướng giảm")
            
            # FVG analysis
            if smc.get('fair_value_gaps'):
                fvg_count = len([fvg for fvg in smc['fair_value_gaps'] if not fvg.get('filled', True)])
                if fvg_count > 2:
                    suggestions.append(f"🎯 Chờ retest")
            
            # Trading signals
            if trading_signals:
                entry_long = trading_signals.get('entry_long', [])
                entry_short = trading_signals.get('entry_short', [])
                
                if entry_long:
                    suggestions.append("🟢 Signal Long xuất hiện")
                if entry_short:
                    suggestions.append("🔴 Signal Short xuất hiện")
            
            if not suggestions:
                suggestions.append("⏸️ Thị trường sideways - Chờ breakout")
                
        except Exception as e:
            logger.error(f"Error in get_trading_suggestion: {e}")
            suggestions.append("⚠️ Không thể phân tích - Kiểm tra lại dữ liệu")
        
        return "\n".join([f"• {s}" for s in suggestions])

    async def show_main_menu(self, query):
        """Hiển thị menu chính"""
        keyboard = [
            [InlineKeyboardButton("📊 Phân tích BTC/USDT", callback_data='analyze_BTC/USDT')],
            [InlineKeyboardButton("📈 Phân tích ETH/USDT", callback_data='analyze_ETH/USDT')],
            [InlineKeyboardButton("🔍 Chọn cặp khác", callback_data='select_pair')],
            [InlineKeyboardButton("ℹ️ Hướng dẫn", callback_data='help')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = """
🚀 **Trading Bot SMC**

**Các tính năng:**
• 📊 Order Blocks Analysis
• 🎯 Fair Value Gaps Detection
• 📈 Break of Structure Signals
• 💧 Liquidity Zones Mapping
• 🔔 Entry/Exit Signals

Chọn cặp để phân tích:
        """
        
        await query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def show_pair_selection(self, query):
        """Hiển thị menu chọn cặp trading với nhiều tùy chọn hơn"""
        keyboard = [
            [InlineKeyboardButton("₿ BTC/USDT", callback_data='pair_BTC/USDT'),
             InlineKeyboardButton("Ξ ETH/USDT", callback_data='pair_ETH/USDT')],
            [InlineKeyboardButton("🟡 BNB/USDT", callback_data='pair_BNB/USDT'),
             InlineKeyboardButton("🔵 WLD/USDT", callback_data='pair_WLD/USDT')],
            [InlineKeyboardButton("🟣 SOL/USDT", callback_data='pair_SOL/USDT'),
             InlineKeyboardButton("🔴 SEI/USDT", callback_data='pair_SEI/USDT')],
            [InlineKeyboardButton("🟠 BNB/USDT", callback_data='pair_BNB/USDT'),
             InlineKeyboardButton("🟢 AGT/USDT", callback_data='pair_AGT/USDT')],
            [InlineKeyboardButton("🟢 PEPE/USDT ", callback_data='pair_PEPE/USDT'),
             InlineKeyboardButton("🟢 SUI/USDT", callback_data='pair_SUI/USDT')],
            [InlineKeyboardButton("🏠 Quay lại", callback_data='start')],

        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📊 **Chọn cặp trading để phân tích:**", 
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def show_help(self, query):
        """Hiển thị hướng dẫn sử dụng"""
        help_text = """
📖 **Hướng dẫn Trading Bot SMC**

**Smart Money Concepts:**

🎯 **Order Blocks (OB):** 
• Khu vực mà smart money đặt lệnh lớn
• Bullish OB: Nến giảm trước BOS tăng
• Bearish OB: Nến tăng trước BOS giảm

📈 **Fair Value Gap (FVG):**
• Khoảng trống giá trên chart
• Thường được "fill" lại bởi giá
• Signal entry khi retest FVG

🔄 **Break of Structure (BOS):**
• Phá vỡ mức swing high/low trước đó
• Xác nhận thay đổi xu hướng
• Bullish BOS: Phá swing high
• Bearish BOS: Phá swing low

💧 **Liquidity Zones:**
• Khu vực có thanh khoản cao
• Smart money thường quét thanh khoản
• BSL: Buy Side Liquidity (trên)
• SSL: Sell Side Liquidity (dưới)

🔔 **Trading Signals:**
• Entry Long: BOS tăng + POI tăng + Swept
• Entry Short: BOS giảm + POI giảm + Swept
• Exit: CHoCH ngược chiều

⚠️ **Lưu ý:** 
Đây là công cụ hỗ trợ phân tích, không phải lời khuyên đầu tư. Luôn quản lý rủi ro và DYOR.
        """
        
        keyboard = [[InlineKeyboardButton("🏠 Quay lại Menu", callback_data='start')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def analysis_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler cho command /analysis"""
        if context.args:
            symbol = context.args[0].upper()
            timeframe = context.args[1] if len(context.args) > 1 else '4h'
            
            await update.message.reply_text(f"🔄 Đang phân tích {symbol} {timeframe}...")
            
            result = self.smc_analyzer.get_trading_signals(symbol, timeframe)
            if result:
                message = self.format_analysis_message(result)
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Không thể phân tích cặp này.")
        else:
            await update.message.reply_text("Cách sử dụng: /analysis BTC/USDT 4h")
    
    def run(self):
        """Chạy bot"""
        # Tạo application
        self.application = Application.builder().token(self.token).build()
        
        # Thêm handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("analysis", self.analysis_command))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        
        # Chạy bot
        print("🤖 Bot đang chạy...")
        self.application.run_polling()

if __name__ == "__main__":
    # Thay YOUR_BOT_TOKEN bằng token thực của bot
    BOT_TOKEN = "8213040530:AAH8oDArhEH75ORttMobEaz6L6lR9CbR53s"
    bot = TradingBot(BOT_TOKEN)
    bot.run()
