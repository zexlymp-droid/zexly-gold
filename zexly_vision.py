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
        # Buka Chart TradingView XAUUSD
        await page.goto("https://www.tradingview.com/chart/?symbol=FX_IDC:XAUUSD", wait_until="networkidle")
        # Tunggu 10 detik agar chart benar-benar loading
        await asyncio.sleep(10)
        await page.screenshot(path="chart.png")
        await browser.close()

def get_data_and_send():
    gold = yf.Ticker("GC=F")
    df = gold.history(period="5d", interval="1h")
    price = round(df['Close'].iloc[-1], 2)
    
    # [span_0](start_span)Hitung Zona Zexly[span_0](end_span)
    high_h4 = df['High'].max()
    low_h4 = df['Low'].min()
    range_total = high_h4 - low_h4
    one_third = range_total / 3
    
    if price >= (high_h4 - one_third):
        [span_1](start_span)[span_2](start_span)status, note = "🔴 UPPER ZONE", "SELL ONLY. Cari base valid di M30/M15[span_1](end_span)[span_2](end_span)."
    elif price <= (low_h4 + one_third):
        status, note = "🔵 LOWER ZONE", "BUY ONLY. [span_3](start_span)[span_4](start_span)Cari base valid di M30/M15[span_3](end_span)[span_4](end_span)."
    else:
        status, note = "🟡 MIDDLE ZONE", "TIDAK TRADING. [span_5](start_span)[span_6](start_span)Area noise, tidak ada edge yang jelas[span_5](end_span)[span_6](end_span)."

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
    asyncio.run(take_screenshot())
    get_data_and_send()
