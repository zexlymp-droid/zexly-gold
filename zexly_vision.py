"""
\u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557
\u2551   ZEXLY METHOD BOT \u2014 XAUUSD AUTO SCANNER        \u2551
\u2551   Equidistant Channel + S&D + Price Action       \u2551
\u2551   Sesuai ZEMETHOD Ebook (H4 \u2192 M30 \u2192 M5 \u2192 M1)   \u2551
\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d

INSTALL DEPENDENCIES:
    pip install python-telegram-bot yfinance numpy pandas pytz playwright python-dotenv
    playwright install chromium

FILE .env (WAJIB ADA DI FOLDER YANG SAMA):
    TELEGRAM_TOKEN=isi_token_bot_lu
    TELEGRAM_CHAT_ID=isi_chat_id_lu
"""

import os, asyncio, logging, json
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf
import pytz
import requests
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

TOKEN   = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WIB     = ZoneInfo("Asia/Jakarta")

# \u2500\u2500\u2500 Interval scan (detik) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
SCAN_INTERVAL = 60   # scan tiap 1 menit

# \u2500\u2500\u2500 State anti-spam \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
STATE_FILE = "zexly_state.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("ZEXLY")

# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  UTILITAS STATE (anti-spam sinyal sama)
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def already_alerted(signal_key: str) -> bool:
    state = load_state()
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    return state.get("date") == today and state.get("key") == signal_key

def mark_alerted(signal_key: str):
    today = datetime.now(WIB).strftime("%Y-%m-%d")
    save_state({"date": today, "key": signal_key})

# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  JAM TRADING CHECK (ZEMETHOD Bab 07)
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

def get_session_status() -> tuple[bool, str]:
    """
    Returns (boleh_trading, nama_sesi)
    London Open  : 14:00\u201318:00 WIB \u2192 TERBAIK
    New York     : 20:00\u201323:00 WIB \u2192 BAIK
    NY-London OL : 19:00\u201320:00 WIB \u2192 HATI-HATI (scan tapi flag)
    Asian        : sisanya \u2192 SKIP
    """
    now_h = datetime.now(WIB).hour
    now_m = datetime.now(WIB).minute
    t = now_h * 60 + now_m

    if 14*60 <= t < 18*60:
        return True, "\ud83c\uddec\ud83c\udde7 London Open (TERBAIK)"
    elif 20*60 <= t < 23*60:
        return True, "\ud83c\uddfa\ud83c\uddf8 New York Session (BAIK)"
    elif 19*60 <= t < 20*60:
        return True, "\u26a0\ufe0f NY-London Overlap (HATI-HATI)"
    else:
        return False, "\ud83d\ude34 Asian / Off-Session (SKIP)"

# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  DATA FETCH
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

def fetch_data() -> dict | None:
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

# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  EQUIDISTANT CHANNEL (ZEMETHOD Bab 01)
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

def calc_equidistant_channel(df: pd.DataFrame) -> dict:
    """
    Equidistant channel via linear regression pada close.
    Upper = midline + 1.5*std (sepertiga atas \u2248 price > upper - std/3)
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

def get_h4_bias(ch: dict, price: float) -> str:
    """
    ZEMETHOD Bab 01 \u2014 3 Zona Channel
    Upper Zone (sepertiga atas) \u2192 SELL ONLY
    Lower Zone (sepertiga bawah) \u2192 BUY ONLY
    Middle Zone \u2192 SKIP
    """
    if price >= ch["upper_third"]:
        return "SELL"
    elif price <= ch["lower_third"]:
        return "BUY"
    else:
        return "SKIP"

# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  RSI
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

def calc_rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 1)

# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  SUPPLY & DEMAND BASE DETECTION (ZEMETHOD Bab 02)
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

def detect_sd_base(df: pd.DataFrame, bias: str) -> dict | None:
    """
    Cari pola RBR (bias BUY) atau DBD (bias SELL).
    Kriteria base valid:
      - 2\u20135 candle di base
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

            # RBR \u2192 bias BUY | DBD \u2192 bias SELL
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

# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  S&R LEVEL DETECTION (M30)
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

def find_sr_levels(df: pd.DataFrame, n_levels: int = 3) -> list[float]:
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

# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  S&R FLIP KONFIRMASI M5 (ZEMETHOD Bab 03)
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

def check_sr_flip_m5(df_m5: pd.DataFrame, sr_levels: list, bias: str) -> dict:
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

# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  CANDLE TRIGGER M1 (ZEMETHOD Bab 03 & 04)
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

def detect_m1_trigger(df_m1: pd.DataFrame, bias: str) -> dict:
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

    # \u2500\u2500\u2500 Bullish Engulfing \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
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

    # \u2500\u2500\u2500 Bearish Engulfing \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
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

# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  SISTEM BINTANG (ZEMETHOD Bab 05)
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

def calc_star_rating(bias_h4: str, sd_base: dict | None,
                     sr_flip: dict, m1_trigger: dict,
                     ch_m30: dict, price
