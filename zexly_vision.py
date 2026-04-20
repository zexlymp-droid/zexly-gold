import requests
import yfinance as yf
from datetime import datetime
import pytz
import asyncio
from playwright.async_api import async_playwright

# KONFIGURASI
TOKEN = "8706271896:AAH6ZL3GJ-CarezdO-TapTJnnyZy6QZ4w2Y"
CHAT_ID = "5801538218"

async def take_screenshot():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        # Menggunakan widget TradingView yang lebih stabil untuk screenshot
        url = "https://s.tradingview.com/widgetembed/?symbol=FX_IDC:XAUUSD&interval=240&theme=dark"
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(5)
        await page.screenshot(path="chart.png")
        await browser.close()

def get_data_and_send():
    gold = yf.Ticker("GC=F")
    df = gold.history(period="10d", interval="1h")
    price = round(df['Close'].iloc[-1], 2)
    
    # Aturan ZEXLY: Pembagian Sepertiga Channel (Halaman 5 Ebook)
    high_h4 = df['High'].max()
    low_h4 = df['Low'].min()
    range_total = high_h4 - low_h4
    one_third = range_total / 3
    
    upper_zone_start = high_h4 - one_third
    lower_zone_end = low_h4 + one_third
    
    if price >= upper_zone_start:
        status = "🔴 UPPER ZONE"
        note = "SELL ONLY. Harga di area resistance bias turun."
    elif price <= lower_zone_end:
        status = "🔵 LOWER ZONE"
        note = "BUY ONLY. Harga di area support bias naik."
    else:
        status = "🟡 MIDDLE ZONE"
        note = "TIDAK TRADING. Area noise, tidak ada edge yang jelas."

    wib = pytz.timezone('Asia/Jakarta')
    waktu = datetime.now(wib).strftime('%H:%M WIB')
    
    caption = (
        f"🦅 *ZEXLY VISION MONITOR*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Gold Price:* `${price}`\n"
        f"📍 *H4 Status:* `{status}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📝 *Zexly Note:* \n_{note}_\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕒 `{waktu}` | *Native Browser Analysis*"
    )
    
    # Kirim ke Telegram
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    with open("chart.png", "rb") as photo:
        requests.post(url, data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "Markdown"}, files={"photo": photo})

if __name__ == "__main__":
    try:
        asyncio.run(take_screenshot())
        get_data_and_send()
    except Exception as e:
        print(f"Error detected: {e}")
