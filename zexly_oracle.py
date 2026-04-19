import requests
import yfinance as yf
from datetime import datetime
import pytz

# DATA UTAMA
TOKEN = "8706271896:AAH6ZL3GJ-CarezdO-TapTJnnyZy6QZ4w2Y"
CHAT_ID = "5801538218"

def get_snr_zones():
    try:
        # Ambil data 5 hari terakhir dengan interval 1 jam (H1)
        gold = yf.Ticker("GC=F")
        df = gold.history(period="5d", interval="1h")
        
        # Mencari High tertinggi dan Low terendah (Zona SNR)
        resistance = round(df['High'].max(), 2)
        support = round(df['Low'].min(), 2)
        current_price = round(df['Close'].iloc[-1], 2)
        
        return current_price, resistance, support
    except:
        return None, None, None

def analyze_logic():
    price, res, sup = get_snr_zones()
    if not price: return

    # 1. Analisa DXY (Sentimen)
    try:
        dxy = yf.Ticker("DX-Y.NYB").history(period="1d")
        dxy_now = dxy['Close'].iloc[-1]
        dxy_change = dxy_now - dxy['Close'].iloc[0]
        dxy_stat = "Kuat" if dxy_change > 0 else "Lemah"
    except:
        dxy_now, dxy_stat = 0, "N/A"

    # 2. LOGIKA SIGNAL ENTRY (ZEMETHOD)
    # Jika harga mendekati Support dan DXY lemah = BUY
    # Jika harga mendekati Resistance dan DXY kuat = SELL
    signal = "WAITING"
    instruction = "Belum ada konfirmasi zona. Standby."
    
    threshold = 2.0 # Toleransi jarak harga ke zona ($2)

    if price <= (sup + threshold):
        if dxy_stat == "Lemah":
            signal = "🚀 BUY SIGNAL"
            instruction = f"Harga menyentuh Demand Area ({sup}). DXY Lemah mendukung kenaikan. Pasang SL di bawah {sup-3}."
        else:
            signal = "⚠️ MONITORING BUY"
            instruction = f"Harga di Demand Area, tapi DXY masih kuat. Tunggu pola M5 untuk Buy."
            
    elif price >= (res - threshold):
        if dxy_stat == "Kuat":
            signal = "📉 SELL SIGNAL"
            instruction = f"Harga menyentuh Supply Area ({res}). DXY Kuat menekan Gold. Pasang SL di atas {res+3}."
        else:
            signal = "⚠️ MONITORING SELL"
            instruction = f"Harga di Supply Area, tapi DXY melemah. Tunggu pola M5 untuk Sell."

    # 3. Kirim Laporan
    wib = pytz.timezone('Asia/Jakarta')
    waktu = datetime.now(wib).strftime('%H:%M WIB')

    teks = (
        f"🦅 *ZEXLY AUTO-ZONE DETECTOR*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 *XAUUSD:* `${price}`\n"
        f"🏛️ *Resistance (Supply):* `${res}`\n"
        f"📉 *Support (Demand):* `${sup}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📢 *SIGNAL:* `{signal}`\n"
        f"💵 *DXY Stat:* `{dxy_stat}`\n\n"
        f"📝 *Instruction:* \n_{instruction}_\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕒 `{waktu}` | *Cloud System Active*"
    )

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.get(url, params={"chat_id": CHAT_ID, "text": teks, "parse_mode": "Markdown"})

if __name__ == "__main__":
    analyze_logic()
