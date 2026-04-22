"""
╔══════════════════════════════════════════════════╗
║   ZEXLY METHOD BOT — XAUUSD AUTO SCANNER        ║
║   Equidistant Channel + S&D + Price Action       ║
║   Sesuai ZEMETHOD Ebook (H4 → M30 → M5 → M1)   ║
║   + Command Handler: /chart /scan /status /force ║
║   + TradingView Chart via chart-img.com          ║
╚══════════════════════════════════════════════════╝
"""

import os, logging, json
from datetime import datetime
import pytz
import numpy as np
import pandas as pd
import yfinance as yf
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN       = os.getenv("TELEGRAM_TOKEN")
CHAT_ID     = os.getenv("TELEGRAM_CHAT_ID", "-1003986432270")
CHARTIMG_KEY = os.getenv("CHARTIMG_KEY", "")
WIB         = pytz.timezone("Asia/Jakarta")

STATE_FILE  = "zexly_state.json"
OFFSET_FILE = "tg_offset.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("ZEXLY")
key_loaded = bool(os.getenv("CHARTIMG_KEY"))
log.info(f"CHARTIMG_KEY loaded: {key_loaded}")

# ══════════════════════════════════════════════════════════════════
#  STATE & ANTI-SPAM
# ══════════════════════════════════════════════════════════════════

def load_state():
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except Exception: return {}

def save_state(state):
    with open(STATE_FILE, "w") as f: json.dump(state, f)

def already_alerted(signal_key):
    state = load_state()
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    return state.get("date") == today and state.get("key") == signal_key

def mark_alerted(signal_key):
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    save_state({"date": today, "key": signal_key})

def load_offset():
    try:
        with open(OFFSET_FILE) as f: return json.load(f).get("offset", 0)
    except Exception: return 0

def save_offset(offset):
    with open(OFFSET_FILE, "w") as f: json.dump({"offset": offset}, f)

# ══════════════════════════════════════════════════════════════════
#  JAM TRADING (ZEMETHOD Bab 07)
# ══════════════════════════════════════════════════════════════════

def get_session_status():
    now = datetime.now(WIB)
    t = now.hour * 60 + now.minute
    if 14*60 <= t < 19*60:   return True,  "London Open (TERBAIK)"
    elif 20*60 <= t < 23*60: return True,  "New York Session (BAIK)"
    elif 19*60 <= t < 20*60: return True,  "NY-London Overlap (HATI-HATI)"
    else:                     return False, "Asian / Off-Session"

def get_waktu():
    return datetime.now(WIB).strftime("%d %b %Y | %H:%M WIB")

# ══════════════════════════════════════════════════════════════════
#  DATA FETCH
# ══════════════════════════════════════════════════════════════════

def fetch_data():
    try:
        gold = yf.Ticker("GC=F")
        df_h4  = gold.history(period="2mo",  interval="1h")
        df_m30 = gold.history(period="10d",  interval="30m")
        df_m5  = gold.history(period="3d",   interval="5m")
        df_m1  = gold.history(period="1d",   interval="1m")
        for label, df in [("H4",df_h4),("M30",df_m30),("M5",df_m5),("M1",df_m1)]:
            if df is None or df.empty:
                log.warning(f"Data {label} kosong")
                return None
            df.dropna(inplace=True)
        return {"h4": df_h4, "m30": df_m30, "m5": df_m5, "m1": df_m1}
    except Exception as e:
        log.error(f"Gagal fetch data: {e}")
        return None

# ══════════════════════════════════════════════════════════════════
#  EQUIDISTANT CHANNEL
# ══════════════════════════════════════════════════════════════════

def find_swings(arr, order=5):
    """Cari swing high dan swing low — minimal order candle di kiri & kanan."""
    highs, lows = [], []
    for i in range(order, len(arr) - order):
        if all(arr[i] >= arr[i-j] for j in range(1, order+1)) and            all(arr[i] >= arr[i+j] for j in range(1, order+1)):
            highs.append((i, float(arr[i])))
        if all(arr[i] <= arr[i-j] for j in range(1, order+1)) and            all(arr[i] <= arr[i+j] for j in range(1, order+1)):
            lows.append((i, float(arr[i])))
    return highs, lows

def calc_equidistant_channel(df):
    """
    Parallel Channel — 2 swing high + 1 swing low (descending)
    atau 2 swing low + 1 swing high (ascending).
    Lower/upper line dibuat paralel satu sama lain.
    Mirip cara gambar channel manual di TradingView.
    """
    highs_arr = df["High"].values
    lows_arr  = df["Low"].values
    closes    = df["Close"].values
    n = len(closes)
    last_x = n - 1

    swing_highs, swing_lows = find_swings(highs_arr, order=5)
    _, swing_lows2 = find_swings(lows_arr, order=5)

    def line_at(x, x1, y1, slope):
        return y1 + slope * (x - x1)

    # Coba descending channel: 2 swing high + 1 swing low
    if len(swing_highs) >= 2 and len(swing_lows2) >= 1:
        sh1, sh2 = swing_highs[-2], swing_highs[-1]
        x1h, y1h = sh1
        x2h, y2h = sh2
        slope = (y2h - y1h) / (x2h - x1h) if x2h != x1h else 0

        # Upper line dari 2 swing high
        upper_at_end = line_at(last_x, x1h, y1h, slope)

        # Lower line paralel melewati swing low terdekat
        sl = swing_lows2[-1]
        xl, yl = sl
        lower_intercept = yl - slope * xl
        lower_at_end = slope * last_x + lower_intercept

        # Mid line
        mid_at_end = (upper_at_end + lower_at_end) / 2
        channel_height = upper_at_end - lower_at_end

        # Pastiin upper > lower
        if channel_height > 0:
            upper_third = upper_at_end - channel_height / 3
            lower_third = lower_at_end + channel_height / 3
            return {
                "slope": slope,
                "intercept": lower_intercept,
                "std": channel_height / 3,
                "mid": round(mid_at_end, 2),
                "upper": round(upper_at_end, 2),
                "lower": round(lower_at_end, 2),
                "upper_third": round(upper_third, 2),
                "lower_third": round(lower_third, 2),
                "method": "parallel_2H1L"
            }

    # Coba ascending channel: 2 swing low + 1 swing high
    if len(swing_lows2) >= 2 and len(swing_highs) >= 1:
        sl1, sl2 = swing_lows2[-2], swing_lows2[-1]
        x1l, y1l = sl1
        x2l, y2l = sl2
        slope = (y2l - y1l) / (x2l - x1l) if x2l != x1l else 0

        lower_at_end = line_at(last_x, x1l, y1l, slope)

        sh = swing_highs[-1]
        xh, yh = sh
        upper_intercept = yh - slope * xh
        upper_at_end = slope * last_x + upper_intercept

        mid_at_end = (upper_at_end + lower_at_end) / 2
        channel_height = upper_at_end - lower_at_end

        if channel_height > 0:
            upper_third = upper_at_end - channel_height / 3
            lower_third = lower_at_end + channel_height / 3
            return {
                "slope": slope,
                "intercept": y1l - slope * x1l,
                "std": channel_height / 3,
                "mid": round(mid_at_end, 2),
                "upper": round(upper_at_end, 2),
                "lower": round(lower_at_end, 2),
                "upper_third": round(upper_third, 2),
                "lower_third": round(lower_third, 2),
                "method": "parallel_2L1H"
            }

    # Fallback linear regression
    x = np.arange(n)
    slope, intercept = np.polyfit(x, closes, 1)
    residuals = closes - (slope * x + intercept)
    std = np.std(residuals)
    mid   = slope * last_x + intercept
    upper = mid + 1.5 * std
    lower = mid - 1.5 * std
    upper_third = upper - (upper - lower) / 3
    lower_third = lower + (upper - lower) / 3
    return {
        "slope": slope, "intercept": intercept, "std": std,
        "mid": round(mid, 2), "upper": round(upper, 2), "lower": round(lower, 2),
        "upper_third": round(upper_third, 2), "lower_third": round(lower_third, 2),
        "method": "regression_fallback"
    }

def get_h4_bias(ch, price):
    if price >= ch["upper_third"]: return "SELL"
    elif price <= ch["lower_third"]: return "BUY"
    return "SKIP"

# ══════════════════════════════════════════════════════════════════
#  RSI
# ══════════════════════════════════════════════════════════════════

def calc_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 1)

# ══════════════════════════════════════════════════════════════════
#  S&D BASE DETECTION
# ══════════════════════════════════════════════════════════════════

def detect_sd_base(df, bias):
    bodies = np.abs(df["Close"].values - df["Open"].values)
    n = len(df)
    if n < 15: return None
    for base_end in range(n - 3, n - 12, -1):
        for base_len in range(2, 6):
            base_start = base_end - base_len
            if base_start < 5: continue
            base_slice  = df.iloc[base_start:base_end + 1]
            base_range  = base_slice["High"].max() - base_slice["Low"].min()
            base_bodies = bodies[base_start:base_end + 1].mean()
            avg_body_before = bodies[max(0, base_start - 5):base_start].mean()
            if avg_body_before == 0 or base_bodies > 0.5 * avg_body_before: continue
            move_start = max(0, base_start - 5)
            move_slice = df.iloc[move_start:base_start]
            if len(move_slice) < 2: continue
            move_range  = move_slice["High"].max() - move_slice["Low"].min()
            if base_range >= move_range: continue
            move_bodies = bodies[move_start:base_start].mean()
            if move_bodies < bodies.mean(): continue
            move_dir = "UP" if move_slice["Close"].iloc[-1] > move_slice["Close"].iloc[0] else "DOWN"
            if bias == "BUY"  and move_dir != "UP":   continue
            if bias == "SELL" and move_dir != "DOWN":  continue
            base_high = round(base_slice["High"].max(), 2)
            base_low  = round(base_slice["Low"].min(), 2)
            return {
                "found": True,
                "type": "RBR" if bias == "BUY" else "DBD",
                "base_high": base_high, "base_low": base_low,
                "base_mid": round((base_high + base_low) / 2, 2),
                "base_range": round(base_range, 2),
                "candles_in_base": base_len,
            }
    return None

# ══════════════════════════════════════════════════════════════════
#  S&R LEVELS — FIX: filter level yang terlalu deket entry
# ══════════════════════════════════════════════════════════════════

def find_sr_levels(df, min_distance=15):
    """
    Cari max 3 level S&R terkuat dari swing high/low M30.
    min_distance: jarak minimum dari harga sekarang (pips)
    """
    highs, lows = df["High"].values, df["Low"].values
    price = float(df["Close"].iloc[-1])
    levels = []
    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
           highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            lvl = round(highs[i], 2)
            # Filter level yang terlalu deket harga sekarang
            if abs(lvl - price) >= min_distance:
                levels.append(lvl)
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
           lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            lvl = round(lows[i], 2)
            if abs(lvl - price) >= min_distance:
                levels.append(lvl)
    if not levels: return []
    levels.sort()
    clustered = [levels[0]]
    for lv in levels[1:]:
        if lv - clustered[-1] > 5: clustered.append(lv)
    clustered.sort(key=lambda x: abs(x - price))
    return clustered[:3]

# ══════════════════════════════════════════════════════════════════
#  S&R FLIP M5
# ══════════════════════════════════════════════════════════════════

def check_sr_flip_m5(df_m5, sr_levels, bias):
    if not sr_levels: return {"confirmed": False}
    last_close = df_m5["Close"].iloc[-1]
    prev_close = df_m5["Close"].iloc[-2]
    for level in sr_levels:
        if bias == "BUY" and prev_close < level and last_close > level:
            return {"confirmed": True, "flip_type": "SUPPORT BARU", "flip_level": level,
                    "detail": f"M5 close {last_close:.2f} tembus ATAS {level:.2f}"}
        if bias == "SELL" and prev_close > level and last_close < level:
            return {"confirmed": True, "flip_type": "RESISTANCE BARU", "flip_level": level,
                    "detail": f"M5 close {last_close:.2f} tembus BAWAH {level:.2f}"}
    return {"confirmed": False}

# ══════════════════════════════════════════════════════════════════
#  CANDLE TRIGGER M1
# ══════════════════════════════════════════════════════════════════

def detect_m1_trigger(df_m1, bias):
    if len(df_m1) < 3: return {"found": False}
    c1 = df_m1.iloc[-2]
    c0 = df_m1.iloc[-3]
    o1, c1c = c1["Open"], c1["Close"]
    h1, l1  = c1["High"], c1["Low"]
    o0, c0c = c0["Open"], c0["Close"]
    body1  = abs(c1c - o1)
    range1 = h1 - l1
    body0  = abs(c0c - o0)
    if range1 == 0: return {"found": False}
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

# ══════════════════════════════════════════════════════════════════
#  SISTEM BINTANG
# ══════════════════════════════════════════════════════════════════

def calc_star_rating(bias_h4, sd_base, sr_flip, m1_trigger, ch_m30, price):
    stars = 0
    reasons = []
    stars += 1
    reasons.append(f"★ Setup searah bias H4 ({bias_h4})")
    if sd_base and sd_base.get("found"):
        stars += 1
        reasons.append(f"★ Pola {sd_base['type']} valid ({sd_base['candles_in_base']} candle di base)")
    if sr_flip.get("confirmed"):
        stars += 1
        reasons.append(f"★ M5 konfirmasi: {sr_flip['detail']}")
    elif sd_base and sd_base.get("found"):
        if bias_h4 == "BUY" and price <= sd_base["base_high"]:
            stars += 1
            reasons.append("★ Harga masuk zona base RBR (konfirmasi M5)")
        elif bias_h4 == "SELL" and price >= sd_base["base_low"]:
            stars += 1
            reasons.append("★ Harga masuk zona base DBD (konfirmasi M5)")
    if m1_trigger.get("found"):
        stars += 1
        reasons.append(f"★ Trigger M1: {m1_trigger['type']} ({m1_trigger['strength']})")
    return stars, reasons

# ══════════════════════════════════════════════════════════════════
#  SL / TP — FIX: TP1 minimum 20 pips dari entry
# ══════════════════════════════════════════════════════════════════

def calc_sl_tp(price, bias, sd_base, sr_levels, ch_m30):
    buffer   = 7.0
    min_tp1  = 20.0  # TP1 minimal 20 pips dari entry

    if bias == "BUY":
        sl_base = sd_base["base_low"] if sd_base and sd_base.get("found") else price - 15
        sl   = round(sl_base - buffer, 2)
        risk = abs(price - sl)
        # TP1: S&R di atas harga, minimal 20 pips
        tp1_c = [lv for lv in sr_levels if lv > price + min_tp1]
        tp1 = round(min(tp1_c), 2) if tp1_c else round(price + max(risk * 1.5, min_tp1), 2)
        tp2 = round(ch_m30["upper"], 2)
        # Pastiin TP2 di atas TP1
        if tp2 <= tp1: tp2 = round(price + risk * 3, 2)
    else:
        sl_base = sd_base["base_high"] if sd_base and sd_base.get("found") else price + 15
        sl   = round(sl_base + buffer, 2)
        risk = abs(sl - price)
        # TP1: S&R di bawah harga, minimal 20 pips
        tp1_c = [lv for lv in sr_levels if lv < price - min_tp1]
        tp1 = round(max(tp1_c), 2) if tp1_c else round(price - max(risk * 1.5, min_tp1), 2)
        tp2 = round(ch_m30["lower"], 2)
        # Pastiin TP2 di bawah TP1
        if tp2 >= tp1: tp2 = round(price - risk * 3, 2)

    rr1 = round(abs(tp1 - price) / risk, 2) if risk > 0 else 0
    rr2 = round(abs(tp2 - price) / risk, 2) if risk > 0 else 0
    return {"sl": sl, "tp1": tp1, "tp2": tp2,
            "risk_pips": round(risk, 1), "rr1": rr1, "rr2": rr2}

# ══════════════════════════════════════════════════════════════════
#  CHART — TradingView via chart-img.com
# ══════════════════════════════════════════════════════════════════

async def take_screenshot(tf="5"):
    """Screenshot TradingView via Playwright."""
    interval_map = {"1":"1","5":"5","15":"15","30":"30","60":"60","240":"240"}
    interval = interval_map.get(str(tf), "5")
    url = (
        f"https://s.tradingview.com/widgetembed/"
        f"?symbol=OANDA:XAUUSD&interval={interval}"
        f"&theme=dark&style=1&locale=id"
        f"&toolbar_bg=%23131722"
    )
    path = f"zexly_chart_{tf}.png"
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await ctx.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)
            import asyncio
            await asyncio.sleep(6)
            await page.screenshot(path=path)
            await browser.close()
        log.info(f"Screenshot tersimpan: {path}")
        return path
    except Exception as e:
        log.error(f"Screenshot error: {e}")
        return None

def overlay_annotations(img_path, ch_h4, ch_m30, sd_base, sr_levels, price, bias, stars):
    """Overlay anotasi ZEMETHOD di atas screenshot TradingView pakai PIL."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import math

        img = Image.open(img_path).convert("RGBA")
        w, h = img.size

        # Hitung price range dari channel
        price_min = ch_h4["lower"] - 50
        price_max = ch_h4["upper"] + 50
        price_range = price_max - price_min

        # Chart area (approximate — TradingView widget)
        chart_top    = 40
        chart_bottom = h - 60
        chart_h      = chart_bottom - chart_top

        def price_to_y(p):
            """Konversi harga ke pixel Y."""
            ratio = (price_max - p) / price_range
            return int(chart_top + ratio * chart_h)

        overlay = Image.new("RGBA", img.size, (0,0,0,0))
        draw = ImageDraw.Draw(overlay)

        # ─── H4 Upper ─────────────────────────────
        y_upper = price_to_y(ch_h4["upper"])
        draw.line([(0, y_upper), (w, y_upper)], fill=(255,76,76,200), width=2)
        draw.text((5, y_upper-14), f"H4 Upper {ch_h4['upper']}", fill=(255,76,76,255))

        # ─── H4 Mid ───────────────────────────────
        y_mid = price_to_y(ch_h4["mid"])
        draw.line([(0, y_mid), (w, y_mid)], fill=(255,255,255,100), width=1)

        # ─── H4 Lower ─────────────────────────────
        y_lower = price_to_y(ch_h4["lower"])
        draw.line([(0, y_lower), (w, y_lower)], fill=(0,200,83,200), width=2)
        draw.text((5, y_lower+2), f"H4 Lower {ch_h4['lower']}", fill=(0,200,83,255))

        # ─── Upper Zone fill ──────────────────────
        y_upper_third = price_to_y(ch_h4["upper_third"])
        draw.rectangle([(0, y_upper), (w, y_upper_third)], fill=(255,76,76,30))

        # ─── Lower Zone fill ──────────────────────
        y_lower_third = price_to_y(ch_h4["lower_third"])
        draw.rectangle([(0, y_lower_third), (w, y_lower)], fill=(0,200,83,30))

        # ─── M30 Channel ──────────────────────────
        y_m30_upper = price_to_y(ch_m30["upper"])
        draw.line([(0, y_m30_upper), (w, y_m30_upper)], fill=(255,140,0,150), width=1)
        draw.text((5, y_m30_upper-14), f"M30 Upper {ch_m30['upper']}", fill=(255,140,0,200))

        y_m30_lower = price_to_y(ch_m30["lower"])
        draw.line([(0, y_m30_lower), (w, y_m30_lower)], fill=(30,144,255,150), width=1)
        draw.text((5, y_m30_lower+2), f"M30 Lower {ch_m30['lower']}", fill=(30,144,255,200))

        # ─── S&D Base Zone ────────────────────────
        if sd_base and sd_base.get("found"):
            base_color = (0,200,83,60) if bias == "BUY" else (255,76,76,60)
            base_border = (0,200,83,200) if bias == "BUY" else (255,76,76,200)
            y_bh = price_to_y(sd_base["base_high"])
            y_bl = price_to_y(sd_base["base_low"])
            draw.rectangle([(0, y_bh), (w, y_bl)], fill=base_color)
            draw.line([(0, y_bh), (w, y_bh)], fill=base_border, width=1)
            draw.line([(0, y_bl), (w, y_bl)], fill=base_border, width=1)
            y_bm = price_to_y(sd_base["base_mid"])
            draw.text((8, y_bm-8), f"{sd_base['type']} Zone", fill=base_border)

        # ─── S&R Levels ───────────────────────────
        for lvl in sr_levels:
            y_sr = price_to_y(lvl)
            draw.line([(0, y_sr), (w, y_sr)], fill=(255,215,0,150), width=1)
            draw.text((w-120, y_sr-12), f"S&R {lvl}", fill=(255,215,0,200))

        # ─── Price Line ───────────────────────────
        y_price = price_to_y(price)
        draw.line([(0, y_price), (w, y_price)], fill=(255,215,0,230), width=2)
        draw.rectangle([(w-110, y_price-12), (w, y_price+4)], fill=(255,215,0,200))
        draw.text((w-108, y_price-11), f"${price}", fill=(0,0,0,255))

        # ─── Signal Label ─────────────────────────
        stars_str = "★" * stars + "☆" * (4-stars)
        sig_color = (0,200,83,230) if bias == "BUY" else (255,76,76,230)
        sig_txt = f"{'▲ BUY' if bias == 'BUY' else '▼ SELL'}  {stars_str}"
        draw.rectangle([(10, 50), (200, 80)], fill=(0,0,0,180))
        draw.text((14, 54), sig_txt, fill=sig_color)

        # Merge overlay
        out = Image.alpha_composite(img, overlay).convert("RGB")
        out.save(img_path)
        log.info("Overlay anotasi selesai")
        return img_path

    except Exception as e:
        log.error(f"Overlay error: {e}")
        return img_path

def generate_chart(bias, stars, tf="5", ch_h4=None, ch_m30=None,
                   sd_base=None, sr_levels=None, price=None):
    """Screenshot TradingView + overlay anotasi ZEMETHOD."""
    import asyncio
    path = asyncio.run(take_screenshot(tf))
    if path and ch_h4 and ch_m30 and price:
        path = overlay_annotations(path, ch_h4, ch_m30,
                                   sd_base, sr_levels or [], price, bias, stars)
    return path

# ══════════════════════════════════════════════════════════════════
#  TELEGRAM
# ══════════════════════════════════════════════════════════════════

def send_telegram(caption, photo_path=None, chat_id=None):
    cid  = chat_id or CHAT_ID
    base = f"https://api.telegram.org/bot{TOKEN}"
    try:
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, "rb") as ph:
                resp = requests.post(
                    f"{base}/sendPhoto",
                    data={"chat_id": cid, "caption": caption, "parse_mode": "Markdown"},
                    files={"photo": ph}, timeout=30
                )
        else:
            resp = requests.post(
                f"{base}/sendMessage",
                data={"chat_id": cid, "text": caption, "parse_mode": "Markdown"},
                timeout=20
            )
        resp.raise_for_status()
        log.info("Pesan terkirim")
        return True
    except Exception as e:
        log.error(f"Telegram error: {e}")
        return False

# ══════════════════════════════════════════════════════════════════
#  FORMAT PESAN SINYAL
# ══════════════════════════════════════════════════════════════════

def format_signal_msg(price, bias, stars, star_reasons, sd_base,
                      m1_trigger, sr_flip, sl_tp, rsi_m15,
                      session, ch_h4, ch_m30, force=False):
    stars_display = "★" * stars + "☆" * (4 - stars)
    trigger_txt = f"`{m1_trigger['type']} ({m1_trigger['strength']})`" \
                  if m1_trigger.get("found") else "`Belum muncul`"
    flip_txt = f"`{sr_flip['detail']}`" if sr_flip.get("confirmed") else "`Belum flip`"
    base_txt = (
        f"`{sd_base['type']} — {sd_base['candles_in_base']} candle`\n"
        f"   Zone: `{sd_base['base_low']} - {sd_base['base_high']}`"
    ) if sd_base and sd_base.get("found") else "`Tidak terdeteksi`"
    rsi_label = (
        "Overbought" if rsi_m15 >= 70 else "Near OB" if rsi_m15 >= 65 else
        "Oversold"   if rsi_m15 <= 30 else "Near OS"  if rsi_m15 <= 35 else "Netral"
    )
    reasons_str = "\n".join([f"  {r}" for r in star_reasons])
    header = "FORCE ENTRY (Manual Override)" if force else "ZEXLY METHOD — SINYAL ENTRY"
    rr_warn = f"\n   ⚠️ RR rendah ({sl_tp['rr1']}:1) — manage risk!" \
              if sl_tp and sl_tp["rr1"] < 1.5 else ""
    signal_emoji = "🔴 SELL" if bias == "SELL" else "🟢 BUY"

    return (
        f"*{header}*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📍 *Instrument:* XAUUSD\n"
        f"💰 *Price:* `${price}`\n"
        f"⚡ *Signal:* {signal_emoji}\n"
        f"⭐ *Kualitas:* `{stars_display}` ({stars}/4 bintang)\n"
        f"📡 *Sesi:* {session}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 *ANALISA ZEMETHOD*\n\n"
        f"🏗️ *H4 Channel*\n"
        f"  Upper: `{ch_h4['upper']}` | Mid: `{ch_h4['mid']}` | Lower: `{ch_h4['lower']}`\n"
        f"  Bias: `{bias} ONLY`\n\n"
        f"📐 *M30 Channel*\n"
        f"  Upper: `{ch_m30['upper']}` | Lower: `{ch_m30['lower']}`\n\n"
        f"🎯 *S&D Base:* {base_txt}\n\n"
        f"🔀 *S&R Flip M5:* {flip_txt}\n\n"
        f"🕯️ *Trigger M1:* {trigger_txt}\n\n"
        f"📈 *RSI M30:* `{rsi_m15}` — {rsi_label}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💼 *RENCANA TRADE*\n\n"
        f"  Entry : `${price}`\n"
        f"  SL    : `${sl_tp['sl']}` ({sl_tp['risk_pips']} pips)\n"
        f"  TP1   : `${sl_tp['tp1']}` (RR `{sl_tp['rr1']}:1`) → tutup 70%\n"
        f"  TP2   : `${sl_tp['tp2']}` (RR `{sl_tp['rr2']}:1`) → sisa 30%{rr_warn}\n\n"
        f"  TP1 hit → geser SL ke breakeven!\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ *ALASAN:*\n{reasons_str}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏰ Konfirmasi visual M1 sebelum entry!\n"
        f"`{get_waktu()}`"
    )

# ══════════════════════════════════════════════════════════════════
#  COMMAND HANDLER
# ══════════════════════════════════════════════════════════════════

def get_telegram_updates(offset=0):
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{TOKEN}/getUpdates",
            params={"offset": offset, "timeout": 5},
            timeout=10
        )
        return resp.json().get("result", [])
    except Exception: return []

def handle_commands():
    offset  = load_offset()
    updates = get_telegram_updates(offset)

    for update in updates:
        offset = update["update_id"] + 1
        save_offset(offset)

        msg = update.get("message") or update.get("channel_post")
        if not msg: continue

        text    = msg.get("text", "").strip().lower()
        chat_id = str(msg["chat"]["id"])
        log.info(f"Command: '{text}' dari {chat_id}")

        if text in ("/chart", "/scan", "/force"):
            send_telegram("🔍 Mengambil data... tunggu sebentar", chat_id=chat_id)
            data = fetch_data()
            if not data:
                send_telegram("❌ Gagal ambil data market.", chat_id=chat_id)
                continue

            price    = round(float(data["m1"]["Close"].iloc[-1]), 2)
            ch_h4    = calc_equidistant_channel(data["h4"])
            ch_m30   = calc_equidistant_channel(data["m30"])
            bias     = get_h4_bias(ch_h4, price)
            rsi      = calc_rsi(data["m30"]["Close"])
            sd_base  = detect_sd_base(data["m30"], bias) if bias != "SKIP" else None
            sr_lvls  = find_sr_levels(data["m30"])
            sr_flip  = check_sr_flip_m5(data["m5"], sr_lvls, bias) if bias != "SKIP" else {"confirmed": False}
            trigger  = detect_m1_trigger(data["m1"], bias) if bias != "SKIP" else {"found": False}
            _, session = get_session_status()

            if text == "/chart":
                # Chart M30 realtime
                tf_bias = "30"
                chart = generate_chart(bias, 0, tf=tf_bias)
                caption = (
                    f"📊 *XAUUSD M30 — REALTIME*\n"
                    f"💰 Price: `${price}` | Bias: `{bias}`\n"
                    f"📡 Sesi: {session}\n"
                    f"H4 Upper: `{ch_h4['upper']}` | Lower: `{ch_h4['lower']}`\n"
                    f"`{get_waktu()}`"
                )
                send_telegram(caption, chart, chat_id=chat_id)

            elif text == "/scan":
                if bias == "SKIP":
                    send_telegram(
                        f"*SCAN RESULT*\n💰 Price: `${price}`\nBias H4: `SKIP` (Middle Zone)\n`{get_waktu()}`",
                        chat_id=chat_id
                    )
                    continue
                stars, reasons = calc_star_rating(bias, sd_base, sr_flip, trigger, ch_m30, price)
                sl_tp   = calc_sl_tp(price, bias, sd_base, sr_lvls, ch_m30)
                caption = format_signal_msg(price, bias, stars, reasons, sd_base,
                                            trigger, sr_flip, sl_tp, rsi, session, ch_h4, ch_m30)
                chart = generate_chart(bias, stars, tf="5", ch_h4=ch_h4, ch_m30=ch_m30, sd_base=sd_base, sr_levels=sr_levels, price=price)
                send_telegram(caption, chart, chat_id=chat_id)

            elif text == "/force":
                force_bias = bias if bias != "SKIP" else "SELL"
                if bias == "SKIP":
                    reasons = ["⚠️ Forced — Middle Zone (tidak ideal)"]
                    stars   = 0
                else:
                    stars, reasons = calc_star_rating(bias, sd_base, sr_flip, trigger, ch_m30, price)
                    reasons.append("⚡ Dikirim via /force (manual override)")
                sl_tp   = calc_sl_tp(price, force_bias, sd_base, sr_lvls, ch_m30)
                caption = format_signal_msg(price, force_bias, stars, reasons, sd_base,
                                            trigger, sr_flip, sl_tp, rsi, session,
                                            ch_h4, ch_m30, force=True)
                chart = generate_chart(force_bias, stars, tf="5", ch_h4=ch_h4, ch_m30=ch_m30, sd_base=sd_base, sr_levels=sr_lvls, price=price)
                send_telegram(caption, chart, chat_id=chat_id)

        elif text == "/status":
            price = None
            try:
                df = yf.Ticker("GC=F").history(period="1d", interval="1m")
                price = round(float(df["Close"].iloc[-1]), 2)
            except Exception: pass
            ok_session, session = get_session_status()
            send_telegram(
                f"📊 *ZEXLY STATUS*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💰 Harga: `${price or 'N/A'}`\n"
                f"📡 Sesi: {session}\n"
                f"🟢 Trading: {'AKTIF' if ok_session else 'OFF'}\n"
                f"`{get_waktu()}`\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"`/chart` — chart M30 realtime\n"
                f"`/scan` — scan manual\n"
                f"`/force` — sinyal paksa\n"
                f"`/status` — status bot",
                chat_id=chat_id
            )

# ══════════════════════════════════════════════════════════════════
#  MAIN AUTO SCAN
# ══════════════════════════════════════════════════════════════════

def run_scan():
    log.info("═══ ZEXLY SCAN ═══")

    handle_commands()

    ok_session, session_name = get_session_status()
    if not ok_session:
        log.info(f"Off-session: {session_name}. Skip scan.")
        return

    data = fetch_data()
    if not data: return

    price    = round(float(data["m1"]["Close"].iloc[-1]), 2)
    ch_h4    = calc_equidistant_channel(data["h4"])
    ch_m30   = calc_equidistant_channel(data["m30"])
    bias     = get_h4_bias(ch_h4, price)

    log.info(f"Price: {price} | Bias: {bias} | Upper: {ch_h4['upper']} | Lower: {ch_h4['lower']}")

    if bias == "SKIP":
        log.info("Middle zone — SKIP")
        return

    rsi_m15    = calc_rsi(data["m30"]["Close"])
    sd_base    = detect_sd_base(data["m30"], bias)
    sr_levels  = find_sr_levels(data["m30"])
    sr_flip    = check_sr_flip_m5(data["m5"], sr_levels, bias)
    m1_trigger = detect_m1_trigger(data["m1"], bias)
    stars, star_reasons = calc_star_rating(bias, sd_base, sr_flip, m1_trigger, ch_m30, price)

    log.info(f"Stars: {stars}/4 | Base: {sd_base} | Trigger: {m1_trigger}")

    if stars < 3:
        log.info(f"Bintang {stars}/4 — belum cukup. Skip.")
        return

    signal_key = f"{bias}_{round(price, 0)}_{stars}"
    if already_alerted(signal_key):
        log.info("Sinyal sama sudah dikirim. Skip.")
        return

    sl_tp   = calc_sl_tp(price, bias, sd_base, sr_levels, ch_m30)
    caption = format_signal_msg(price, bias, stars, star_reasons, sd_base,
                                m1_trigger, sr_flip, sl_tp, rsi_m15,
                                session_name, ch_h4, ch_m30)
    chart   = generate_chart(bias, stars, tf="5", ch_h4=ch_h4, ch_m30=ch_m30, sd_base=sd_base, sr_levels=sr_levels, price=price)

    send_telegram(caption, chart)
    mark_alerted(signal_key)
    log.info(f"Sinyal {bias} {stars} bintang terkirim!")


if __name__ == "__main__":
    run_scan()
