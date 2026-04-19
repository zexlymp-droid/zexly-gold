import os
import requests
import yfinance as yf
from datetime import datetime
import pytz

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def get_gold_price():
    # Menggunakan beberapa sumber cadangan untuk harga Gold
    urls = [
        "https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDT",
        "https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDC"
    ]
    for url in urls:
        try:
            res = requests.get(url, timeout=10).json()
            if 'price' in res:
                return float(res['price'])
        except:
            continue
    return None

def get_deep_analysis():
    price = get_gold_price()
    if not price:
        print("Gagal mengambil harga emas.")
        return

    # 1. ANALISA SENTIMEN DXY (Korelasi Negatif dengan Gold)
    try:
        dxy = yf.Ticker("DX-Y.NYB")
        dxy_data = dxy.history(period="2d")
        dxy_now = dxy_data['Close'].iloc[-1]
        dxy_prev = dxy_data['Close'].iloc[-2]
        dxy_change = dxy_now - dxy_prev
        dxy_stat = "📈 MENGUAT" if dxy_change > 0 else "📉 MELEMAH"
    except:
        dxy_stat = "⚠️ Data DXY Delay"
        dxy_now = 0

    # 2. ANALISA FUNDAMENTAL & NEWS IMPACT
    # Kita buat logika interpretasi berdasarkan sesi dan pergerakan DXY
    wib = pytz.timezone('Asia/Jakarta')
    now = datetime.now(wib)
    
    impact_msg = ""
    if dxy_change > 0.10:
        impact_msg = "🔴 *BEARISH IMPACT:* Dollar sedang menguat tajam. Hati-hati jebakan 'Fakeout' di area Support/Demand. Utamakan Sell di area Supply."
    elif dxy_change < -0.10:
        impact_msg = "🟢 *BULLISH IMPACT:* Dollar tertekan. Tekanan beli pada Gold meningkat. Area Demand akan sangat valid jika ada konfirmasi M5."
    else:
        impact_msg = "⚪ *NEUTRAL:* Pergerakan stabil. Ikuti teknikal murni sesuai Equidistant Channel."

    # 3. RANGKUMAN ANALISA SPESIFIK
    msg = (
        f"🏛️ *ZEXLY CLOUD ORACLE V3.1*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 *XAUUSD:* `${price}`\n"
        f"💵 *DXY Index:* `{dxy_now:.2f}` ({dxy_stat})\n"
        f"🕒 *Sesi:* `{'LONDON/NY' if (14 <= now.hour <= 23) else 'ASIAN/REST'}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 *SENTIMEN & NEWS IMPACT:*\n"
        f"{impact_msg}\n\n"
        f"🔍 *Deep Note:* Analisa ini menggabungkan korelasi Intermarket. Jika DXY dan Gold bergerak searah, itu tanda manipulasi besar. *Stay Sharp!*"
    )
    
    send_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(send_url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

if __name__ == "__main__":
    get_deep_analysis()

