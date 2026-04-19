import requests
import yfinance as yf
from datetime import datetime
import pytz

# DATA LANGSUNG (HARD-CODED)
TOKEN = "8706271896:AAH6ZL3GJ-CarezdO-TapTJnnyZy6QZ4w2Y"
CHAT_ID = "5801538218"

def run_now():
    # 1. Ambil Harga Gold
    try:
        gold = yf.Ticker("GC=F").history(period="1d")
        price = round(gold['Close'].iloc[-1], 2)
    except:
        price = "Check MT5"

    # 2. Ambil Waktu
    wib = pytz.timezone('Asia/Jakarta')
    waktu = datetime.now(wib).strftime('%H:%M WIB')

    # 3. Pesan Sederhana untuk Tes
    teks = f"⚡ *ZEXLY ORACLE CLOUD*\n━━━━━━━━━━━━━━\n💰 Gold: ${price}\n🕒 Jam: {waktu}\n✅ Status: Connected to Server"

    # 4. Kirim dengan cara paling basic
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text={teks}&parse_mode=Markdown"
    res = requests.get(url)
    print(f"Status Kirim: {res.status_code}")

if __name__ == "__main__":
    run_now()

