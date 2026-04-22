"""
╔══════════════════════════════════════════════════╗
║   ZEXLY COMMAND BOT — Manual Control Center     ║
║   Upgrade: /chart, /scan, /status, /bias        ║
╚══════════════════════════════════════════════════╝

INSTALL:
    pip install python-telegram-bot yfinance pytz playwright numpy pandas python-dotenv
    playwright install chromium

JALANKAN:
    python zexly.py
"""

import os
import asyncio
import logging
import requests
import pytz
import numpy as np
import pandas as pd
import yfinance as yf

from datetime import datetime
from dotenv import load_dotenv


from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

load_dotenv()

# ─── KONFIGURASI ───────────────────────────────────────────────
TOKEN   = os.getenv("TELEGRAM_TOKEN")
USER_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
WIB     = pytz.timezone("Asia/Jakarta")

# ─── STATE GLOBAL ──────────────────────────────────────────────
zexly_config = {
    "bias":             "WAIT",
    "snr":              0.0,
    "monitoring":       False,
    "last_alert_price": 0.0,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("ZEXLY-CMD")

# ══════════════════════════════════════════════════════════════════
#  UTILITAS
# ══════════════════════════════════════════════════════════════════

def get_gold_price():
    try:
        gold = yf.Ticker("GC=F")
        df = gold.history(period="1d", interval="1m")
        if df.empty:
            return None
        return round(float(df["Close"].iloc[-1]), 2)
    except Exception as e:
        log.error(f"Gagal ambil harga: {e}")
        return None

def check_session():
    """Cek sesi trading sesuai ZEMETHOD Bab 07."""
    now = datetime.now(WIB)
    t = now.hour * 60 + now.minute
    if 14*60 <= t < 19*60:
        return "LONDON 🇬🇧 (TERBAIK)"
    if 19*60 <= t < 20*60:
        return "NY-LONDON OVERLAP ⚠️"
    if 20*60 <= t < 23*60:
        return "NEW YORK 🇺🇸 (BAIK)"
    return None

def get_waktu():
    return datetime.now(WIB).strftime("%d %b %Y | %H:%M WIB")

# ══════════════════════════════════════════════════════════════════
#  ZEMETHOD SCAN (dari zexly_vision.py)
# ══════════════════════════════════════════════════════════════════

def calc_equidistant_channel(df):
    closes = df["Close"].values
    x = np.arange(len(closes))
    slope, intercept = np.polyfit(x, closes, 1)
    residuals = closes - (slope * x + intercept)
    std = np.std(residuals)
    last_x = len(closes) - 1
    mid   = slope * last_x + intercept
    upper = mid + 1.5 * std
    lower = mid - 1.5 * std
    upper_third = upper - (upper - lower) / 3
    lower_third = lower + (upper - lower) / 3
    return {
        "mid": round(mid, 2), "upper": round(upper, 2),
        "lower": round(lower, 2), "upper_third": round(upper_third, 2),
        "lower_third": round(lower_third, 2),
    }

def get_h4_bias(ch, price):
    if price >= ch["upper_third"]: return "SELL"
    elif price <= ch["lower_third"]: return "BUY"
    return "SKIP"

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 1)

def detect_sd_base(df, bias):
    bodies = np.abs(df["Close"].values - df["Open"].values)
    n = len(df)
    if n < 15:
        return None
    for base_end in range(n - 3, n - 12, -1):
        for base_len in range(2, 6):
            base_start = base_end - base_len
            if base_start < 5:
                continue
            base_slice = df.iloc[base_start:base_end + 1]
            base_range = base_slice["High"].max() - base_slice["Low"].min()
            base_bodies = bodies[base_start:base_end + 1].mean()
            avg_body_before = bodies[max(0, base_start - 5):base_start].mean()
            if avg_body_before == 0 or base_bodies > 0.5 * avg_body_before:
                continue
            move_start = max(0, base_start - 5)
            move_slice = df.iloc[move_start:base_start]
            if len(move_slice) < 2:
                continue
            move_range = move_slice["High"].max() - move_slice["Low"].min()
            if base_range >= move_range:
                continue
            move_bodies = bodies[move_start:base_start].mean()
            if move_bodies < bodies.mean():
                continue
            move_dir = "UP" if move_slice["Close"].iloc[-1] > move_slice["Close"].iloc[0] else "DOWN"
            if bias == "BUY" and move_dir != "UP": continue
            if bias == "SELL" and move_dir != "DOWN": continue
            base_high = round(base_slice["High"].max(), 2)
            base_low  = round(base_slice["Low"].min(), 2)
            return {
                "found": True,
                "type": "RBR" if bias == "BUY" else "DBD",
                "base_high": base_high, "base_low": base_low,
                "base_mid": round((base_high + base_low) / 2, 2),
                "candles_in_base": base_len,
            }
    return None

def find_sr_levels(df):
    highs, lows = df["High"].values, df["Low"].values
    levels = []
    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
           highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            levels.append(round(highs[i], 2))
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
           lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            levels.append(round(lows[i], 2))
    if not levels: return []
    levels.sort()
    clustered = [levels[0]]
    for lv in levels[1:]:
        if lv - clustered[-1] > 5:
            clustered.append(lv)
    price = df["Close"].iloc[-1]
    clustered.sort(key=lambda x: abs(x - price))
    return clustered[:3]

def detect_m1_trigger(df_m1, bias):
    if len(df_m1) < 3:
        return {"found": False}
    c1 = df_m1.iloc[-2]
    c0 = df_m1.iloc[-3]
    o1, c1c = c1["Open"], c1["Close"]
    h1, l1  = c1["High"], c1["Low"]
    o0, c0c = c0["Open"], c0["Close"]
    body1  = abs(c1c - o1)
    range1 = h1 - l1
    body0  = abs(c0c - o0)
    if range1 == 0:
        return {"found": False}
    upper_shadow = h1 - max(o1, c1c)
    lower_shadow = min(o1, c1c) - l1
    if bias == "BUY":
        if c1c > o1 and c0c < o0 and o1 <= c0c and c1c >= o0:
            return {"found": True, "type": "Bullish Engulfing",
                    "strength": "KUAT" if body1 > body0 else "SEDANG"}
        if c1c > o1 and lower_shadow >= 2*body1 and upper_shadow <= 0.3*range1:
            return {"found": True, "type": "Bullish Pin Bar", "strength": "KUAT"}
    elif bias == "SELL":
        if c1c < o1 and c0c > o0 and o1 >= c0c and c1c <= o0:
            return {"found": True, "type": "Bearish Engulfing",
                    "strength": "KUAT" if body1 > body0 else "SEDANG"}
        if c1c < o1 and upper_shadow >= 2*body1 and lower_shadow <= 0.3*range1:
            return {"found": True, "type": "Bearish Pin Bar", "strength": "KUAT"}
    return {"found": False}

def calc_sl_tp(price, bias, sd_base, sr_levels, ch_m30):
    buffer = 7.0
    if bias == "BUY":
        sl_base = sd_base["base_low"] if sd_base and sd_base.get("found") else price - 15
        sl = round(sl_base - buffer, 2)
        risk = abs(price - sl)
        tp1_c = [lv for lv in sr_levels if lv > price]
        tp1 = round(min(tp1_c), 2) if tp1_c else round(price + risk * 2, 2)
        tp2 = round(ch_m30["upper"], 2)
    else:
        sl_base = sd_base["base_high"] if sd_base and sd_base.get("found") else price + 15
        sl = round(sl_base + buffer, 2)
        risk = abs(sl - price)
        tp1_c = [lv for lv in sr_levels if lv < price]
        tp1 = round(max(tp1_c), 2) if tp1_c else round(price - risk * 2, 2)
        tp2 = round(ch_m30["lower"], 2)
    rr1 = round(abs(tp1 - price) / risk, 2) if risk > 0 else 0
    rr2 = round(abs(tp2 - price) / risk, 2) if risk > 0 else 0
    return {"sl": sl, "tp1": tp1, "tp2": tp2,
            "risk_pips": round(risk, 1), "rr1": rr1, "rr2": rr2}

async def run_zemethod_scan():
    """Jalanin full ZEMETHOD scan, return dict hasil."""
    try:
        
        df_h4  = gold.history(period="2mo", interval="1h")
        df_m30 = gold.history(period="10d", interval="30m")
        df_m5  = gold.history(period="3d",  interval="5m")
        df_m1  = gold.history(period="1d",  interval="1m")
        for df in [df_h4, df_m30, df_m5, df_m1]:
            df.dropna(inplace=True)
    except Exception as e:
        return {"error": str(e)}

    price   = round(float(df_m1["Close"].iloc[-1]), 2)
    ch_h4   = calc_equidistant_channel(df_h4)
    ch_m30  = calc_equidistant_channel(df_m30)
    bias    = get_h4_bias(ch_h4, price)
    rsi     = calc_rsi(df_m30["Close"])
    sd_base = detect_sd_base(df_m30, bias) if bias != "SKIP" else None
    sr_lvls = find_sr_levels(df_m30)
    trigger = detect_m1_trigger(df_m1, bias) if bias != "SKIP" else {"found": False}

    stars = 0
    reasons = []
    if bias != "SKIP":
        stars += 1
        reasons.append(f"★ Bias H4: {bias}")
        if sd_base and sd_base.get("found"):
            stars += 1
            reasons.append(f"★ Pola {sd_base['type']} ({sd_base['candles_in_base']} candle)")
            if (bias == "BUY" and price <= sd_base["base_high"]) or \
               (bias == "SELL" and price >= sd_base["base_low"]):
                stars += 1
                reasons.append("★ Harga masuk zona base (konfirmasi M5)")
        if trigger.get("found"):
            stars += 1
            reasons.append(f"★ Trigger M1: {trigger['type']} ({trigger['strength']})")

    sl_tp = calc_sl_tp(price, bias, sd_base, sr_lvls, ch_m30) if bias != "SKIP" else None

    return {
        "price": price, "bias": bias, "stars": stars, "reasons": reasons,
        "ch_h4": ch_h4, "ch_m30": ch_m30, "sd_base": sd_base,
        "trigger": trigger, "rsi": rsi, "sl_tp": sl_tp,
        "sr_levels": sr_lvls, "session": check_session(),
    }

# ══════════════════════════════════════════════════════════════════
#  SCREENSHOT TRADINGVIEW
# ══════════════════════════════════════════════════════════════════

INTERVAL_MAP = {
    "M1": "1", "M5": "5", "M15": "15",
    "M30": "30", "H1": "60", "H4": "240"
}

async def take_tv_screenshot(tf: str = "M5"):
    interval = INTERVAL_MAP.get(tf.upper(), "5")
    url = (
        f"https://s.tradingview.com/widgetembed/"
        f"?symbol=OANDA:XAUUSD&interval={interval}"
        f"&theme=dark&style=1&locale=id"
        f"&toolbar_bg=%23131722"
    )
    path = f"zexly_chart_{tf}.png"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await ctx.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(6)
            await page.screenshot(path=path)
            await browser.close()
        return path
    except Exception as e:
        log.error(f"Screenshot error: {e}")
        return None

# ══════════════════════════════════════════════════════════════════
#  BACKGROUND MONITORING
# ══════════════════════════════════════════════════════════════════

async def monitor_market(context: ContextTypes.DEFAULT_TYPE):
    if not zexly_config["monitoring"] or zexly_config["bias"] == "WAIT":
        return
    price   = get_gold_price()
    session = check_session()
    if not price or not session:
        return
    bias = zexly_config["bias"]
    snr  = zexly_config["snr"]
    is_in_zone = (
        (bias == "BUY"  and price <= snr + 1.5) or
        (bias == "SELL" and price >= snr - 1.5)
    )
    if is_in_zone and abs(price - zexly_config["last_alert_price"]) > 2.0:
        zexly_config["last_alert_price"] = price
        msg = (
            f"⭐ *ZEXLY ALERT — HARGA MASUK ZONA*\n"
            f"━━━━━━━━━━━━━━\n"
            f"🕒 Sesi: {session}\n"
            f"💰 Harga: `${price}`\n"
            f"📈 Bias: `{bias}`\n"
            f"🎯 SNR: `{snr}`\n"
            f"━━━━━━━━━━━━━━\n"
            f"🔥 Cek M5/M1 untuk konfirmasi entry!"
        )
        await context.bot.send_message(
            chat_id=USER_ID, text=msg, parse_mode="Markdown"
        )

# ══════════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ══════════════════════════════════════════════════════════════════

def is_authorized(update: Update):
    return update.effective_user.id == USER_ID

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    keyboard = [
        [InlineKeyboardButton("📈 Set Bias H4", callback_data="menu_bias")],
        [InlineKeyboardButton("🎯 Set SNR M30", callback_data="menu_snr")],
        [InlineKeyboardButton("🚀 Start Monitor", callback_data="mon_on"),
         InlineKeyboardButton("🛑 Stop Monitor", callback_data="mon_off")],
        [InlineKeyboardButton("📊 Status", callback_data="status"),
         InlineKeyboardButton("💰 Harga", callback_data="price")],
        [InlineKeyboardButton("🔍 Scan ZEMETHOD", callback_data="scan"),
         InlineKeyboardButton("📸 Chart", callback_data="chart_menu")],
    ]
    await update.message.reply_text(
        f"🦅 *ZEXLY COMMAND CENTER*\n`{get_waktu()}`",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def cmd_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /chart [TF] — contoh: /chart M5 atau /chart H4"""
    if not is_authorized(update): return
    args = context.args
    tf = args[0].upper() if args else "M5"
    if tf not in INTERVAL_MAP:
        await update.message.reply_text(
            f"❌ TF tidak valid. Pilihan: {', '.join(INTERVAL_MAP.keys())}"
        )
        return
    msg = await update.message.reply_text(f"📸 Mengambil chart {tf}... tunggu sebentar")
    screenshot = await take_tv_screenshot(tf)
    if screenshot and os.path.exists(screenshot):
        with open(screenshot, "rb") as ph:
            await update.message.reply_photo(
                photo=ph,
                caption=(
                    f"📊 *XAUUSD — {tf}*\n"
                    f"💰 Price: `${get_gold_price()}`\n"
                    f"🕒 `{get_waktu()}`"
                ),
                parse_mode="Markdown"
            )
        await msg.delete()
    else:
        await msg.edit_text("❌ Gagal ambil screenshot. Coba lagi.")

async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /scan — jalanin ZEMETHOD scan manual."""
    if not is_authorized(update): return
    msg = await update.message.reply_text("🔍 Scanning ZEMETHOD... tunggu sebentar")
    result = await run_zemethod_scan()
    if "error" in result:
        await msg.edit_text(f"❌ Error scan: {result['error']}")
        return
    await msg.delete()
    await _send_scan_result(update, result)

async def _send_scan_result(update, result):
    price   = result["price"]
    bias    = result["bias"]
    stars   = result["stars"]
    ch_h4   = result["ch_h4"]
    ch_m30  = result["ch_m30"]
    sd_base = result["sd_base"]
    trigger = result["trigger"]
    rsi     = result["rsi"]
    sl_tp   = result["sl_tp"]
    session = result["session"] or "😴 Off-Session"
    reasons = result["reasons"]

    stars_display = "★" * stars + "☆" * (4 - stars)
    emoji_bias = {"BUY": "🟢 BUY", "SELL": "🔴 SELL", "SKIP": "⏸ SKIP"}.get(bias, bias)

    base_txt = (
        f"`{sd_base['type']} — {sd_base['candles_in_base']} candle`\n"
        f"   Zone: `{sd_base['base_low']} – {sd_base['base_high']}`"
    ) if sd_base and sd_base.get("found") else "`Tidak terdeteksi`"

    trigger_txt = f"`{trigger['type']} ({trigger['strength']})`" \
                  if trigger.get("found") else "`Belum muncul`"

    rsi_label = (
        "⚠️ Overbought" if rsi >= 70 else
        "🔶 Near OB"    if rsi >= 65 else
        "⚠️ Oversold"   if rsi <= 30 else
        "🔷 Near OS"    if rsi <= 35 else "➖ Netral"
    )

    trade_txt = ""
    if sl_tp and bias != "SKIP":
        trade_txt = (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💼 *RENCANA TRADE*\n\n"
            f"   Entry : `${price}`\n"
            f"   SL    : `${sl_tp['sl']}` ({sl_tp['risk_pips']} pips)\n"
            f"   TP1   : `${sl_tp['tp1']}` (RR `{sl_tp['rr1']}:1`) → tutup 70%\n"
            f"   TP2   : `${sl_tp['tp2']}` (RR `{sl_tp['rr2']}:1`) → sisa 30%\n\n"
            f"   TP1 hit → geser SL ke breakeven!\n"
        )

    reasons_txt = "\n".join([f"  {r}" for r in reasons]) if reasons else "  (tidak ada)"

    caption = (
        f"🦅 *ZEXLY METHOD — SCAN MANUAL*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Price:* `${price}`\n"
        f"⚡ *Signal:* {emoji_bias}\n"
        f"⭐ *Kualitas:* `{stars_display}` ({stars}/4 bintang)\n"
        f"📡 *Sesi:* {session}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏗️ *H4 Channel*\n"
        f"   Upper: `{ch_h4['upper']}` | Mid: `{ch_h4['mid']}` | Lower: `{ch_h4['lower']}`\n\n"
        f"📐 *M30 Channel*\n"
        f"   Upper: `{ch_m30['upper']}` | Lower: `{ch_m30['lower']}`\n\n"
        f"🎯 *S&D Base:* {base_txt}\n\n"
        f"🕯️ *Trigger M1:* {trigger_txt}\n\n"
        f"📈 *RSI M30:* `{rsi}` — {rsi_label}\n"
        f"{trade_txt}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ *Alasan:*\n{reasons_txt}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕒 `{get_waktu()}`"
    )

    # Kirim chart M5 sekalian
    screenshot = await take_tv_screenshot("M5")
    if screenshot and os.path.exists(screenshot):
        with open(screenshot, "rb") as ph:
            await update.message.reply_photo(
                photo=ph, caption=caption, parse_mode="Markdown"
            )
    else:
        await update.message.reply_text(caption, parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════
#  CALLBACK HANDLER (tombol inline)
# ══════════════════════════════════════════════════════════════════

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_bias":
        kbd = [[
            InlineKeyboardButton("🟢 BUY",  callback_data="set_BUY"),
            InlineKeyboardButton("🔴 SELL", callback_data="set_SELL"),
            InlineKeyboardButton("⏸ WAIT", callback_data="set_WAIT"),
        ]]
        await query.edit_message_text(
            "📈 Pilih Bias H4:", reply_markup=InlineKeyboardMarkup(kbd)
        )

    elif data.startswith("set_"):
        zexly_config["bias"] = data.split("_")[1]
        await query.edit_message_text(
            f"✅ Bias diatur ke: *{zexly_config['bias']}*", parse_mode="Markdown"
        )

    elif data == "menu_snr":
        await query.edit_message_text("⌨️ Kirim angka SNR (contoh: `3250.5`)", parse_mode="Markdown")
        context.user_data["input_snr"] = True

    elif data == "mon_on":
        zexly_config["monitoring"] = True
        await query.edit_message_text("🚀 *Monitoring Aktif!*\nBot akan alert jika harga masuk zona SNR.", parse_mode="Markdown")

    elif data == "mon_off":
        zexly_config["monitoring"] = False
        await query.edit_message_text("🛑 *Monitoring Dimatikan.*", parse_mode="Markdown")

    elif data == "price":
        price = get_gold_price()
        session = check_session() or "😴 Off-Session"
        await query.edit_message_text(
            f"💰 *XAUUSD:* `${price}`\n📡 Sesi: {session}\n🕒 `{get_waktu()}`",
            parse_mode="Markdown"
        )

    elif data == "status":
        stat = "AKTIF 🟢" if zexly_config["monitoring"] else "MATI 🔴"
        price = get_gold_price()
        await query.edit_message_text(
            f"📝 *STATUS ZEXLY*\n\n"
            f"• Monitor: {stat}\n"
            f"• Bias H4: `{zexly_config['bias']}`\n"
            f"• SNR M30: `{zexly_config['snr']}`\n"
            f"• Harga: `${price}`\n"
            f"• Sesi: {check_session() or '😴 Off-Session'}\n"
            f"• Waktu: `{get_waktu()}`",
            parse_mode="Markdown"
        )

    elif data == "scan":
        await query.edit_message_text("🔍 Scanning ZEMETHOD... tunggu sebentar")
        result = await run_zemethod_scan()
        if "error" in result:
            await query.edit_message_text(f"❌ Error: {result['error']}")
            return
        # Hapus pesan lama, kirim hasil scan baru
        await query.delete_message()
        # Bikin fake update object untuk reuse _send_scan_result
        class FakeUpdate:
            class message:
                @staticmethod
                async def reply_text(text, **kwargs):
                    await context.bot.send_message(chat_id=USER_ID, text=text, **kwargs)
                @staticmethod
                async def reply_photo(photo, **kwargs):
                    await context.bot.send_photo(chat_id=USER_ID, photo=photo, **kwargs)
        await _send_scan_result(FakeUpdate(), result)

    elif data == "chart_menu":
        kbd = [[
            InlineKeyboardButton("M1",  callback_data="chart_M1"),
            InlineKeyboardButton("M5",  callback_data="chart_M5"),
            InlineKeyboardButton("M15", callback_data="chart_M15"),
        ], [
            InlineKeyboardButton("M30", callback_data="chart_M30"),
            InlineKeyboardButton("H1",  callback_data="chart_H1"),
            InlineKeyboardButton("H4",  callback_data="chart_H4"),
        ]]
        await query.edit_message_text(
            "📸 Pilih timeframe chart:", reply_markup=InlineKeyboardMarkup(kbd)
        )

    elif data.startswith("chart_"):
        tf = data.split("_")[1]
        await query.edit_message_text(f"📸 Mengambil chart {tf}... tunggu sebentar")
        screenshot = await take_tv_screenshot(tf)
        await query.delete_message()
        if screenshot and os.path.exists(screenshot):
            with open(screenshot, "rb") as ph:
                await context.bot.send_photo(
                    chat_id=USER_ID,
                    photo=ph,
                    caption=(
                        f"📊 *XAUUSD — {tf}*\n"
                        f"💰 Price: `${get_gold_price()}`\n"
                        f"🕒 `{get_waktu()}`"
                    ),
                    parse_mode="Markdown"
                )
        else:
            await context.bot.send_message(
                chat_id=USER_ID, text="❌ Gagal ambil screenshot."
            )

# ══════════════════════════════════════════════════════════════════
#  TEXT HANDLER (input SNR)
# ══════════════════════════════════════════════════════════════════

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    if context.user_data.get("input_snr"):
        try:
            val = float(update.message.text)
            zexly_config["snr"] = val
            context.user_data["input_snr"] = False
            await update.message.reply_text(
                f"🎯 SNR diset ke: *${val}*\nMonitoring akan alert jika harga mendekati level ini.",
                parse_mode="Markdown"
            )
        except ValueError:
            await update.message.reply_text("❌ Format salah. Kirim angka saja, contoh: `3250.5`", parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()

    # Background monitoring tiap 60 detik
    app.job_queue.run_repeating(monitor_market, interval=60, first=10)

    # Command handlers
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("chart",  cmd_chart))
    app.add_handler(CommandHandler("scan",   cmd_scan))

    # Callback & text
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    log.info("🦅 ZEXLY Command Bot running...")
    app.run_polling()

# Override take_tv_screenshot tanpa playwright
async def take_tv_screenshot(tf: str = "M5"):
    interval = INTERVAL_MAP.get(tf.upper(), "5")
    url = (
        f"https://api.chart-img.com/v1/tradingview/advanced-chart"
        f"?symbol=OANDA:XAUUSD&interval={interval}&theme=dark"
        f"&width=1280&height=720"
    )
    path = f"zexly_chart_{tf}.png"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            with open(path, "wb") as f:
                f.write(resp.content)
            return path
    except Exception as e:
        log.error(f"Chart error: {e}")
    return None
