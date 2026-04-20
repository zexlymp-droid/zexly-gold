import requests
import yfinance as yf
from datetime import datetime
import pytz
import os

# KONFIGURASI
TOKEN = "8706271896:AAH6ZL3GJ-CarezdO-TapTJnnyZy6QZ4w2Y"
CHAT_ID = "5801538218"

def analyze_and_send():
    try:
        # 1. Ambil Data Gold
        gold = yf.Ticker("GC=F")
        df = gold.history(period="5d", interval="1h")
        price = round(df['Close'].iloc[-1], 2)
        
        # 2. Hitung Range H4 (3 Zona Zexly)
        high_h4 = df['High'].max()
        low_h4 = df['Low'].min()
        range_total = high_h4 - low_h4
        one_third = range_total / 3
        
        upper_limit = high_h4 - one_third
        lower_limit = low_h4 + one_third
        
        # Penentuan Status & Bias
        if price >= upper_limit:
            status = "🔴 UPPER ZONE (Sell Only)"
            note = "Cari base valid di M30/M15 untuk Sell."
        elif price <= lower_limit:
            status = "🔵 LOWER ZONE (Buy Only)"
            note = "Cari base valid di M30/M15 untuk Buy."
        else:
            status = "🟡 MIDDLE ZONE (No Trade)"
            note = "Harga di tengah. Tutup platform atau tunggu zona."

        # 3. Ambil Screenshot Chart (Via API)
        # Menampilkan chart XAUUSD dengan indikator standar
        img_url = f"https://api.screenshotmachine.com/?key=bc893b&url=https://www.tradingview.com/chart/?symbol=FX_IDC:XAUUSD&dimension=1024x768&delay=5000"
        
        # 4. Susun Pesan Telegram
        wib = pytz.timezone('Asia/Jakarta')
        waktu = datetime.now(wib).strftime('%H:%M WIB')
        
        caption = (
            f"🦅 *ZEXLY VISION MONITOR*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 *Gold Price:* `${price}`\n"
            f"📍 *H4 Status:* `{status}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📝 *Zexly Note:* \n_{note}_\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🕒 `{waktu}` | *Visual Analysis*"
        )
        
        # 5. Kirim ke Telegram (Foto + Caption)
        params = {
            "chat_id": CHAT_ID,
            "photo": img_url,
            "caption": caption,
            "parse_mode": "Markdown"
        }
        requests.get(f"https://api.telegram.org/bot{TOKEN}/sendPhoto", params=params)
        print(f"Laporan terkirim pada {waktu}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze_and_send()
