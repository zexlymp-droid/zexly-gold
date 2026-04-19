import requests
import yfinance as yf
from datetime import datetime
import pytz

# MASUKKAN LANGSUNG DI SINI (Jangan pakai os.getenv)
TOKEN = "8706271896:AAH6ZL3GJ-CarezdO-TapTJnnyZy6QZ4w2Y"
CHAT_ID = "5801538218"

def get_gold_price():
    try:
        gold = yf.Ticker("GC=F")
        price = gold.history(period="1d")['Close'].iloc[-1]
        return round(float(price), 2)
    except:
        return None

def get_deep_analysis():
    price = get_gold_price()
    if not price: return

    # Analisa DXY
    try:
        dxy = yf.Ticker("DX-Y.NYB").history(period="2d")
        dxy_now = dxy['Close'].iloc[-1]
        dxy_change = dxy_now - dxy['Close'].iloc[-2]
        dxy_stat = "📈 NAIK" if dxy_change > 0 else "📉 TURUN"
    except:
        dxy_now, dxy_stat = 0, "Delay"

    wib = pytz.timezone('Asia/Jakarta')
    now = datetime.now(wib)
    
    msg = (
        f"🚀 *ZEXLY CLOUD LIVE*\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 *Gold:* `${price}`\n"
        f"💵 *DXY:* `{dxy_now:.2f}` ({dxy_stat})\n"
        f"🕒 *Jam:* {now.strftime('%H:%M')} WIB\n"
        f"━━━━━━━━━━━━━━\n"
        f"✅ *Status:* Server GitHub Aktif!"
    )

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.get(url, params={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

if __name__ == "__main__":
    get_deep_analysis()
