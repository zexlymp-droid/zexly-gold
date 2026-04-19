import requests
import time
from datetime import datetime

# --- KONFIGURASI ---
TOKEN = "8706271896:AAH6ZL3GJ-CarezdO-TapTJnnyZy6QZ4w2Y"
CHAT_ID = "5801538218"

# --- ATURAN ZEXLY (Input Manual Setiap Pagi) ---
BIAS_H4 = "BUY" # Isi 'BUY' jika di Lower Zone, 'SELL' jika di Upper Zone
ZONE_ENTRY = 2320.0 # Contoh level S&R M30/M15 yang kamu tandai

def get_gold_price():
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDT"
        return float(requests.get(url).json()['price'])
    except:
        return None

def is_zexly_session():
    # Jam Trading: London (14-18 WIB) & NY (20-23 WIB)
    now = datetime.now().hour
    return (14 <= now <= 18) or (20 <= now <= 23)

def send_alert(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text={msg}"
    requests.get(url)

print("--- ZEXLY MONITORING ACTIVE ---")

while True:
    if is_zexly_session():
        price = get_gold_price()
        if price:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] XAUUSD: ${price}")
            
            # Logika Bintang 1 & 2: Searah Bias & Masuk Zona S&R
            if BIAS_H4 == "BUY" and price <= ZONE_ENTRY:
                send_alert(f"⭐ ZEXLY ALERT: Harga masuk zona BUY (${price}). Cek konfirmasi M5/M1!")
                time.sleep(1800) # Berhenti 30 menit setelah alert
            elif BIAS_H4 == "SELL" and price >= ZONE_ENTRY:
                send_alert(f"⭐ ZEXLY ALERT: Harga masuk zona SELL (${price}). Cek konfirmasi M5/M1!")
                time.sleep(1800)
    else:
        print("Sesi Luar London/NY. Filter Noise aktif.")
        
    time.sleep(60)

