import requests
import yfinance as yf
from datetime import datetime
import pytz

# KONFIGURASI BOT
TOKEN = "8706271896:AAH6ZL3GJ-CarezdO-TapTJnnyZy6QZ4w2Y"
CHAT_ID = "5801538218"

def analyze_zexly_pro():
    try:
        gold = yf.Ticker("GC=F")
        
        # 1. ANALISA H4: BIAS UTAMA (BAB 01 & 04)
        h4_df = gold.history(period="20d", interval="4h")
        high_h4 = h4_df['High'].max()
        low_h4 = h4_df['Low'].min()
        price = round(h4_df['Close'].iloc[-1], 2)
        
        # Pembagian 3 Zona (Rule Mutlak H4)
        zone_size = (high_h4 - low_h4) / 3
        upper_zone = high_h4 - zone_size
        lower_zone = low_h4 + zone_size
        
        if price >= upper_zone:
            bias = "SELL ONLY"
            status_h4 = "🔴 UPPER ZONE (Mencari Supply)"
        elif price <= lower_zone:
            bias = "BUY ONLY"
            status_h4 = "🔵 LOWER ZONE (Mencari Demand)"
        else:
            send_telegram("⚠️ *ZEXLY MIDDLE ZONE*\nAturan Ebook: Harga di tengah range H4. Skip trading & tutup platform.")
            return

        # 2. ANALISA M30: EQUIDISTANT CHANNEL & BASE (BAB 02)
        m30_df = gold.history(period="5d", interval="30m")
        res_m30 = round(m30_df['High'].tail(20).max(), 2)
        sup_m30 = round(m30_df['Low'].tail(20).min(), 2)
        
        # Deteksi S&R Flip Sederhana (M30)
        prev_res = m30_df['High'].iloc[-40:-20].max()
        is_flip = "YA" if abs(price - prev_res) < 1.0 else "TIDAK"

        # 3. KORELASI DXY (FILTER TAMBAHAN)
        dxy = yf.download("DX-Y.NYB", period="1d", progress=False)['Close'].iloc[-1]

        # 4. SISTEM BINTANG (FILTER KUALITAS - BAB 05)
        stars = 0
        checklist = []
        
        # Bintang 1: Searah Bias H4
        stars += 1
        checklist.append("✅ Bias H4 Terkonfirmasi")
        
        # Bintang 2: Base di level S&R M30
        dist_to_snr = min(abs(price - res_m30), abs(price - sup_m30))
        if dist_to_snr <= 2.5:
            stars += 1
            checklist.append("✅ Berada di Area S&R M30")
        else:
            checklist.append("❌ Jauh dari S&R M30")

        # Bintang 3: Konfirmasi DXY (Korelasi Negatif Gold)
        # Jika DXY turun dan kita mau Buy, atau DXY naik dan kita mau Sell
        dxy_prev = yf.download("DX-Y.NYB", period="1d", progress=False)['Open'].iloc[-1]
        if (bias == "BUY ONLY" and dxy < dxy_prev) or (bias == "SELL ONLY" and dxy > dxy_prev):
            stars += 1
            checklist.append("✅ Konfirmasi DXY Mendukung")
        else:
            checklist.append("❌ DXY Melawan Arah")

        # Keputusan Akhir
        decision = "🔥 ENTRY" if stars >= 3 else "⌛ WAIT / SKIP"

        # 5. PENYUSUNAN LAPORAN TERPERINCI
        wib = pytz.timezone('Asia/Jakarta')
        waktu = datetime.now(wib).strftime('%H:%M WIB')

        msg = (
            f"🦅 *ZEXLY METHOD PRO V6.0*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📍 *H4 Position:* `{status_h4}`\n"
            f"🎯 *Main Bias:* `{bias}`\n"
            f"💰 *Price:* `${price}` | *DXY:* `{dxy:.2f}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📏 *LEVEL MONITORING (M30):*\n"
            f"Supply: `${res_m30}`\n"
            f"Demand: `${sup_m30}`\n"
            f"S&R Flip: `{is_flip}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⭐ *SISTEM BINTANG ({stars}/4):*\n"
            + "\n".join(checklist) + "\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📢 *RESULT:* `{decision}`\n"
            f"📝 *Trigger M1:* Tunggu Engulfing/Pinbar\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🕒 `{waktu}` | *ZEXLY COMPLIANCE*"
        )
        send_telegram(msg)
        
    except Exception as e:
        print(f"Error detail: {e}")

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.get(url, params={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})

if __name__ == "__main__":
    analyze_zexly_pro()
