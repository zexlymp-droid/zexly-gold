import logging
import requests
import pytz
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# --- KONFIGURASI ---
TOKEN = "8706271896:AAH6ZL3GJ-CarezdO-TapTJnnyZy6QZ4w2Y"
USER_ID = 5801538218

# Data Global
zexly_config = {
    "bias": "WAIT",
    "snr": 0.0,
    "monitoring": False,
    "last_alert_price": 0.0
}

# --- FUNGSI ANALISA (CORE LOGIC) ---
def get_gold_price():
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDT"
        return float(requests.get(url).json()['price'])
    except: return None

def check_session():
    wib = pytz.timezone('Asia/Jakarta')
    now = datetime.now(wib)
    if (14 <= now.hour <= 17): return "LONDON 🇬🇧"
    if (20 <= now.hour <= 22): return "NEW YORK 🇺🇸"
    return None

# --- FUNGSI BACKGROUND MONITORING ---
async def monitor_market(context: ContextTypes.DEFAULT_TYPE):
    if not zexly_config["monitoring"] or zexly_config["bias"] == "WAIT":
        return

    price = get_gold_price()
    session = check_session()
    
    if price and session:
        bias = zexly_config["bias"]
        snr = zexly_config["snr"]
        
        # Logika Alert: Jarak harga ke SNR (Threshold 1.5 pips)
        is_in_zone = False
        if bias == "BUY" and price <= snr + 1.5: is_in_zone = True
        if bias == "SELL" and price >= snr - 1.5: is_in_zone = True
        
        # Cegah spam alert jika harga masih di area yang sama
        if is_in_zone and abs(price - zexly_config["last_alert_price"]) > 2.0:
            zexly_config["last_alert_price"] = price
            msg = (
                f"⭐ *ZEXLY SIGNAL DETECTED*\n"
                f"━━━━━━━━━━━━━━\n"
                f"🕒 Sesi: {session}\n"
                f"💰 Harga: ${price}\n"
                f"📈 Bias: {bias}\n"
                f"🎯 SNR: {snr}\n"
                f"━━━━━━━━━━━━━━\n"
                f"🔥 *Check M5/M1 untuk konfirmasi!*"
            )
            await context.bot.send_message(chat_id=USER_ID, text=msg, parse_mode="Markdown")

# --- HANDLER TOMBOL & PERINTAH ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != USER_ID: return
    keyboard = [
        [InlineKeyboardButton("📈 Set Bias H4", callback_data="menu_bias")],
        [InlineKeyboardButton("🎯 Set SNR M30", callback_data="menu_snr")],
        [InlineKeyboardButton("🚀 Start Monitor", callback_data="mon_on"),
         InlineKeyboardButton("🛑 Stop", callback_data="mon_off")],
        [InlineKeyboardButton("📊 Status", callback_data="status")]
    ]
    await update.message.reply_text("🎛 *ZEXLY COMMAND CENTER*", 
                                  reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "menu_bias":
        kbd = [[InlineKeyboardButton("BUY", callback_data="set_BUY"), 
                InlineKeyboardButton("SELL", callback_data="set_SELL"),
                InlineKeyboardButton("WAIT", callback_data="set_WAIT")]]
        await query.edit_message_text("Pilih Bias H4 Saat Ini:", reply_markup=InlineKeyboardMarkup(kbd))
    
    elif query.data.startswith("set_"):
        zexly_config["bias"] = query.data.split("_")[1]
        await query.edit_message_text(f"✅ Bias diatur: *{zexly_config['bias']}*", parse_mode="Markdown")
        
    elif query.data == "menu_snr":
        await query.edit_message_text("⌨️ Masukkan angka SNR (Contoh: 2350.5)")
        context.user_data["input_snr"] = True

    elif query.data == "mon_on":
        zexly_config["monitoring"] = True
        await query.edit_message_text("🚀 *Monitoring Aktif!* Bot akan lapor jika harga masuk zona.")

    elif query.data == "mon_off":
        zexly_config["monitoring"] = False
        await query.edit_message_text("🛑 *Monitoring Dimatikan.*")

    elif query.data == "status":
        stat = "AKTIF 🟢" if zexly_config["monitoring"] else "MATI 🔴"
        msg = (f"📝 *STATUS ZEXLY*\n\n"
               f"• Monitor: {stat}\n"
               f"• Bias H4: {zexly_config['bias']}\n"
               f"• SNR M30: {zexly_config['snr']}\n"
               f"• Session: {check_session() or 'OFF'}")
        await query.edit_message_text(msg, parse_mode="Markdown")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("input_snr"):
        try:
            val = float(update.message.text)
            zexly_config["snr"] = val
            context.user_data["input_snr"] = False
            await update.message.reply_text(f"🎯 SNR di-set ke: *{val}*", parse_mode="Markdown")
        except:
            await update.message.reply_text("❌ Kirim angka saja!")

# --- MAIN ---
if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()
    
    # Tambahkan tugas rutin setiap 60 detik
    app.job_queue.run_repeating(monitor_market, interval=60, first=10)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("ZEXLY Bot is running...")
    app.run_polling()
