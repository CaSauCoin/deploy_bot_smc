import os
import asyncio
import logging
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from AdvancedSMC import AdvancedSMC
import json

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO,
    stream=sys.stdout
)
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
🚀 *Chào mừng đến với Trading Bot SMC!*

Bot này sử dụng Smart Money Concepts để phân tích thị trường crypto.

*Các tính năng:*
• 📊 Phân tích Order Blocks
• 🎯 Tìm Fair Value Gaps (FVG)
• 📈 Break of Structure (BOS)
• 💧 Liquidity Zones
• 📉 Indicators (RSI, MA)
• 🔔 Trading Signals

Chọn một tùy chọn bên dưới để bắt đầu:
        """
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler cho các nút inline"""
        query = update.callback_query
        await query.answer()
        
        try:
            if query.data.startswith('analyze_'):
                symbol = query.data.replace('analyze_', '')
                await self.send_analysis(query, symbol, '4h')
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
                parts = query.data.replace('tf_', '').split('_')
                if len(parts) >= 2:
                    symbol = '_'.join(parts[:-1]).replace('_', '/')
                    timeframe = parts[-1]
                    await self.send_analysis(query, symbol, timeframe)
        except Exception as e:
            logger.error(f"Error in button_handler: {e}")
            await query.edit_message_text("❌ Có lỗi xảy ra. Vui lòng thử lại.")

    async def send_analysis(self, query, symbol, timeframe='4h'):
        """Gửi phân tích SMC cho symbol với timeframe cụ thể"""
        await query.edit_message_text("🔄 Đang phân tích... Vui lòng đợi...")
        
        try:
            # Lấy phân tích từ SMC
            result = self.smc_analyzer.get_trading_signals(symbol, timeframe)
            
            if result is None:
                await query.edit_message_text("❌ Không thể lấy dữ liệu. Vui lòng thử lại sau.")
                return
            
            # Format message
            message = self.format_analysis_message(result)
            
            # Tạo keyboard
            symbol_encoded = symbol.replace('/', '_')
            keyboard = [
                [InlineKeyboardButton("📊 15m", callback_data=f'tf_{symbol_encoded}_15m'),
                 InlineKeyboardButton("📊 1h", callback_data=f'tf_{symbol_encoded}_1h'),
                 InlineKeyboardButton("📊 4h", callback_data=f'tf_{symbol_encoded}_4h')],
                [InlineKeyboardButton("📊 1d", callback_data=f'tf_{symbol_encoded}_1d'),
                 InlineKeyboardButton("🔄 Refresh", callback_data=f'tf_{symbol_encoded}_{timeframe}'),
                 InlineKeyboardButton("🏠 Menu", callback_data='start')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in analysis: {e}")
            await query.edit_message_text(f"❌ Lỗi khi phân tích: {str(e)}")
    
    def format_analysis_message(self, result):
        """Format kết quả phân tích thành message Telegram"""
        try:
            smc = result['smc_analysis']
            indicators = result['indicators']
            trading_signals = result.get('trading_signals', {})
            
            # Header
            message = f"📊 *Phân tích {result['symbol']} - {result['timeframe']}*\n\n"
            
            # Price info
            message += f"💰 *Giá hiện tại:* ${result['current_price']:,.2f}\n"
            
            # Indicators
            rsi = indicators.get('rsi', 50)
            rsi_emoji = "🟢" if rsi < 30 else ("🔴" if rsi > 70 else "🟡")
            message += f"📈 *RSI:* {rsi_emoji} {rsi:.1f}\n\n"
            
            # SMC Analysis
            message += "🔍 *SMC ANALYSIS:*\n"
            message += f"📦 *Order Blocks:* {len(smc['order_blocks'])}\n"
            message += f"🎯 *Fair Value Gaps:* {len(smc['fair_value_gaps'])}\n"
            message += f"🔄 *Break of Structure:* {len(smc['break_of_structure'])}\n"
            message += f"💧 *Liquidity Zones:* {len(smc['liquidity_zones'])}\n\n"
            
            # Trading Signals
            if trading_signals:
                message += "🔔 *TRADING SIGNALS:*\n"
                entry_long = trading_signals.get('entry_long', [])
                entry_short = trading_signals.get('entry_short', [])
                
                if entry_long:
                    message += f"🟢 *Long Signals:* {len(entry_long)}\n"
                if entry_short:
                    message += f"🔴 *Short Signals:* {len(entry_short)}\n"
                
                if not entry_long and not entry_short:
                    message += "⏸️ Không có signal nào\n"
            
            # Timestamp
            from datetime import datetime
            timestamp = datetime.fromtimestamp(result['timestamp'])
            message += f"\n🕐 *Cập nhật:* {timestamp.strftime('%H:%M:%S %d/%m/%Y')}"
            
            return message
            
        except Exception as e:
            logger.error(f"Error formatting message: {e}")
            return f"❌ Lỗi khi format message cho {result.get('symbol', 'N/A')}"

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
🚀 *Trading Bot SMC*

*Các tính năng:*
• 📊 Order Blocks Analysis
• 🎯 Fair Value Gaps Detection
• 📈 Break of Structure Signals
• 💧 Liquidity Zones Mapping
• 🔔 Entry/Exit Signals

Chọn cặp để phân tích:
        """
        
        await query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def show_pair_selection(self, query):
        """Hiển thị menu chọn cặp trading"""
        keyboard = [
            [InlineKeyboardButton("₿ BTC/USDT", callback_data='pair_BTC/USDT'),
             InlineKeyboardButton("Ξ ETH/USDT", callback_data='pair_ETH/USDT')],
            [InlineKeyboardButton("🟡 BNB/USDT", callback_data='pair_BNB/USDT'),
             InlineKeyboardButton("🔵 ADA/USDT", callback_data='pair_ADA/USDT')],
            [InlineKeyboardButton("🟣 SOL/USDT", callback_data='pair_SOL/USDT'),
             InlineKeyboardButton("🔴 DOT/USDT", callback_data='pair_DOT/USDT')],
            [InlineKeyboardButton("🏠 Quay lại", callback_data='start')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📊 *Chọn cặp trading để phân tích:*", 
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def show_help(self, query):
        """Hiển thị hướng dẫn sử dụng"""
        help_text = """
📖 *Hướng dẫn Trading Bot SMC*

*Smart Money Concepts:*

🎯 *Order Blocks (OB):* 
Khu vực mà smart money đặt lệnh lớn

📈 *Fair Value Gap (FVG):*
Khoảng trống giá trên chart

🔄 *Break of Structure (BOS):*
Phá vỡ mức swing high/low trước đó

💧 *Liquidity Zones:*
Khu vực có thanh khoản cao

⚠️ *Lưu ý:* 
Đây là công cụ hỗ trợ phân tích, không phải lời khuyên đầu tư.
        """
        
        keyboard = [[InlineKeyboardButton("🏠 Quay lại Menu", callback_data='start')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    def run(self):
        """Chạy bot"""
        try:
            # Tạo application
            self.application = Application.builder().token(self.token).build()
            
            # Thêm handlers
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CallbackQueryHandler(self.button_handler))
            
            # Chạy bot
            logger.info("🤖 Bot starting...")
            self.application.run_polling(drop_pending_updates=True)
            
        except Exception as e:
            logger.error(f"Error running bot: {e}")
            raise

if __name__ == "__main__":
    # Lấy BOT_TOKEN từ environment variable
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN environment variable not found!")
        sys.exit(1)
    
    logger.info("Starting Trading SMC Bot...")
    bot = TradingBot(BOT_TOKEN)
    bot.run()