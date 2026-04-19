import os
import requests
import yfinance as yf
from datetime import datetime
import pytz

# Mengambil data dari Secrets GitHub
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def get_gold_price():
    """Mengambil harga emas spot dari Yahoo Finance (Sangat stabil untuk Cloud)"""
    try:
        gold = yf.Ticker("GC=F")
        data = gold.history(period="1d")
        if not data.empty:
            price = data['Close'].iloc[-1]
            return round(float(price), 2)
    except Exception as e:
        print(f"Gagal ambil harga Yahoo: {e}")
    
    # Cadangan: Ambil dari Binance jika Yahoo gagal
    try:
        res = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDT", timeout=10).json()
        return round(float(res['price']), 2)
    except:
        return None

def get_deep_analysis():
    price = get_gold_price()
    if not price:
        print("Error: Harga emas tidak ditemukan.")
        return

    # 1. Analisa Sentimen Dollar (DXY)
    try:
        dxy = yf.Ticker("DX-Y.NYB")
        dxy_data = dxy.history(period="2d")
        dxy_now = dxy_data['Close'].iloc[-1]
        dxy_prev = dxy_data['Close'].iloc[-2]
        dxy_change = dxy_now - dxy_prev
        dxy_stat = "📈 MENGUAT" if dxy_change > 0 else "📉 MELEMAH"
    except:
        dxy_now, dxy_stat, dxy_change = 0, "⚠️ Data Delay", 0

    # 2. Logika Interpretasi Fundamental
    wib = pytz.timezone('Asia/Jakarta')
    now = datetime.now(wib)
    
    if dxy_change > 0.05:
        impact = "🔴 *BEARISH IMPACT:* Dollar menguat. Gold cenderung tertekan. Cari konfirmasi SELL di area Supply."
    elif dxy_change < -0.05:
        impact = "🟢 *BULLISH IMPACT:* Dollar melemah. Peluang kenaikan Gold. Cari konfirmasi BUY di area Demand."
    else:
        impact = "⚪ *NEUTRAL:* Pergerakan stabil. Fokus pada teknikal SNR dan Market Structure."

    # 3. Menyusun Pesan
    msg = (
        f"🏛️ *ZEXLY CLOUD ORACLE V3.2*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 *GOLD (XAUUSD):* `${price}`\n"
        f"💵 *DXY Index:* `{dxy_now:.2f}` ({dxy_stat})\n"
        f"🕒 *Sesi:* `{'LONDON/NY' if (14 <= now.hour <= 23) else 'ASIAN/REST'}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 *ANALISA FUNDAMENTAL:*\n"
        f"{impact}\n\n"
        f"💡 *Saran:* Pantau korelasi DXY. Jika DXY naik tapi Gold juga naik, waspada 'Smart Money Trap'!"
    )

    # 4. Perbaikan Cara Kirim Pesan (Method GET agar lebih simpel)
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.get(url, params=payload, timeout=10)
        if response.status_code == 200:
            print("✅ Pesan berhasil terkirim ke Telegram!")
        else:
            print(f"❌ Gagal kirim. Response: {response.text}")
    except Exception as e:
        print(f"❌ Error saat mengirim pesan: {e}")

if __name__ == "__main__":
    get_deep_analysis()
