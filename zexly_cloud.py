import os
import requests
import yfinance as yf
from datetime import datetime
import pytz

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def get_deep_analysis():
    # 1. Cek Harga Gold
    gold_url = "https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDT"
    price = float(requests.get(gold_url).json()['price'])
    
    # 2. Analisa Sentimen DXY (Dollar)
    dxy = yf.Ticker("DX-Y.NYB")
    dxy_data = dxy.history(period="2d")
    dxy_change = dxy_data['Close'].iloc[-1] - dxy_data['Close'].iloc[-2]
    dxy_stat = "📈 MENGUAT (Tekanan pada Gold)" if dxy_change > 0 else "📉 MELEMAH (Support buat Gold)"
    
    # 3. Cek Jam Sesi (ZEXLY Rules)
    wib = pytz.timezone('Asia/Jakarta')
    now = datetime.now(wib)
    session = "LONDON/NY" if (14 <= now.hour <= 23) else "ASIAN/BREAK"
    
    # 4. Rangkuman Pesan
    msg = (
        f"🌍 *ZEXLY CLOUD ORACLE REPORT*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 *XAUUSD:* ${price}\n"
        f"💵 *DXY Sentiment:* {dxy_stat}\n"
        f"🕒 *Current Session:* {session}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
        f"📰 *Fundamental Note:* Perhatikan pergerakan Dollar. Jika DXY naik tajam, "
        f"abaikan setup BUY meskipun di zona Demand untuk menghindari SL Hunter.\n"
        f"💡 *Saran:* Selalu cek kalender ekonomi sebelum eksekusi."
    )
    
    send_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text={msg}&parse_mode=Markdown"
    requests.get(send_url)

if __name__ == "__main__":
    get_deep_analysis()

