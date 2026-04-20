import requests
import yfinance as yf
from datetime import datetime
import pytz
import asyncio
from playwright.async_api import async_playwright

# CONFIG
TOKEN = "8706271896:AAH6ZL3GJ-CarezdO-TapTJnnyZy6QZ4w2Y"
CHAT_ID = "5801538218"

async def generate_zexly_analysis():
    # 1. Ambil Data Teknis
    gold = yf.Ticker("GC=F")
    df = gold.history(period="5d", interval="15m")
    current_price = round(df['Close'].iloc[-1], 2)
    
    # Hitung SnR Sederhana (High/Low Terdekat)
    res_level = round(df['High'].tail(20).max(), 2)
    sup_level = round(df['Low'].tail(20).min(), 2)
    
    # 2. Logic Multi-Timeframe & Bintang (Ebook Bab 05)
    # Cek Kondisi Momentum untuk Sinyal (Bukan Timer)
    momentum_detected = False
    stars = 1 # Start with 1 star for monitoring
    
    if current_price >= res_level - 1: # Dekat Resistance
        stars += 1
        action = "SELL"
    elif current_price <= sup_level + 1: # Dekat Support
        stars += 1
        action = "BUY"
    else:
        action = "MONITORING"

    # Hanya kirim jika 3 Bintang atau lebih (Ada rejection/close konfirmasi)
    # Untuk simulasi, kita set True agar kamu bisa lihat hasilnya dulu
    momentum_detected = True 

    if momentum_detected:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            # Buka Chart M5 untuk Scalping
            url = f"https://s.tradingview.com/widgetembed/?symbol=FX_IDC:XAUUSD&interval=5&theme=dark"
            await page.goto(url, wait_until="networkidle")
            await asyncio.sleep(5)
            
            # INJEKSI JAVASCRIPT: Menggambar Garis SnR di Chart
            await page.evaluate(f"""
                const style = document.createElement('style');
                style.innerHTML = `
                    .zexly-line {{
                        position: absolute; left: 0; width: 100%; height: 2px;
                        background: rgba(255, 0, 0, 0.5); z-index: 999;
                        border-top: 1px dashed white;
                    }}
                    .zexly-label {{
                        position: absolute; right: 10px; color: white; 
                        font-size: 12px; background: black; padding: 2px 5px;
                    }}
                `;
                document.head.appendChild(style);
                
                // Gambar Resistance Line (Simulasi Visual)
                const resLine = document.createElement('div');
                resLine.className = 'zexly-line';
                resLine.style.top = '30%'; // Menyesuaikan posisi visual
                resLine.innerHTML = '<span class="zexly-label">ZEXLY RESISTANCE: {res_level}</span>';
                document.body.appendChild(resLine);
            """)
            
            await page.screenshot(path="zexly_analysis.png")
            await browser.close()

        # Susun Pesan sesuai Strategi Bintang
        wib = pytz.timezone('Asia/Jakarta')
        waktu = datetime.now(wib).strftime('%H:%M WIB')
        
        caption = (
            f"🦅 *ZEXLY SCALPER SIGNAL (M5/M1)*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ *Momentum:* `{action} AREA`\n"
            f"💰 *Current:* `${current_price}`\n"
            f"🎯 *Target Zone:* `{res_level if action == 'SELL' else sup_level}`\n"
            f"⭐ *Quality:* `{stars}/4 Stars`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📝 *Note:* Tunggu rejection candle M1 untuk eksekusi!\n"
            f"🕒 `{waktu}`"
        )
        
        # Kirim ke Telegram
        files = {'photo': open("zexly_analysis.png", "rb")}
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendPhoto", 
                      data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "Markdown"}, 
                      files=files)

if __name__ == "__main__":
    asyncio.run(generate_zexly_analysis())
