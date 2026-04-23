"""
╔══════════════════════════════════════════════════════════╗
║   ZEXLY METHOD BOT v3.0 — XAUUSD AUTO SCANNER          ║
║   Parallel Channel + S&D + Price Action                  ║
║   Sesuai ZEMETHOD Ebook (H4 → M30 → M5 → M1)           ║
║                                                          ║
║   Commands:                                              ║
║   /setchannel [p1] [p2] [p3] — set channel manual      ║
║   /delchannel                 — hapus channel manual    ║
║   /scan                       — scan manual             ║
║   /force                      — sinyal paksa            ║
║   /chart [tf]                 — chart realtime          ║
║   /status                     — status bot              ║
║   /summary                    — ringkasan harian        ║
╚══════════════════════════════════════════════════════════╝
"""

import os, logging, json, re
from datetime import datetime, timedelta
import pytz
import numpy as np
import pandas as pd
import yfinance as yf
import requests
from dotenv import load_dotenv

load_dotenv()

# ─── CONFIG ────────────────────────────────────────────────────
TOKEN        = os.getenv("TELEGRAM_TOKEN")
CHAT_ID      = os.getenv("TELEGRAM_CHAT_ID", "-1003986432270")
CHARTIMG_KEY = os.getenv("CHARTIMG_KEY", "")
ZEXLY_CH_ENV = os.getenv("ZEXLY_CHANNEL", "")  # format: "4920,4880,4660"
WIB          = pytz.timezone("Asia/Jakarta")

STATE_FILE   = "zexly_state.json"
OFFSET_FILE  = "tg_offset.json"
CHANNEL_FILE = "zexly_channel.json"
POSITION_FILE = "zexly_position.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("ZEXLY")

# ══════════════════════════════════════════════════════════════════
#  STATE MANAGEMENT
# ══════════════════════════════════════════════════════════════════

def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

def already_alerted(signal_key):
    state = load_json(STATE_FILE)
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    return state.get("date") == today and state.get("key") == signal_key

def mark_alerted(signal_key):
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    save_json(STATE_FILE, {"date": today, "key": signal_key})

def load_offset():
    return load_json(OFFSET_FILE, {"offset": 0}).get("offset", 0)

def save_offset(offset):
    save_json(OFFSET_FILE, {"offset": offset})

# ══════════════════════════════════════════════════════════════════
#  CHANNEL MANAGEMENT
# ══════════════════════════════════════════════════════════════════

def calc_channel_from_3points(p1, p2, p3):
    pts    = sorted([p1, p2, p3], reverse=True)
    high1, mid_pt, low1 = pts[0], pts[1], pts[2]
    diff_top = abs(high1 - mid_pt)
    diff_bot = abs(mid_pt - low1)
    if diff_top < diff_bot:
        upper = (high1 + mid_pt) / 2
        lower = low1
        mode  = "2H+1L"
    else:
        upper = high1
        lower = (mid_pt + low1) / 2
        mode  = "1H+2L"
    channel_height = upper - lower
    upper_third    = upper - channel_height / 3
    lower_third    = lower + channel_height / 3
    mid            = (upper + lower) / 2
    return {
        "upper": round(upper, 2), "lower": round(lower, 2),
        "mid": round(mid, 2), "upper_third": round(upper_third, 2),
        "lower_third": round(lower_third, 2), "slope": 0,
        "intercept": lower, "std": round(channel_height / 3, 2),
        "mode": mode, "manual": True, "points": [p1, p2, p3]
    }

def load_manual_channel():
    # Prioritas 1: env variable (GitHub Secrets)
    if ZEXLY_CH_ENV:
        try:
            parts = [float(x) for x in ZEXLY_CH_ENV.split(",")]
            if len(parts) == 3:
                return calc_channel_from_3points(*parts)
        except Exception:
            pass
    # Prioritas 2: file lokal
    data = load_json(CHANNEL_FILE)
    return data if data else None

def save_manual_channel(data):
    save_json(CHANNEL_FILE, data)

def delete_manual_channel():
    try:
        os.remove(CHANNEL_FILE)
    except Exception:
        pass

# ══════════════════════════════════════════════════════════════════
#  POSITION TRACKING (untuk notif TP hit)
# ══════════════════════════════════════════════════════════════════

def save_position(bias, entry, sl, tp1, tp2):
    save_json(POSITION_FILE, {
        "bias": bias, "entry": entry,
        "sl": sl, "tp1": tp1, "tp2": tp2,
        "tp1_hit": False, "tp2_hit": False,
        "sl_hit": False,
        "time": get_waktu()
    })

def load_position():
    return load_json(POSITION_FILE)

def clear_position():
    try:
        os.remove(POSITION_FILE)
    except Exception:
        pass

def check_tp_sl_hit(price):
    pos = load_position()
    if not pos or not pos.get("bias"):
        return

    bias  = pos["bias"]
    entry = pos["entry"]
    sl    = pos["sl"]
    tp1   = pos["tp1"]
    tp2   = pos["tp2"]
    tp1_hit = pos.get("tp1_hit", False)
    tp2_hit = pos.get("tp2_hit", False)
    sl_hit  = pos.get("sl_hit", False)

    if sl_hit or tp2_hit:
        clear_position()
        return

    alerts = []

    if bias == "SELL":
        if not tp1_hit and price <= tp1:
            alerts.append(f"🎯 *TP1 HIT!* `${tp1}`\nTutup 70% posisi & geser SL ke `${entry}` (breakeven)")
            pos["tp1_hit"] = True
        if tp1_hit and not tp2_hit and price <= tp2:
            alerts.append(f"🏆 *TP2 HIT!* `${tp2}`\nTutup sisa 30% posisi — FULL PROFIT!")
            pos["tp2_hit"] = True
        if not sl_hit and price >= sl:
            alerts.append(f"🛑 *SL HIT!* `${sl}`\nPosisi ditutup — loss terkontrol.")
            pos["sl_hit"] = True
    elif bias == "BUY":
        if not tp1_hit and price >= tp1:
            alerts.append(f"🎯 *TP1 HIT!* `${tp1}`\nTutup 70% posisi & geser SL ke `${entry}` (breakeven)")
            pos["tp1_hit"] = True
        if tp1_hit and not tp2_hit and price >= tp2:
            alerts.append(f"🏆 *TP2 HIT!* `${tp2}`\nTutup sisa 30% posisi — FULL PROFIT!")
            pos["tp2_hit"] = True
        if not sl_hit and price <= sl:
            alerts.append(f"🛑 *SL HIT!* `${sl}`\nPosisi ditutup — loss terkontrol.")
            pos["sl_hit"] = True

    for alert in alerts:
        msg = (
            f"{alert}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Entry: `${entry}` | Price: `${price}`\n"
            f"SL: `${sl}` | TP1: `${tp1}` | TP2: `${tp2}`\n"
            f"`{get_waktu()}`"
        )
        send_telegram(msg)
        log.info(f"Alert: {alert[:30]}")

    save_json(POSITION_FILE, pos)

    if pos.get("sl_hit") or pos.get("tp2_hit"):
        clear_position()

# ══════════════════════════════════════════════════════════════════
#  JAM TRADING (ZEMETHOD Bab 07)
# ══════════════════════════════════════════════════════════════════

def get_session_status():
    now = datetime.now(WIB)
    t   = now.hour * 60 + now.minute
    if 14*60 <= t < 19*60:   return True,  "London Open (TERBAIK)"
    elif 20*60 <= t < 23*60: return True,  "New York Session (BAIK)"
    elif 19*60 <= t < 20*60: return True,  "NY-London Overlap (HATI-HATI)"
    else:                     return False, "Asian / Off-Session"

def get_waktu():
    return datetime.now(WIB).strftime("%d %b %Y | %H:%M WIB")

# ══════════════════════════════════════════════════════════════════
#  NEWS FILTER — Forex Factory scraping
# ══════════════════════════════════════════════════════════════════

def get_high_impact_news():
    """
    Scrape Forex Factory untuk high impact news USD hari ini.
    Return list of {"time": datetime, "title": str}
    """
    try:
        today = datetime.now(WIB).strftime("%b%d.%Y").lower()
        url   = f"https://www.forexfactory.com/calendar?day={today}"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return []

        # Cari high impact USD news
        pattern = r'impact--red.*?<td class="calendar__currency">(.*?)</td>.*?<td class="calendar__event">(.*?)</td>.*?<td class="calendar__time">(.*?)</td>'
        matches = re.findall(pattern, resp.text, re.DOTALL)

        news = []
        now_wib = datetime.now(WIB)
        for currency, title, time_str in matches:
            currency = re.sub(r'<.*?>', '', currency).strip()
            title    = re.sub(r'<.*?>', '', title).strip()
            time_str = re.sub(r'<.*?>', '', time_str).strip()
            if "USD" not in currency:
                continue
            try:
                t = datetime.strptime(f"{now_wib.strftime('%Y-%m-%d')} {time_str}", "%Y-%m-%d %I:%M%p")
                t = WIB.localize(t) + timedelta(hours=12)  # EST to WIB approx
                news.append({"time": t, "title": title})
            except Exception:
                continue
        return news
    except Exception as e:
        log.warning(f"News fetch gagal: {e}")
        return []

def is_near_news(buffer_minutes=30):
    """Cek apakah sekarang dalam 30 menit sebelum/sesudah high impact news."""
    news_list = get_high_impact_news()
    now = datetime.now(WIB)
    for news in news_list:
        diff = abs((news["time"] - now).total_seconds() / 60)
        if diff <= buffer_minutes:
            return True, news["title"]
    return False, ""

# ══════════════════════════════════════════════════════════════════
#  DATA FETCH
# ══════════════════════════════════════════════════════════════════

def fetch_data():
    try:
        gold   = yf.Ticker("GC=F")
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

def get_current_price():
    try:
        df = yf.Ticker("GC=F").history(period="1d", interval="1m")
        return round(float(df["Close"].iloc[-1]), 2)
    except Exception:
        return None

# ══════════════════════════════════════════════════════════════════
#  PARALLEL CHANNEL (auto fallback)
# ══════════════════════════════════════════════════════════════════

def find_swings(arr, order=5):
    highs, lows = [], []
    for i in range(order, len(arr) - order):
        if all(arr[i] >= arr[i-j] for j in range(1, order+1)) and \
           all(arr[i] >= arr[i+j] for j in range(1, order+1)):
            highs.append((i, float(arr[i])))
        if all(arr[i] <= arr[i-j] for j in range(1, order+1)) and \
           all(arr[i] <= arr[i+j] for j in range(1, order+1)):
            lows.append((i, float(arr[i])))
    return highs, lows

def calc_auto_channel(df):
    highs_arr = df["High"].values
    lows_arr  = df["Low"].values
    closes    = df["Close"].values
    n         = len(closes)
    last_x    = n - 1

    swing_highs, swing_lows = find_swings(highs_arr, order=5)
    _, swing_lows2 = find_swings(lows_arr, order=5)

    def line_at(x, x1, y1, slope):
        return y1 + slope * (x - x1)

    # Coba 2H + 1L
    if len(swing_highs) >= 2 and len(swing_lows2) >= 1:
        sh1, sh2 = swing_highs[-2], swing_highs[-1]
        x1h, y1h = sh1
        x2h, y2h = sh2
        slope = (y2h - y1h) / (x2h - x1h) if x2h != x1h else 0
        upper_at_end = line_at(last_x, x1h, y1h, slope)
        xl, yl = swing_lows2[-1]
        lower_intercept = yl - slope * xl
        lower_at_end = slope * last_x + lower_intercept
        channel_height = upper_at_end - lower_at_end
        if channel_height > 20:
            mid = (upper_at_end + lower_at_end) / 2
            return {
                "slope": slope, "intercept": lower_intercept,
                "std": channel_height / 3,
                "mid": round(mid, 2),
                "upper": round(upper_at_end, 2),
                "lower": round(lower_at_end, 2),
                "upper_third": round(upper_at_end - channel_height/3, 2),
                "lower_third": round(lower_at_end + channel_height/3, 2),
                "mode": "auto_2H1L", "manual": False
            }

    # Coba 2L + 1H
    if len(swing_lows2) >= 2 and len(swing_highs) >= 1:
        sl1, sl2 = swing_lows2[-2], swing_lows2[-1]
        x1l, y1l = sl1
        x2l, y2l = sl2
        slope = (y2l - y1l) / (x2l - x1l) if x2l != x1l else 0
        lower_at_end = line_at(last_x, x1l, y1l, slope)
        xh, yh = swing_highs[-1]
        upper_intercept = yh - slope * xh
        upper_at_end = slope * last_x + upper_intercept
        channel_height = upper_at_end - lower_at_end
        if channel_height > 20:
            mid = (upper_at_end + lower_at_end) / 2
            return {
                "slope": slope, "intercept": y1l - slope*x1l,
                "std": channel_height / 3,
                "mid": round(mid, 2),
                "upper": round(upper_at_end, 2),
                "lower": round(lower_at_end, 2),
                "upper_third": round(upper_at_end - channel_height/3, 2),
                "lower_third": round(lower_at_end + channel_height/3, 2),
                "mode": "auto_2L1H", "manual": False
            }

    # Fallback linear regression
    x = np.arange(n)
    slope, intercept = np.polyfit(x, closes, 1)
    residuals = closes - (slope * x + intercept)
    std = np.std(residuals)
    mid   = slope * last_x + intercept
    upper = mid + 1.5 * std
    lower = mid - 1.5 * std
    return {
        "slope": slope, "intercept": intercept, "std": std,
        "mid": round(mid, 2), "upper": round(upper, 2), "lower": round(lower, 2),
        "upper_third": round(upper - (upper-lower)/3, 2),
        "lower_third": round(lower + (upper-lower)/3, 2),
        "mode": "regression", "manual": False
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
    return round(float((100 - (100 / (1 + rs))).iloc[-1]), 1)

# ══════════════════════════════════════════════════════════════════
#  S&D BASE — threshold dilonggarkan
# ══════════════════════════════════════════════════════════════════

def detect_sd_base(df, bias):
    bodies = np.abs(df["Close"].values - df["Open"].values)
    n = len(df)
    if n < 15: return None

    for base_end in range(n - 2, n - 15, -1):
        for base_len in range(2, 7):  # max 6 candle (dilonggarkan dari 5)
            base_start = base_end - base_len
            if base_start < 5: continue

            base_slice  = df.iloc[base_start:base_end + 1]
            base_range  = base_slice["High"].max() - base_slice["Low"].min()
            base_bodies = bodies[base_start:base_end + 1].mean()
            avg_body_before = bodies[max(0, base_start - 5):base_start].mean()

            if avg_body_before == 0: continue
            if base_bodies > 0.6 * avg_body_before: continue  # dilonggarkan dari 0.5

            move_start = max(0, base_start - 6)
            move_slice = df.iloc[move_start:base_start]
            if len(move_slice) < 2: continue

            move_range  = move_slice["High"].max() - move_slice["Low"].min()
            if base_range >= move_range * 0.8: continue  # dilonggarkan

            move_bodies = bodies[move_start:base_start].mean()
            if move_bodies < bodies.mean() * 0.8: continue  # dilonggarkan

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
#  S&R LEVELS
# ══════════════════════════════════════════════════════════════════

def find_sr_levels(df, min_distance=15):
    highs, lows = df["High"].values, df["Low"].values
    price = float(df["Close"].iloc[-1])
    levels = []
    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
           highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            lvl = round(highs[i], 2)
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
            return {"confirmed": True, "flip_type": "SUPPORT BARU",
                    "detail": f"M5 close {last_close:.2f} tembus ATAS {level:.2f}"}
        if bias == "SELL" and prev_close > level and last_close < level:
            return {"confirmed": True, "flip_type": "RESISTANCE BARU",
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
    body1   = abs(c1c - o1)
    range1  = h1 - l1
    body0   = abs(c0c - o0)
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
#  SISTEM BINTANG (ZEMETHOD Bab 05)
# ══════════════════════════════════════════════════════════════════

def calc_star_rating(bias_h4, sd_base, sr_flip, m1_trigger, ch_m30, price):
    stars   = 0
    reasons = []

    # Bintang 1 — Bias H4
    stars += 1
    reasons.append(f"★ Setup searah bias H4 ({bias_h4})")

    # Bintang 2 — S&D Base valid
    if sd_base and sd_base.get("found"):
        stars += 1
        reasons.append(f"★ Pola {sd_base['type']} valid ({sd_base['candles_in_base']} candle di base)")

    # Bintang 3 — Konfirmasi M5
    if sr_flip.get("confirmed"):
        stars += 1
        reasons.append(f"★ S&R Flip M5: {sr_flip['detail']}")
    elif sd_base and sd_base.get("found"):
        if bias_h4 == "BUY"  and price <= sd_base["base_high"]:
            stars += 1
            reasons.append("★ Harga masuk zona base RBR (konfirmasi M5)")
        elif bias_h4 == "SELL" and price >= sd_base["base_low"]:
            stars += 1
            reasons.append("★ Harga masuk zona base DBD (konfirmasi M5)")

    # Bintang 4 — Trigger M1
    if m1_trigger.get("found"):
        stars += 1
        reasons.append(f"★ Trigger M1: {m1_trigger['type']} ({m1_trigger['strength']})")

    return stars, reasons

# ══════════════════════════════════════════════════════════════════
#  SL / TP
# ══════════════════════════════════════════════════════════════════

def calc_sl_tp(price, bias, sd_base, sr_levels, ch_m30):
    buffer  = 7.0
    min_tp1 = 20.0

    if bias == "BUY":
        sl_base = sd_base["base_low"] if sd_base and sd_base.get("found") else price - 15
        sl   = round(sl_base - buffer, 2)
        risk = abs(price - sl)
        tp1_c = [lv for lv in sr_levels if lv > price + min_tp1]
        tp1   = round(min(tp1_c), 2) if tp1_c else round(price + max(risk * 1.5, min_tp1), 2)
        tp2   = round(ch_m30["upper"], 2)
        if tp2 <= tp1: tp2 = round(price + risk * 3, 2)
    else:
        sl_base = sd_base["base_high"] if sd_base and sd_base.get("found") else price + 15
        sl   = round(sl_base + buffer, 2)
        risk = abs(sl - price)
        tp1_c = [lv for lv in sr_levels if lv < price - min_tp1]
        tp1   = round(max(tp1_c), 2) if tp1_c else round(price - max(risk * 1.5, min_tp1), 2)
        tp2   = round(ch_m30["lower"], 2)
        if tp2 >= tp1: tp2 = round(price - risk * 3, 2)

    rr1 = round(abs(tp1 - price) / risk, 2) if risk > 0 else 0
    rr2 = round(abs(tp2 - price) / risk, 2) if risk > 0 else 0
    return {"sl": sl, "tp1": tp1, "tp2": tp2,
            "risk_pips": round(risk, 1), "rr1": rr1, "rr2": rr2}

# ══════════════════════════════════════════════════════════════════
#  CHART — TradingView via chart-img.com
# ══════════════════════════════════════════════════════════════════

INTERVAL_MAP = {
    "M1": "1", "M5": "5", "M15": "15",
    "M30": "30", "H1": "60", "H4": "240"
}

def generate_chart(tf="M5"):
    """Screenshot TradingView via Playwright."""
    import asyncio
    from playwright.async_api import async_playwright

    interval = INTERVAL_MAP.get(tf.upper(), "5")
    path = f"zexly_chart_{tf}.png"

    async def _screenshot():
        url = (
            f"https://s.tradingview.com/widgetembed/"
            f"?symbol=OANDA:XAUUSD&interval={interval}"
            f"&theme=dark&style=1&locale=id"
            f"&toolbar_bg=%23131722"
        )
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                ctx = await browser.new_context(viewport={"width": 1280, "height": 720})
                page = await ctx.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(6)
                await page.screenshot(path=path)
                await browser.close()
            log.info(f"Screenshot {tf} tersimpan")
            return path
        except Exception as e:
            log.error(f"Screenshot error: {e}")
            return None

    try:
        return asyncio.run(_screenshot())
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
#  FORMAT PESAN
# ══════════════════════════════════════════════════════════════════

def format_signal_msg(price, bias, stars, star_reasons, sd_base,
                      m1_trigger, sr_flip, sl_tp, rsi_m15,
                      session, ch_h4, ch_m30, force=False):
    stars_display = "★" * stars + "☆" * (4 - stars)
    signal_emoji  = "🔴 SELL" if bias == "SELL" else "🟢 BUY"
    trigger_txt   = f"`{m1_trigger['type']} ({m1_trigger['strength']})`" \
                    if m1_trigger.get("found") else "`Belum muncul`"
    flip_txt      = f"`{sr_flip['detail']}`" \
                    if sr_flip.get("confirmed") else "`Belum flip`"
    base_txt      = (
        f"`{sd_base['type']} — {sd_base['candles_in_base']} candle`\n"
        f"   Zone: `{sd_base['base_low']} - {sd_base['base_high']}`"
    ) if sd_base and sd_base.get("found") else "`Tidak terdeteksi`"
    rsi_label = (
        "⚠️ Overbought" if rsi_m15 >= 70 else "🔶 Near OB" if rsi_m15 >= 65 else
        "⚠️ Oversold"   if rsi_m15 <= 30 else "🔷 Near OS" if rsi_m15 <= 35 else "➖ Netral"
    )
    reasons_str = "\n".join([f"  {r}" for r in star_reasons])
    header      = "⚡ *FORCE ENTRY (Manual Override)*" if force else "🦅 *ZEXLY METHOD — SINYAL ENTRY*"
    rr_warn     = f"\n   ⚠️ RR rendah ({sl_tp['rr1']}:1) — manage risk!" \
                  if sl_tp["rr1"] < 1.5 else ""
    ch_mode     = ch_h4.get("mode", "auto")
    manual_tag  = " _(manual)_" if ch_h4.get("manual") else f" _{ch_mode}_"

    return (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📍 *Instrument:* XAUUSD\n"
        f"💰 *Price:* `${price}`\n"
        f"⚡ *Signal:* {signal_emoji}\n"
        f"⭐ *Kualitas:* `{stars_display}` ({stars}/4 bintang)\n"
        f"📡 *Sesi:* {session}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 *ANALISA ZEMETHOD*\n\n"
        f"🏗️ *H4 Channel*{manual_tag}\n"
        f"   Upper: `{ch_h4['upper']}` | Mid: `{ch_h4['mid']}` | Lower: `{ch_h4['lower']}`\n"
        f"   Bias: `{bias} ONLY`\n\n"
        f"📐 *M30 Channel*\n"
        f"   Upper: `{ch_m30['upper']}` | Lower: `{ch_m30['lower']}`\n\n"
        f"🎯 *S&D Base:* {base_txt}\n\n"
        f"🔀 *S&R Flip M5:* {flip_txt}\n\n"
        f"🕯️ *Trigger M1:* {trigger_txt}\n\n"
        f"📈 *RSI M30:* `{rsi_m15}` — {rsi_label}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💼 *RENCANA TRADE*\n\n"
        f"   Entry : `${price}`\n"
        f"   SL    : `${sl_tp['sl']}` ({sl_tp['risk_pips']} pips)\n"
        f"   TP1   : `${sl_tp['tp1']}` (RR `{sl_tp['rr1']}:1`) → tutup 70%\n"
        f"   TP2   : `${sl_tp['tp2']}` (RR `{sl_tp['rr2']}:1`) → sisa 30%{rr_warn}\n\n"
        f"   TP1 hit → geser SL ke breakeven!\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ *ALASAN:*\n{reasons_str}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏰ Konfirmasi visual M1 sebelum entry!\n"
        f"`{get_waktu()}`"
    )

# ══════════════════════════════════════════════════════════════════
#  DAILY SUMMARY
# ══════════════════════════════════════════════════════════════════

def send_daily_summary():
    now = datetime.now(WIB)
    # Kirim summary jam 14:00 WIB (London open)
    if now.hour != 14 or now.minute > 5:
        return

    state = load_json(STATE_FILE)
    if state.get("summary_date") == now.strftime("%Y-%m-%d"):
        return  # Udah kirim hari ini

    data = fetch_data()
    if not data: return

    price     = round(float(data["m1"]["Close"].iloc[-1]), 2)
    manual_ch = load_manual_channel()
    ch_h4     = manual_ch if manual_ch else calc_auto_channel(data["h4"])
    ch_m30    = calc_auto_channel(data["m30"])
    bias      = get_h4_bias(ch_h4, price)
    rsi       = calc_rsi(data["m30"]["Close"])
    sr_levels = find_sr_levels(data["m30"])
    _, session = get_session_status()

    bias_emoji = "🔴 SELL ONLY" if bias == "SELL" else "🟢 BUY ONLY" if bias == "BUY" else "⏸ SKIP (Middle Zone)"
    ch_mode    = "manual" if ch_h4.get("manual") else ch_h4.get("mode", "auto")
    sr_txt     = " | ".join([f"`{lv}`" for lv in sr_levels]) if sr_levels else "`Tidak ada`"

    near_news, news_title = is_near_news(60)
    news_txt = f"⚠️ News dalam 1 jam: _{news_title}_" if near_news else "✅ Tidak ada high impact news"

    msg = (
        f"🌅 *ZEXLY DAILY SUMMARY*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📅 {now.strftime('%A, %d %b %Y')}\n"
        f"💰 Price: `${price}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏗️ *H4 Channel* _{ch_mode}_\n"
        f"   Upper: `{ch_h4['upper']}` | Lower: `{ch_h4['lower']}`\n"
        f"   Upper Zone: > `{ch_h4['upper_third']}`\n"
        f"   Lower Zone: < `{ch_h4['lower_third']}`\n\n"
        f"⚡ *Bias Hari Ini:* {bias_emoji}\n\n"
        f"📐 *M30 Channel*\n"
        f"   Upper: `{ch_m30['upper']}` | Lower: `{ch_m30['lower']}`\n\n"
        f"🎯 *Level S&R Penting:* {sr_txt}\n\n"
        f"📈 *RSI M30:* `{rsi}`\n\n"
        f"{news_txt}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Fokus trading: *London 14:00-19:00* & *NY 20:00-23:00 WIB*\n"
        f"`{get_waktu()}`"
    )

    chart = generate_chart("M30")
    send_telegram(msg, chart)

    state["summary_date"] = now.strftime("%Y-%m-%d")
    save_json(STATE_FILE, state)
    log.info("Daily summary terkirim")

# ══════════════════════════════════════════════════════════════════
#  COMMAND HANDLER
# ══════════════════════════════════════════════════════════════════

def get_telegram_updates(offset=0):
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{TOKEN}/getUpdates",
            params={"offset": offset, "timeout": 5}, timeout=10
        )
        return resp.json().get("result", [])
    except Exception: return []

def do_scan(data, bias, ch_h4, ch_m30, price, force=False):
    """Jalanin scan dan return caption + chart."""
    rsi      = calc_rsi(data["m30"]["Close"])
    sd_base  = detect_sd_base(data["m30"], bias) if bias != "SKIP" else None
    sr_lvls  = find_sr_levels(data["m30"])
    sr_flip  = check_sr_flip_m5(data["m5"], sr_lvls, bias) if bias != "SKIP" else {"confirmed": False}
    trigger  = detect_m1_trigger(data["m1"], bias) if bias != "SKIP" else {"found": False}
    _, session = get_session_status()

    if bias == "SKIP" and not force:
        return (
            f"⏸ *SCAN RESULT*\n"
            f"💰 Price: `${price}`\n"
            f"Bias H4: `SKIP` — Middle Zone, tidak trading\n"
            f"`{get_waktu()}`"
        ), None

    stars, reasons = calc_star_rating(bias, sd_base, sr_flip, trigger, ch_m30, price)
    if force: reasons.append("⚡ Dikirim via /force (manual override)")

    sl_tp   = calc_sl_tp(price, bias, sd_base, sr_lvls, ch_m30)
    caption = format_signal_msg(price, bias, stars, reasons, sd_base,
                                trigger, sr_flip, sl_tp, rsi,
                                session, ch_h4, ch_m30, force=force)
    chart   = generate_chart("M5")
    return caption, chart

def handle_commands():
    offset  = load_offset()
    updates = get_telegram_updates(offset)

    for update in updates:
        offset = update["update_id"] + 1
        save_offset(offset)

        msg = update.get("message") or update.get("channel_post")
        if not msg: continue

        text    = msg.get("text", "").strip()
        cmd     = text.lower().split()[0] if text else ""
        chat_id = str(msg["chat"]["id"])
        log.info(f"Command: '{cmd}' dari {chat_id}")

        # ─── /setchannel ──────────────────────────────
        if cmd == "/setchannel":
            parts = text.split()
            if len(parts) != 4:
                send_telegram(
                    "*Format:* `/setchannel [p1] [p2] [p3]`\n\n"
                    "Contoh 2 upper 1 lower:\n`/setchannel 4920 4880 4660`\n\n"
                    "Contoh 1 upper 2 lower:\n`/setchannel 4920 4700 4660`",
                    chat_id=chat_id
                )
                continue
            try:
                p1, p2, p3 = float(parts[1]), float(parts[2]), float(parts[3])
                ch = calc_channel_from_3points(p1, p2, p3)
                save_manual_channel(ch)
                send_telegram(
                    f"✅ *CHANNEL DISIMPAN*\n"
                    f"Mode: `{ch['mode']}`\n"
                    f"Upper: `{ch['upper']}` | Mid: `{ch['mid']}` | Lower: `{ch['lower']}`\n"
                    f"Upper Zone: > `{ch['upper_third']}`\n"
                    f"Lower Zone: < `{ch['lower_third']}`\n\n"
                    f"Bot pakai channel ini sampai lu update lagi.",
                    chat_id=chat_id
                )
            except ValueError:
                send_telegram("❌ Angka tidak valid. Contoh: `/setchannel 4920 4880 4660`",
                              chat_id=chat_id)

        # ─── /delchannel ──────────────────────────────
        elif cmd == "/delchannel":
            delete_manual_channel()
            send_telegram(
                "🗑️ *Channel manual dihapus.*\n"
                "Bot kembali pakai auto detect parallel channel.",
                chat_id=chat_id
            )

        # ─── /scan & /force ───────────────────────────
        elif cmd in ("/scan", "/force"):
            send_telegram("🔍 Scanning... tunggu sebentar", chat_id=chat_id)
            data = fetch_data()
            if not data:
                send_telegram("❌ Gagal ambil data market.", chat_id=chat_id)
                continue
            price     = round(float(data["m1"]["Close"].iloc[-1]), 2)
            manual_ch = load_manual_channel()
            ch_h4     = manual_ch if manual_ch else calc_auto_channel(data["h4"])
            ch_m30    = calc_auto_channel(data["m30"])
            bias      = get_h4_bias(ch_h4, price)
            force     = cmd == "/force"
            if force and bias == "SKIP":
                bias = "SELL"  # default ke SELL kalau middle zone
            caption, chart = do_scan(data, bias, ch_h4, ch_m30, price, force=force)
            send_telegram(caption, chart, chat_id=chat_id)
            # Save position untuk monitoring TP/SL
            if force or True:
                try:
                    sl_tp = calc_sl_tp(price, bias,
                                       detect_sd_base(data["m30"], bias),
                                       find_sr_levels(data["m30"]), ch_m30)
                    save_position(bias, price, sl_tp["sl"], sl_tp["tp1"], sl_tp["tp2"])
                except Exception: pass

        # ─── /chart ───────────────────────────────────
        elif cmd == "/chart":
            parts = text.split()
            tf    = parts[1].upper() if len(parts) > 1 else "M30"
            if tf not in INTERVAL_MAP:
                send_telegram(f"TF tidak valid. Pilihan: {', '.join(INTERVAL_MAP.keys())}",
                              chat_id=chat_id)
                continue
            send_telegram(f"📸 Mengambil chart {tf}...", chat_id=chat_id)
            price = get_current_price()
            chart = generate_chart(tf)
            caption = (
                f"📊 *XAUUSD {tf} — Realtime*\n"
                f"💰 Price: `${price}`\n"
                f"`{get_waktu()}`"
            )
            send_telegram(caption, chart, chat_id=chat_id)

        # ─── /summary ─────────────────────────────────
        elif cmd == "/summary":
            data = fetch_data()
            if not data:
                send_telegram("❌ Gagal ambil data.", chat_id=chat_id)
                continue
            price     = round(float(data["m1"]["Close"].iloc[-1]), 2)
            manual_ch = load_manual_channel()
            ch_h4     = manual_ch if manual_ch else calc_auto_channel(data["h4"])
            ch_m30    = calc_auto_channel(data["m30"])
            bias      = get_h4_bias(ch_h4, price)
            rsi       = calc_rsi(data["m30"]["Close"])
            sr_levels = find_sr_levels(data["m30"])
            bias_emoji = "🔴 SELL ONLY" if bias == "SELL" else "🟢 BUY ONLY" if bias == "BUY" else "⏸ SKIP"
            ch_mode    = "manual" if ch_h4.get("manual") else ch_h4.get("mode", "auto")
            sr_txt     = " | ".join([f"`{lv}`" for lv in sr_levels]) if sr_levels else "`Tidak ada`"
            near_news, news_title = is_near_news(60)
            news_txt = f"⚠️ News: _{news_title}_" if near_news else "✅ Tidak ada high impact news"
            msg = (
                f"📊 *ZEXLY SUMMARY*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💰 Price: `${price}`\n"
                f"⚡ Bias: {bias_emoji}\n\n"
                f"🏗️ *H4 Channel* _{ch_mode}_\n"
                f"   Upper: `{ch_h4['upper']}` | Lower: `{ch_h4['lower']}`\n\n"
                f"📐 *M30 Channel*\n"
                f"   Upper: `{ch_m30['upper']}` | Lower: `{ch_m30['lower']}`\n\n"
                f"🎯 *S&R:* {sr_txt}\n"
                f"📈 *RSI M30:* `{rsi}`\n"
                f"{news_txt}\n"
                f"`{get_waktu()}`"
            )
            chart = generate_chart("M30")
            send_telegram(msg, chart, chat_id=chat_id)

        # ─── /status ──────────────────────────────────
        elif cmd == "/status":
            price     = get_current_price()
            ok_ses, session = get_session_status()
            manual_ch = load_manual_channel()
            ch_mode   = "manual" if manual_ch else "auto"
            pos       = load_position()
            pos_txt   = (
                f"📌 Posisi aktif: `{pos['bias']}` entry `${pos['entry']}`\n"
                f"   SL: `${pos['sl']}` | TP1: `${pos['tp1']}` | TP2: `${pos['tp2']}`"
            ) if pos and pos.get("bias") else "📌 Tidak ada posisi aktif"
            send_telegram(
                f"📊 *ZEXLY STATUS*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💰 Harga: `${price or 'N/A'}`\n"
                f"📡 Sesi: {session}\n"
                f"🟢 Trading: {'AKTIF' if ok_ses else 'OFF'}\n"
                f"🏗️ Channel: `{ch_mode}`\n"
                f"{pos_txt}\n"
                f"`{get_waktu()}`\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"`/setchannel p1 p2 p3` — set channel\n"
                f"`/delchannel` — hapus channel manual\n"
                f"`/scan` — scan manual\n"
                f"`/force` — sinyal paksa\n"
                f"`/chart [tf]` — chart (M1/M5/M15/M30/H1/H4)\n"
                f"`/summary` — ringkasan market\n"
                f"`/status` — status bot",
                chat_id=chat_id
            )

# ══════════════════════════════════════════════════════════════════
#  MAIN AUTO SCAN
# ══════════════════════════════════════════════════════════════════

def run_scan():
    log.info("═══ ZEXLY SCAN v3.0 ═══")

    # Cek command
    handle_commands()

    # Cek TP/SL hit
    price_now = get_current_price()
    if price_now:
        check_tp_sl_hit(price_now)

    # Daily summary jam 14:00 WIB
    send_daily_summary()

    # Cek jam trading
    ok_session, session_name = get_session_status()
    if not ok_session:
        log.info(f"Off-session: {session_name}. Skip scan.")
        return

    # Cek news filter
    near_news, news_title = is_near_news(30)
    if near_news:
        log.info(f"High impact news: {news_title}. Skip scan.")
        return

    # Fetch data
    data = fetch_data()
    if not data: return

    price     = round(float(data["m1"]["Close"].iloc[-1]), 2)
    manual_ch = load_manual_channel()
    ch_h4     = manual_ch if manual_ch else calc_auto_channel(data["h4"])
    ch_m30    = calc_auto_channel(data["m30"])
    bias      = get_h4_bias(ch_h4, price)

    log.info(f"Price: {price} | Bias: {bias} | Channel: {ch_h4.get('mode','?')} | Upper: {ch_h4['upper']} | Lower: {ch_h4['lower']}")

    if bias == "SKIP":
        log.info("Middle zone — SKIP")
        return

    rsi_m15    = calc_rsi(data["m30"]["Close"])
    sd_base    = detect_sd_base(data["m30"], bias)
    sr_levels  = find_sr_levels(data["m30"])
    sr_flip    = check_sr_flip_m5(data["m5"], sr_levels, bias)
    m1_trigger = detect_m1_trigger(data["m1"], bias)
    stars, star_reasons = calc_star_rating(bias, sd_base, sr_flip, m1_trigger, ch_m30, price)

    log.info(f"Stars: {stars}/4 | Base: {bool(sd_base)} | Trigger: {m1_trigger.get('type','none')}")

    if stars < 3:
        log.info(f"Bintang {stars}/4 — belum cukup. Skip.")
        return

    signal_key = f"{bias}_{round(price, -1)}_{stars}"
    if already_alerted(signal_key):
        log.info("Sinyal sama sudah dikirim. Skip.")
        return

    sl_tp   = calc_sl_tp(price, bias, sd_base, sr_levels, ch_m30)
    caption = format_signal_msg(price, bias, stars, star_reasons, sd_base,
                                m1_trigger, sr_flip, sl_tp, rsi_m15,
                                session_name, ch_h4, ch_m30)
    chart   = generate_chart("M5")

    send_telegram(caption, chart)
    mark_alerted(signal_key)
    save_position(bias, price, sl_tp["sl"], sl_tp["tp1"], sl_tp["tp2"])
    log.info(f"Sinyal {bias} {stars}★ terkirim!")


if __name__ == "__main__":
    run_scan()
