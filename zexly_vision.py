import requests
import yfinance as yf
from datetime import datetime
import pytz
import asyncio
from playwright.async_api import async_playwright
import numpy as np

TOKEN = "8706271896:AAH6ZL3GJ-CarezdO-TapTJnnyZy6QZ4w2Y"
CHAT_ID = "5801538218"

def get_channel_coords(df):
    y = df['Close'].values
    x = np.arange(len(y))
    slope, intercept = np.polyfit(x, y, 1)
    std = np.std(y - (slope * x + intercept))
    return slope, intercept, std, len(y)

async def zexly_pro_scanner():
    gold = yf.Ticker("GC=F")
    # Ambil data untuk berbagai timeframe
    df_h4 = gold.history(period="1mo", interval="4h")
    df_m15 = gold.history(period="5d", interval="15m")
    
    price = round(df_m15['Close'].iloc[-1], 2)
    slope, intercept, std, length = get_channel_coords(df_h4)
    
    # Kalkulasi Parallel Channel Utama & Duplikat (Atas/Bawah)
    current_mid = slope * (length - 1) + intercept
    upper_1 = current_mid + (2 * std)
    lower_1 = current_mid - (2 * std)
    upper_2 = upper_1 + (2 * std) # Duplikat Atas
    lower_2 = lower_1 - (2 * std) # Duplikat Bawah

    # Logika Sinyal: Cek jika harga masuk ke area "Duplikat" (Pucuk)
    is_pucuk_sell = price >= upper_1
    is_pucuk_buy = price <= lower_1
    
    # Kita set True untuk testing visual pertama
    if is_pucuk_sell or is_pucuk_buy:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            # Buka M5/M15 untuk visualisasi scalping
            url = "https://s.tradingview.com/widgetembed/?symbol=FX_IDC:XAUUSD&interval=15&theme=dark"
            await page.goto(url, wait_until="networkidle")
            await asyncio.sleep(5)

            # Gambar Parallel Channel Bertingkat di Browser
            await page.evaluate(f"""
                const drawCanvasLine = (top, color, label, dashed) => {{
                    const div = document.createElement('div');
                    div.style.cssText = `position:absolute; top:${{top}}%; width:100%; border-top:2px ${{dashed ? 'dashed' : 'solid'}} ${{color}}; z-index:1000;`;
                    div.innerHTML = `<span style="background:${{color}}; color:white; font-size:9px;">${{label}}</span>`;
                    document.body.appendChild(div);
                }};
                drawCanvasLine(20, 'purple', 'DUPLICATE UPPER (EXTREME SELL)', true);
                drawCanvasLine(35, 'red', 'MAIN UPPER CHANNEL', false);
                drawCanvasLine(65, 'green', 'MAIN LOWER CHANNEL', false);
                drawCanvasLine(80, 'blue', 'DUPLICATE LOWER (EXTREME BUY)', true);
            """)
            
            await page.screenshot(path="zexly_final.png")
            await browser.close()

        wib = pytz.timezone('Asia/Jakarta')
        waktu = datetime.now(wib).strftime('%H:%M WIB')
        
        caption = (
            f"🦅 *ZEXLY MULTI-PARALLEL SCANNER*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📈 *TF:* `M15 Scalp` | *Bias:* `H4 Parallel` \n"
            f"💰 *Price:* `${price}`\n"
            f"⚠️ *Zone:* `{'AREA PUCUK ATAS' if is_pucuk_sell else 'AREA PUCUK BAWAH' if is_pucuk_buy else 'Normal Zone'}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ *Strategy:* Gunakan M5/M1 untuk konfirmasi MSB/Rejection!\n"
            f"🕒 `{waktu}`"
        )
        
        with open("zexly_final.png", "rb") as photo:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendPhoto", 
                          data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "Markdown"}, 
                          files={"photo": photo})

if __name__ == "__main__":
    asyncio.run(zexly_pro_scanner())
