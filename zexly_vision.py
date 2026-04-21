"""
╔══════════════════════════════════════════════════╗
║   ZEXLY METHOD BOT — XAUUSD AUTO SCANNER        ║
║   Equidistant Channel + S&D + Price Action       ║
║   Sesuai ZEMETHOD Ebook (H4 → M30 → M5 → M1)   ║
╚══════════════════════════════════════════════════╝

INSTALL DEPENDENCIES:
    pip install python-telegram-bot yfinance numpy pandas pytz playwright python-dotenv
    playwright install chromium

FILE .env (WAJIB ADA DI FOLDER YANG SAMA):
    TELEGRAM_TOKEN=isi_token_bot_lu
    TELEGRAM_CHAT_ID=isi_chat_id_lu
"""

import os, asyncio, logging, json
from datetime import datetime, time as dtime
import pytz

import numpy as np
import pandas as pd
import yfinance as yf
import pytz
import requests
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

TOKEN   = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "-1003986432270")
WIB = pytz.timezone("Asia/Jakarta")

# ─── Interval scan (detik) ─────────────────────────────────────
SCAN_INTERVAL = 60   # scan tiap 1 menit

# ─── State anti-spam ───────────────────────────────────────────
STATE_FILE = "zexly_state.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("ZEXLY")

# ══════════════════════════════════════════════════════════════════
#  UTILITAS STATE (anti-spam sinyal sama)
# ══════════════════════════════════════════════════════════════════

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def already_alerted(signal_key: str):
    state = load_state()
    today = datetime.now(pytz.utc).astimezone(WIB).strftime("%Y-%m-%d")
    return state.get("date") == today and state.get("key") == signal_key

def mark_alerted(signal_key: str):
    today = datetime.now(pytz.utc).astimezone(WIB).strftime("%Y-%m-%d")
    save_state({"date": today, "key": signal_key})

# ══════════════════════════════════════════════════════════════════
#  JAM TRADING CHECK (ZEMETHOD Bab 07)
# ══════════════════════════════════════════════════════════════════

def get_session_status() -> tuple[bool, str]:
    """
    Returns (boleh_trading, nama_sesi)
    London Open  : 14:00–18:00 WIB → TERBAIK
    New York     : 20:00–23:00 WIB → BAIK
    NY-London OL : 19:00–20:00 WIB → HATI-HATI (scan tapi flag)
    Asian        : sisanya → SKIP
    """
    now_h = datetime.now(pytz.utc).astimezone(WIB).hour
    now_m = datetime.now(pytz.utc).astimezone(WIB).minute
    t = now_h * 60 + now_m

    if 14*60 <= t < 19*60:
        return True, "🇬🇧 London Open (TERBAIK)"
    elif 20*60 <= t < 23*60:
        return True, "🇺🇸 New York Session (BAIK)"
    elif 19*60 <= t < 20*60:
        return True, "⚠️ NY-London Overlap (HATI-HATI)"
    else:
        return False, "😴 Asian / Off-Session (SKIP)"

# ══════════════════════════════════════════════════════════════════
#  DATA FETCH
# ══════════════════════════════════════════════════════════════════

def fetch_data():
    try:
        gold = yf.Ticker("GC=F")
        df_h4  = gold.history(period="2mo",  interval="1h")   # H4 approx via 1h
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
#  EQUIDISTANT CHANNEL (ZEMETHOD Bab 01)
# ══════════════════════════════════════════════════════════════════

def calc_equidistant_channel(df: pd.DataFrame):
    """
    Equidistant channel via linear regression pada close.
    Upper = midline + 1.5*std (sepertiga atas ≈ price > upper - std/3)
    Lower = midline - 1.5*std
    """
    closes = df["Close"].values
    x = np.arange(len(closes))
    slope, intercept = np.polyfit(x, closes, 1)
    mid_vals = slope * x + intercept
    residuals = closes - mid_vals
    std = np.std(residuals)

    # Nilai channel pada candle terakhir
    last_x = len(closes) - 1
    mid   = slope * last_x + intercept
    upper = mid + 1.5 * std
    lower = mid - 1.5 * std

    # Boundary sepertiga (untuk zone check)
    upper_third = upper - (upper - lower) / 3
    lower_third = lower + (upper - lower) / 3

    return {
        "slope": slope, "intercept": intercept, "std": std,
        "mid": round(mid, 2),
        "upper": round(upper, 2),
        "lower": round(lower, 2),
        "upper_third": round(upper_third, 2),   # batas masuk Upper Zone
        "lower_third": round(lower_third, 2),   # batas masuk Lower Zone
    }

def get_h4_bias(ch: dict, price: float):
    """
    ZEMETHOD Bab 01 — 3 Zona Channel
    Upper Zone (sepertiga atas) → SELL ONLY
    Lower Zone (sepertiga bawah) → BUY ONLY
    Middle Zone → SKIP
    """
    if price >= ch["upper_third"]:
        return "SELL"
    elif price <= ch["lower_third"]:
        return "BUY"
    else:
        return "SKIP"

# ══════════════════════════════════════════════════════════════════
#  RSI
# ══════════════════════════════════════════════════════════════════

def calc_rsi(series: pd.Series, period: int = 14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 1)

# ══════════════════════════════════════════════════════════════════
#  SUPPLY & DEMAND BASE DETECTION (ZEMETHOD Bab 02)
# ══════════════════════════════════════════════════════════════════

def detect_sd_base(df: pd.DataFrame, bias: str):
    """
    Cari pola RBR (bias BUY) atau DBD (bias SELL).
    Kriteria base valid:
      - 2–5 candle di base
      - Body candle base kecil (< 50% rata-rata body sebelumnya)
      - Move sebelum base kuat (candle momentum)
      - Base lebih kecil dari move
    """
    closes = df["Close"].values
    highs  = df["High"].values
    lows   = df["Low"].values
    bodies = np.abs(df["Close"].values - df["Open"].values)
    n      = len(closes)

    if n < 15:
        return None

    # Scan dari candle -10 ke -3 (cari base yang baru terbentuk)
    for base_end in range(n - 3, n - 12, -1):
        for base_len in range(2, 6):
            base_start = base_end - base_len
            if base_start < 5:
                continue

            base_slice  = df.iloc[base_start:base_end + 1]
            base_range  = base_slice["High"].max() - base_slice["Low"].min()
            base_bodies = bodies[base_start:base_end + 1].mean()
            avg_body_before = bodies[max(0, base_start - 5):base_start].mean()

            # Syarat 1: body base kecil vs candle sebelumnya
            if avg_body_before == 0:
                continue
            if base_bodies > 0.5 * avg_body_before:
                continue

            # Move sebelum base (5 candle sebelum base_start)
            move_start = max(0, base_start - 5)
            move_slice = df.iloc[move_start:base_start]
            if len(move_slice) < 2:
                continue
            move_range = move_slice["High"].max() - move_slice["Low"].min()

            # Syarat 2: base lebih kecil dari move
            if base_range >= move_range:
                continue

            # Syarat 3: move kuat (rata-rata body move > avg body keseluruhan)
            move_bodies = bodies[move_start:base_start].mean()
            overall_avg = bodies.mean()
            if move_bodies < overall_avg:
                continue

            # Arah move sebelum base
            move_dir = "UP" if move_slice["Close"].iloc[-1] > move_slice["Close"].iloc[0] else "DOWN"

            # RBR → bias BUY | DBD → bias SELL
            if bias == "BUY"  and move_dir != "UP":   continue
            if bias == "SELL" and move_dir != "DOWN":  continue

            base_high = round(base_slice["High"].max(), 2)
            base_low  = round(base_slice["Low"].min(), 2)

            return {
                "found": True,
                "type": "RBR" if bias == "BUY" else "DBD",
                "base_high": base_high,
                "base_low":  base_low,
                "base_mid":  round((base_high + base_low) / 2, 2),
                "base_range": round(base_range, 2),
                "candles_in_base": base_len,
                "base_start_idx": base_start,
                "base_end_idx":   base_end,
            }

    return None

# ══════════════════════════════════════════════════════════════════
#  S&R LEVEL DETECTION (M30)
# ══════════════════════════════════════════════════════════════════

def find_sr_levels(df: pd.DataFrame, n_levels: int = 3):
    """
    Cari max 3 level S&R terkuat dari swing high/low M30.
    """
    highs = df["High"].values
    lows  = df["Low"].values
    levels = []

    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
           highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            levels.append(round(highs[i], 2))
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
           lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            levels.append(round(lows[i], 2))

    if not levels:
        return []

    # Cluster level yang berdekatan (dalam 5 pips)
    levels.sort()
    clustered = [levels[0]]
    for lv in levels[1:]:
        if lv - clustered[-1] > 5:
            clustered.append(lv)

    # Ambil 3 terdekat dari harga saat ini
    price = df["Close"].iloc[-1]
    clustered.sort(key=lambda x: abs(x - price))
    return clustered[:n_levels]

# ══════════════════════════════════════════════════════════════════
#  S&R FLIP KONFIRMASI M5 (ZEMETHOD Bab 03)
# ══════════════════════════════════════════════════════════════════

def check_sr_flip_m5(df_m5: pd.DataFrame, sr_levels: list, bias: str):
    """
    Cek apakah candle M5 terakhir sudah close melewati S&R level
    dan harga sedang retest level tersebut.
    """
    if not sr_levels:
        return {"confirmed": False}

    last_close = df_m5["Close"].iloc[-1]
    prev_close = df_m5["Close"].iloc[-2]

    for level in sr_levels:
        # BUY flip: close sebelumnya di bawah level, close sekarang di atas
        if bias == "BUY":
            if prev_close < level and last_close > level:
                return {
                    "confirmed": True,
                    "flip_type": "SUPPORT BARU",
                    "flip_level": level,
                    "detail": f"M5 close {last_close:.2f} tembus ATAS {level:.2f}"
                }
        # SELL flip: close sebelumnya di atas level, close sekarang di bawah
        elif bias == "SELL":
            if prev_close > level and last_close < level:
                return {
                    "confirmed": True,
                    "flip_type": "RESISTANCE BARU",
                    "flip_level": level,
                    "detail": f"M5 close {last_close:.2f} tembus BAWAH {level:.2f}"
                }

    return {"confirmed": False}

# ══════════════════════════════════════════════════════════════════
#  CANDLE TRIGGER M1 (ZEMETHOD Bab 03 & 04)
# ══════════════════════════════════════════════════════════════════

def detect_m1_trigger(df_m1: pd.DataFrame, bias: str):
    """
    Deteksi Engulfing atau Pin Bar di M1 (candle terakhir yang sudah close).
    Gunakan candle index -2 (sudah close), bukan -1 (masih berjalan).
    """
    if len(df_m1) < 3:
        return {"found": False}

    # Candle yang sudah close = index -2
    c1 = df_m1.iloc[-2]  # trigger candle (sudah close)
    c0 = df_m1.iloc[-3]  # candle sebelumnya

    o1, c1_close = c1["Open"], c1["Close"]
    h1, l1       = c1["High"], c1["Low"]
    o0, c0_close = c0["Open"], c0["Close"]

    body1  = abs(c1_close - o1)
    range1 = h1 - l1
    body0  = abs(c0_close - o0)

    if range1 == 0:
        return {"found": False}

    # ─── Bullish Engulfing ─────────────────────────
    if bias == "BUY":
        is_engulfing = (
            c1_close > o1 and          # candle hijau
            c0_close < o0 and          # candle sebelumnya merah
            o1 <= c0_close and         # open di bawah close sebelumnya
            c1_close >= o0             # close di atas open sebelumnya
        )
        upper_shadow = h1 - max(o1, c1_close)
        lower_shadow = min(o1, c1_close) - l1
        is_pin_bar = (
            c1_close > o1 and
            lower_shadow >= 2 * body1 and
            upper_shadow <= 0.3 * range1
        )
        if is_engulfing:
            return {"found": True, "type": "Bullish Engulfing", "strength": "KUAT" if body1 > body0 else "SEDANG"}
        if is_pin_bar:
            return {"found": True, "type": "Bullish Pin Bar", "strength": "KUAT"}

    # ─── Bearish Engulfing ─────────────────────────
    elif bias == "SELL":
        is_engulfing = (
            c1_close < o1 and
            c0_close > o0 and
            o1 >= c0_close and
            c1_close <= o0
        )
        upper_shadow = h1 - max(o1, c1_close)
        lower_shadow = min(o1, c1_close) - l1
        is_pin_bar = (
            c1_close < o1 and
            upper_shadow >= 2 * body1 and
            lower_shadow <= 0.3 * range1
        )
        if is_engulfing:
            return {"found": True, "type": "Bearish Engulfing", "strength": "KUAT" if body1 > body0 else "SEDANG"}
        if is_pin_bar:
            return {"found": True, "type": "Bearish Pin Bar", "strength": "KUAT"}

    return {"found": False}

# ══════════════════════════════════════════════════════════════════
#  SISTEM BINTANG (ZEMETHOD Bab 05)
# ══════════════════════════════════════════════════════════════════

def calc_star_rating(bias_h4: str, sd_base,
                     sr_flip: dict, m1_trigger: dict,
                     ch_m30: dict, price: float):
    """
    4 kriteria bintang ZEMETHOD:
    ★1 — Searah bias H4
    ★2 — Base valid di level S&R M30
    ★3 — Candle M5 konfirmasi
    ★4 — Candle trigger M1 jelas
    """
    stars = 0
    reasons = []

    # Bintang 1 — Bias H4
    # (selalu 1 karena kita sudah filter bias SKIP di awal)
    stars += 1
    reasons.append(f"★ Setup searah bias H4 ({bias_h4})")

    # Bintang 2 — Base di level S&R atau tepi channel
    base_near_sr = False
    if sd_base and sd_base.get("found"):
        # Cek apakah base dekat tepi channel (upper/lower zone)
        if bias_h4 == "BUY"  and abs(sd_base["base_low"] - ch_m30["lower"]) < 15:
            base_near_sr = True
        elif bias_h4 == "SELL" and abs(sd_base["base_high"] - ch_m30["upper"]) < 15:
            base_near_sr = True
        if base_near_sr or sd_base.get("found"):
            stars += 1
            reasons.append(f"★ Pola {sd_base['type']} valid ({sd_base['candles_in_base']} candle di base)")

    # Bintang 3 — M5 konfirmasi (S&R flip atau price di zona channel)
    if sr_flip.get("confirmed"):
        stars += 1
        reasons.append(f"★ M5 konfirmasi: {sr_flip['detail']}")
    elif sd_base and sd_base.get("found"):
        # Alternatif: harga sudah di dalam zona base
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
#  SL / TP KALKULASI (ZEMETHOD Bab 06)
# ══════════════════════════════════════════════════════════════════

def calc_sl_tp(price: float, bias: str, sd_base,
               sr_levels: list, ch_m30: dict):
    """
    SL: di luar base + 5-7 pips buffer (total ~10-15 pips dari entry)
    TP1: S&R berikutnya
    TP2: Tepi channel M30 seberang
    RR minimum 1:1.5
    """
    buffer = 7.0  # pips

    if bias == "BUY":
        sl_base = sd_base["base_low"] if sd_base and sd_base.get("found") else price - 15
        sl = round(sl_base - buffer, 2)
        risk = abs(price - sl)

        # TP1: level S&R di atas harga
        tp1_candidates = [lv for lv in sr_levels if lv > price]
        tp1 = round(min(tp1_candidates), 2) if tp1_candidates else round(price + risk * 1.5, 2)

        # TP2: upper channel M30
        tp2 = round(ch_m30["upper"], 2)

    else:  # SELL
        sl_base = sd_base["base_high"] if sd_base and sd_base.get("found") else price + 15
        sl = round(sl_base + buffer, 2)
        risk = abs(sl - price)

        tp1_candidates = [lv for lv in sr_levels if lv < price]
        tp1 = round(max(tp1_candidates), 2) if tp1_candidates else round(price - risk * 1.5, 2)

        tp2 = round(ch_m30["lower"], 2)

    rr1 = round(abs(tp1 - price) / risk, 2) if risk > 0 else 0
    rr2 = round(abs(tp2 - price) / risk, 2) if risk > 0 else 0

    return {
        "sl": sl, "tp1": tp1, "tp2": tp2,
        "risk_pips": round(risk, 1),
        "rr1": rr1, "rr2": rr2
    }

# ══════════════════════════════════════════════════════════════════
#  GENERATE CHART MATPLOTLIB (ZEMETHOD ANNOTATED)
# ══════════════════════════════════════════════════════════════════

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

async def take_tv_screenshot(interval: str = "5", context: dict = None):
    """
    Generate chart XAUUSD dengan anotasi ZEMETHOD:
    - Equidistant Channel H4
    - S&D Base zone
    - S&R levels
    - Entry area highlight
    - Harga sekarang
    """
    path = "zexly_chart_annotated.png"
    try:
        gold = yf.Ticker("GC=F")
        # Pakai M30 untuk chart utama
        df = gold.history(period="5d", interval="30m")
        df.dropna(inplace=True)

        if df.empty:
            return None

        # Ambil context dari parameter (channel, base, sr, price, bias)
        ch_h4   = context.get("ch_h4")   if context else None
        ch_m30  = context.get("ch_m30")  if context else None
        sd_base = context.get("sd_base") if context else None
        sr_lvls = context.get("sr_lvls") if context else []
        price   = context.get("price")   if context else float(df["Close"].iloc[-1])
        bias    = context.get("bias")    if context else "SKIP"
        stars   = context.get("stars")   if context else 0

        closes = df["Close"].values
        highs  = df["High"].values
        lows   = df["Low"].values
        x      = np.arange(len(closes))

        # ─── Setup Figure ───────────────────────────────
        fig, ax = plt.subplots(figsize=(14, 7), facecolor="#131722")
        ax.set_facecolor("#131722")

        # ─── Candlestick (simplified: bar chart) ────────
        for i in range(len(closes)):
            color = "#26a69a" if closes[i] >= df["Open"].values[i] else "#ef5350"
            ax.plot([i, i], [lows[i], highs[i]], color=color, linewidth=0.8, alpha=0.7)
            body_bot = min(closes[i], df["Open"].values[i])
            body_top = max(closes[i], df["Open"].values[i])
            ax.bar(i, body_top - body_bot, bottom=body_bot,
                   color=color, width=0.6, alpha=0.9)

        # ─── Channel H4 ─────────────────────────────────
        if ch_h4:
            ax.axhline(ch_h4["upper"], color="#FF4C4C", linewidth=1.5,
                       linestyle="-", label=f"H4 Upper {ch_h4['upper']}", zorder=3)
            ax.axhline(ch_h4["mid"],   color="#ffffff", linewidth=1,
                       linestyle="--", alpha=0.5, label=f"H4 Mid {ch_h4['mid']}", zorder=3)
            ax.axhline(ch_h4["lower"], color="#00C853", linewidth=1.5,
                       linestyle="-", label=f"H4 Lower {ch_h4['lower']}", zorder=3)
            ax.axhline(ch_h4["upper_third"], color="#FF4C4C", linewidth=0.8,
                       linestyle=":", alpha=0.5, label="Upper Zone Boundary")
            ax.axhline(ch_h4["lower_third"], color="#00C853", linewidth=0.8,
                       linestyle=":", alpha=0.5, label="Lower Zone Boundary")
            # Fill zones
            ymin, ymax = ax.get_ylim()
            ax.axhspan(ch_h4["upper_third"], ch_h4["upper"],
                       alpha=0.06, color="red", zorder=1)
            ax.axhspan(ch_h4["lower"], ch_h4["lower_third"],
                       alpha=0.06, color="green", zorder=1)

        # ─── M30 Channel ────────────────────────────────
        if ch_m30:
            ax.axhline(ch_m30["upper"], color="#FF8C00", linewidth=1,
                       linestyle="-.", alpha=0.7, label=f"M30 Upper {ch_m30['upper']}")
            ax.axhline(ch_m30["lower"], color="#1E90FF", linewidth=1,
                       linestyle="-.", alpha=0.7, label=f"M30 Lower {ch_m30['lower']}")

        # ─── S&D Base Zone ───────────────────────────────
        if sd_base and sd_base.get("found"):
            base_color = "#00C853" if bias == "BUY" else "#FF4C4C"
            ax.axhspan(sd_base["base_low"], sd_base["base_high"],
                       alpha=0.15, color=base_color, zorder=2)
            ax.axhline(sd_base["base_high"], color=base_color,
                       linewidth=1, linestyle="--", alpha=0.8)
            ax.axhline(sd_base["base_low"], color=base_color,
                       linewidth=1, linestyle="--", alpha=0.8)
            mid_x = len(closes) - 5
            ax.text(mid_x, sd_base["base_mid"],
                    f"  {sd_base['type']} ZONE", color=base_color,
                    fontsize=8, fontweight="bold", va="center")

        # ─── S&R Levels ──────────────────────────────────
        for lvl in sr_lvls:
            ax.axhline(lvl, color="#FFD700", linewidth=0.8,
                       linestyle=":", alpha=0.7)
            ax.text(len(closes) - 1, lvl, f" S&R {lvl}",
                    color="#FFD700", fontsize=7, va="bottom")

        # ─── Harga Sekarang ──────────────────────────────
        ax.axhline(price, color="#FFD700", linewidth=2,
                   linestyle="-", zorder=5, label=f"Price ${price}")
        ax.text(len(closes) - 1, price, f" ${price}",
                color="#FFD700", fontsize=9, fontweight="bold", va="bottom")

        # ─── Entry Arrow ─────────────────────────────────
        if bias in ("BUY", "SELL") and stars >= 3:
            arrow_y = price
            dy = 15 if bias == "BUY" else -15
            arrow_color = "#00C853" if bias == "BUY" else "#FF4C4C"
            direction = "▲ BUY" if bias == "BUY" else "▼ SELL"
            ax.annotate(
                f"  {direction}\n  {stars}★",
                xy=(len(closes) - 3, arrow_y),
                xytext=(len(closes) - 8, arrow_y + dy * 2),
                arrowprops=dict(arrowstyle="->", color=arrow_color, lw=2),
                color=arrow_color, fontsize=10, fontweight="bold"
            )

        # ─── Labels & Title ──────────────────────────────
        bias_emoji = {"BUY": "🟢 BUY", "SELL": "🔴 SELL", "SKIP": "⏸ SKIP"}.get(bias, bias)
        stars_str  = "★" * stars + "☆" * (4 - stars)
        waktu      = datetime.now(pytz.utc).astimezone(WIB).strftime("%d %b %Y %H:%M WIB")

        ax.set_title(
            f"ZEXLY METHOD — XAUUSD M30  |  Bias: {bias}  |  {stars_str} ({stars}/4)  |  {waktu}",
            color="white", fontsize=11, fontweight="bold", pad=10
        )
        ax.tick_params(colors="#aaaaaa")
        for spine in ax.spines.values():
            spine.set_color("#333333")
        ax.set_ylabel("Price (USD)", color="#aaaaaa", fontsize=9)
        ax.set_xlabel("Candle M30", color="#aaaaaa", fontsize=9)

        # Legend
        legend_elements = [
            Line2D([0], [0], color="#FF4C4C", lw=1.5, label=f"H4 Upper {ch_h4['upper'] if ch_h4 else ''}"),
            Line2D([0], [0], color="#00C853", lw=1.5, label=f"H4 Lower {ch_h4['lower'] if ch_h4 else ''}"),
            Line2D([0], [0], color="#FF8C00", lw=1, linestyle="-.", label=f"M30 Upper {ch_m30['upper'] if ch_m30 else ''}"),
            Line2D([0], [0], color="#1E90FF", lw=1, linestyle="-.", label=f"M30 Lower {ch_m30['lower'] if ch_m30 else ''}"),
            Line2D([0], [0], color="#FFD700", lw=2, label=f"Price ${price}"),
        ]
        ax.legend(handles=legend_elements, loc="upper left",
                  fontsize=7, facecolor="#1e222d",
                  labelcolor="white", framealpha=0.8)

        plt.tight_layout()
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        log.info(f"Chart annotated tersimpan: {path}")
        return path

    except Exception as e:
        log.error(f"Chart error: {e}")
        return None

# ══════════════════════════════════════════════════════════════════
#  KIRIM TELEGRAM
# ══════════════════════════════════════════════════════════════════

def send_telegram(caption: str, photo_path: str = None):
    base = f"https://api.telegram.org/bot{TOKEN}"
    try:
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, "rb") as ph:
                resp = requests.post(
                    f"{base}/sendPhoto",
                    data={"chat_id": CHAT_ID, "caption": caption,
                          "parse_mode": "Markdown"},
                    files={"photo": ph},
                    timeout=20
                )
        else:
            resp = requests.post(
                f"{base}/sendMessage",
                data={"chat_id": CHAT_ID, "text": caption,
                      "parse_mode": "Markdown"},
                timeout=20
            )
        resp.raise_for_status()
        log.info("Pesan terkirim ke Telegram ✓")
    except Exception as e:
        log.error(f"Telegram error: {e}")

def send_startup_msg():
    waktu = datetime.now(pytz.utc).astimezone(WIB).strftime("%d %b %Y | %H:%M WIB")
    msg = (
        f"🦅 *ZEXLY METHOD BOT — AKTIF*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ Bot berhasil dinyalakan\n"
        f"🕒 `{waktu}`\n"
        f"⏱ Scan tiap `{SCAN_INTERVAL}` detik\n"
        f"📊 Instrument: `XAUUSD`\n"
        f"🔍 Metode: Equidistant Channel + S&D + PA\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Bot akan scan otomatis selama jam London & New York (WIB).\n"
        f"Sinyal dikirim jika minimal *3/4 bintang* ZEMETHOD terpenuhi."
    )
    send_telegram(msg)

# ══════════════════════════════════════════════════════════════════
#  FORMAT PESAN SINYAL
# ══════════════════════════════════════════════════════════════════

def format_signal_msg(
    price: float, bias: str, stars: int, star_reasons: list,
    sd_base, m1_trigger: dict, sr_flip: dict,
    sl_tp, rsi_m15, session,
    ch_h4, ch_m30
):

    emoji_bias = "🔴 SELL" if bias == "SELL" else "🟢 BUY"
    stars_display = "★" * stars + "☆" * (4 - stars)
    waktu = datetime.now(pytz.utc).astimezone(WIB).strftime("%d %b %Y | %H:%M WIB")

    trigger_txt = f"`{m1_trigger['type']} ({m1_trigger['strength']})`" \
                  if m1_trigger.get("found") else "`Belum muncul`"

    flip_txt = f"`{sr_flip['detail']}`" if sr_flip.get("confirmed") else "`Belum flip`"

    base_txt = (
        f"`{sd_base['type']} — {sd_base['candles_in_base']} candle`\n"
        f"   Zone: `{sd_base['base_low']} – {sd_base['base_high']}`"
    ) if sd_base and sd_base.get("found") else "`Tidak terdeteksi`"

    rsi_label = (
        "⚠️ Overbought" if rsi_m15 >= 70 else
        "🔶 Near OB"    if rsi_m15 >= 65 else
        "⚠️ Oversold"   if rsi_m15 <= 30 else
        "🔷 Near OS"    if rsi_m15 <= 35 else
        "➖ Netral"
    )

    reasons_str = "\n".join([f"  {r}" for r in star_reasons])

    msg = (
        f"🦅 *ZEXLY METHOD — SINYAL ENTRY*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📍 *Instrument:* `XAUUSD`\n"
        f"💰 *Price:* `${price}`\n"
        f"⚡ *Signal:* {emoji_bias}\n"
        f"⭐ *Kualitas:* `{stars_display}` ({stars}/4 bintang)\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 *ANALISA ZEMETHOD*\n\n"
        f"🏗️ *H4 Equidistant Channel*\n"
        f"   Upper: `{ch_h4['upper']}` | Mid: `{ch_h4['mid']}` | Lower: `{ch_h4['lower']}`\n"
        f"   Bias: *{bias} ONLY*\n\n"
        f"📐 *M30 Channel*\n"
        f"   Upper: `{ch_m30['upper']}` | Lower: `{ch_m30['lower']}`\n\n"
        f"🎯 *S&D Base (M30)*\n"
        f"   {base_txt}\n\n"
        f"🔀 *S&R Flip M5*\n"
        f"   {flip_txt}\n\n"
        f"🕯️ *Trigger M1*\n"
        f"   {trigger_txt}\n\n"
        f"📈 *RSI M15:* `{rsi_m15}` — {rsi_label}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💼 *RENCANA TRADE*\n\n"
        f"   Entry  : `${price}`\n"
        f"   SL     : `${sl_tp['sl']}` ({sl_tp['risk_pips']} pips)\n"
        f"   TP1    : `${sl_tp['tp1']}` (RR {sl_tp['rr1']}:1) → tutup 70%\n"
        f"   TP2    : `${sl_tp['tp2']}` (RR {sl_tp['rr2']}:1) → sisa 30% (risk-free)\n\n"
        f"   Setelah TP1 hit → geser SL ke breakeven!\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ *ALASAN ENTRY*\n"
        f"{reasons_str}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏰ *Next Step:* Konfirmasi visual M1 sebelum klik entry!\n"
        f"🕒 `{waktu}`\n"
        f"📡 `{session}`"
    )
    return msg

# ══════════════════════════════════════════════════════════════════
#  MAIN SCAN LOOP
# ══════════════════════════════════════════════════════════════════

async def run_scan():
    log.info("═══ ZEXLY SCAN ═══")

    # 1. Cek jam trading (ZEMETHOD Bab 07)
    ok_session, session_name = get_session_status()
    if not ok_session:
        log.info(f"Off-session: {session_name}. Skip scan.")
        return

    # 2. Ambil data
    data = fetch_data()
    if not data:
        return
    df_h4, df_m30 = data["h4"], data["m30"]
    df_m5, df_m1  = data["m5"], data["m1"]

    price = round(float(df_m1["Close"].iloc[-1]), 2)

    # 3. H4 Channel & Bias (Bab 01)
    ch_h4  = calc_equidistant_channel(df_h4)
    ch_m30 = calc_equidistant_channel(df_m30)
    bias   = get_h4_bias(ch_h4, price)

    log.info(f"Price: {price} | H4 Bias: {bias} | "
             f"Upper: {ch_h4['upper']} | Lower: {ch_h4['lower']}")

    if bias == "SKIP":
        log.info("Middle zone — SKIP (ZEMETHOD Bab 01: tidak trading di middle zone)")

    # 4. RSI M15
    rsi_m15 = calc_rsi(df_m30["Close"])

    # 5. S&D Base (Bab 02)
    sd_base = detect_sd_base(df_m30, bias)

    # 6. S&R Levels & Flip M5 (Bab 03)
    sr_levels = find_sr_levels(df_m30)
    sr_flip   = check_sr_flip_m5(df_m5, sr_levels, bias)

    # 7. Trigger M1 (Bab 04)
    m1_trigger = detect_m1_trigger(df_m1, bias)

    # 8. Sistem Bintang (Bab 05)
    stars, star_reasons = calc_star_rating(
        bias, sd_base, sr_flip, m1_trigger, ch_m30, price
    )

    log.info(f"Stars: {stars}/4 | Base: {sd_base} | Trigger: {m1_trigger}")

    # 9. Minimal 3/4 bintang untuk entry (ZEMETHOD Bab 05)
    if stars < 3:
        log.info(f"Bintang {stars}/4 — belum cukup untuk entry. Skip alert.")
        return

    # 10. Anti-spam: cek apakah sinyal ini sudah dikirim
    signal_key = f"{bias}_{round(price, 0)}_{stars}"
    if already_alerted(signal_key):
        log.info("Sinyal sama sudah dikirim. Skip.")

    # 11. SL/TP (Bab 06)
    sl_tp = calc_sl_tp(price, bias, sd_base, sr_levels, ch_m30)


    # 12. Format pesan
    caption = format_signal_msg(
        price, bias, stars, star_reasons,
        sd_base, m1_trigger, sr_flip,
        sl_tp, rsi_m15, session_name,
        ch_h4, ch_m30
    )

    # 13. Screenshot TradingView M5
    log.info("Ambil screenshot TradingView...")
    screenshot = await take_tv_screenshot(interval="5", context={
        "ch_h4": ch_h4, "ch_m30": ch_m30,
        "sd_base": sd_base, "sr_lvls": sr_levels,
        "price": price, "bias": bias, "stars": stars
    })

    # 14. Kirim ke Telegram
    send_telegram(caption, screenshot)
    mark_alerted(signal_key)
    log.info(f"✅ Sinyal {bias} {stars}★ terkirim!")

if __name__ == "__main__":
    asyncio.run(run_scan())
