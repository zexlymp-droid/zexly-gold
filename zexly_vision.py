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
        "slope": slope, "intercept": intercept, "std": std,
        "mid": round(mid, 2), "upper": round(upper, 2), "lower": round(lower, 2),
        "upper_third": round(upper_third, 2), "lower_third": round(lower_third, 2),
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

def generate_chart(bias, stars, tf="30"):
    """
    Ambil chart TradingView realtime via chart-img.com API.
    tf: 1=M1, 5=M5, 15=M15, 30=M30, 60=H1, 240=H4
    """
    path = "zexly_chart.png"

    if not CHARTIMG_KEY:
        log.warning("CHARTIMG_KEY tidak ada, skip chart")
        return None

    # Interval map untuk chart-img
    interval_map = {
        "1": "1m", "5": "5m", "15": "15m",
        "30": "30m", "60": "1h", "240": "4h"
    }
    interval = interval_map.get(str(tf), "30m")

    try:
        url = "https://api.chart-img.com/v1/tradingview/advanced-chart"
        params = {
            "symbol":   "OANDA:XAUUSD",
            "interval": interval,
            "theme":    "dark",
            "studies":  "RSI@tv-basicstudies",
            "width":    1280,
            "height":   720,
            "key":      CHARTIMG_KEY,
        }
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image"):
            with open(path, "wb") as f:
                f.write(resp.content)
            log.info(f"Chart TradingView tersimpan: {path}")
            return path
        else:
            log.error(f"chart-img error: {resp.status_code} — {resp.text[:200]}")
            return None
    except Exception as e:
        log.error(f"Chart error: {e}")
        return None

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
                chart = generate_chart(bias, stars, tf="5")
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
                chart = generate_chart(force_bias, stars, tf="5")
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
    chart   = generate_chart(bias, stars, tf="5")

    send_telegram(caption, chart)
    mark_alerted(signal_key)
    log.info(f"Sinyal {bias} {stars} bintang terkirim!")


if __name__ == "__main__":
    run_scan()
