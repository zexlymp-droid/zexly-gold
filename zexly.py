"""
╔══════════════════════════════════════════════════════════╗
║   ZEXLY COMMAND BOT — Telegram Polling                  ║
║   Deploy ke Railway.app                                  ║
║   Commands:                                              ║
║   /start    — menu utama                                ║
║   /scan     — scan manual                               ║
║   /force    — sinyal paksa                              ║
║   /chart    — chart realtime                            ║
║   /status   — status bot                                ║
║   /summary  — ringkasan market                          ║
║   /setchannel p1 p2 p3 — set channel manual            ║
║   /delchannel — hapus channel manual                    ║
╚══════════════════════════════════════════════════════════╝
"""

import os, logging, json, asyncio
from datetime import datetime
import pytz
import numpy as np
import pandas as pd
import yfinance as yf
import requests
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

load_dotenv()

TOKEN        = os.getenv("TELEGRAM_TOKEN")
CHAT_ID      = os.getenv("TELEGRAM_CHAT_ID", "")
BROADCAST_IDS = ["-1003986432270", "8706271896"]
CHARTIMG_KEY = os.getenv("CHARTIMG_KEY", "")
TWELVEDATA_KEY = os.getenv("TWELVEDATA_KEY", "")
ZEXLY_CH_ENV = os.getenv("ZEXLY_CHANNEL", "")
WIB          = pytz.timezone("Asia/Jakarta")

CHANNEL_FILE  = "zexly_channel.json"
POSITION_FILE = "zexly_position.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("ZEXLY-CMD")

# ══════════════════════════════════════════════════════════════════
#  UTILS
# ══════════════════════════════════════════════════════════════════

def load_json(path, default=None):
    try:
        with open(path) as f: return json.load(f)
    except Exception: return default if default is not None else {}

def save_json(path, data):
    with open(path, "w") as f: json.dump(data, f)

def get_waktu():
    return datetime.now(WIB).strftime("%d %b %Y | %H:%M WIB")

def get_session_status():
    now = datetime.now(WIB)
    t   = now.hour * 60 + now.minute
    if 14*60 <= t < 18*60:   return True,  "London Open (TERBAIK)"
    elif 18*60 <= t < 20*60: return False, "NY-London Overlap (HINDARI)"
    elif 20*60 <= t < 23*60: return True,  "New York Session (BAIK)"
    elif 3*60  <= t < 11*60: return False, "Asian Session (HINDARI)"
    else:                     return False, "Off-Session"

# ══════════════════════════════════════════════════════════════════
#  CHANNEL
# ══════════════════════════════════════════════════════════════════

def calc_channel_from_3points(p1, p2, p3):
    pts = sorted([p1, p2, p3], reverse=True)
    high1, mid_pt, low1 = pts
    diff_top = abs(high1 - mid_pt)
    diff_bot = abs(mid_pt - low1)
    if diff_top < diff_bot:
        upper, lower, mode = (high1 + mid_pt) / 2, low1, "2H+1L"
    else:
        upper, lower, mode = high1, (mid_pt + low1) / 2, "1H+2L"
    ch_h = upper - lower
    return {
        "upper": round(upper, 2), "lower": round(lower, 2),
        "mid": round((upper+lower)/2, 2),
        "upper_third": round(upper - ch_h/3, 2),
        "lower_third": round(lower + ch_h/3, 2),
        "slope": 0, "std": round(ch_h/3, 2),
        "mode": mode, "manual": True, "points": [p1, p2, p3]
    }

def load_manual_channel():
    if ZEXLY_CH_ENV:
        try:
            parts = [float(x) for x in ZEXLY_CH_ENV.split(",")]
            if len(parts) == 3:
                return calc_channel_from_3points(*parts)
        except Exception: pass
    data = load_json(CHANNEL_FILE)
    return data if data else None

def save_manual_channel(data):
    save_json(CHANNEL_FILE, data)

def delete_manual_channel():
    try: os.remove(CHANNEL_FILE)
    except Exception: pass

# ══════════════════════════════════════════════════════════════════
#  DATA & ANALISA
# ══════════════════════════════════════════════════════════════════

def _td_fetch(interval, outputsize=150):
    """Ambil OHLCV dari Twelve Data — realtime"""
    try:
        resp = requests.get(
            "https://api.twelvedata.com/time_series",
            params={
                "symbol": "XAU/USD",
                "interval": interval,
                "outputsize": outputsize,
                "apikey": TWELVEDATA_KEY,
                "format": "JSON",
                "timezone": "UTC"
            }, timeout=15
        )
        data = resp.json()
        if "values" not in data:
            log.error(f"Twelve Data error ({interval}): {data.get('message','unknown')}")
            return None
        rows = data["values"]
        df = pd.DataFrame(rows)
        df = df.rename(columns={
            "datetime": "Datetime",
            "open": "Open", "high": "High",
            "low": "Low", "close": "Close",
            "volume": "Volume"
        })
        df["Datetime"] = pd.to_datetime(df["Datetime"])
        df = df.set_index("Datetime").sort_index()
        for col in ["Open","High","Low","Close"]:
            df[col] = df[col].astype(float)
        df["Volume"] = df.get("Volume", pd.Series([0]*len(df))).astype(float)
        df.dropna(inplace=True)
        return df
    except Exception as e:
        log.error(f"Twelve Data fetch error ({interval}): {e}")
        return None

def fetch_data():
    try:
        df_h4  = _td_fetch("4h",  outputsize=120)
        df_m30 = _td_fetch("30min", outputsize=150)
        df_m5  = _td_fetch("5min",  outputsize=150)
        df_m1  = _td_fetch("1min",  outputsize=100)
        for label, df in [("H4",df_h4),("M30",df_m30),("M5",df_m5),("M1",df_m1)]:
            if df is None or df.empty:
                log.warning(f"Data {label} kosong")
                return None
        return {"h4": df_h4, "m30": df_m30, "m5": df_m5, "m1": df_m1}
    except Exception as e:
        log.error(f"Gagal fetch: {e}")
        return None

def get_current_price():
    try:
        df = _td_fetch("1min", outputsize=1)
        if df is not None and not df.empty:
            return round(float(df["Close"].iloc[-1]), 2)
        return None
    except Exception: return None

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
    closes = df["Close"].values
    highs_arr = df["High"].values
    lows_arr  = df["Low"].values
    n = len(closes)
    last_x = n - 1

    swing_highs, _ = find_swings(highs_arr, order=5)
    _, swing_lows  = find_swings(lows_arr, order=5)

    def line_at(x, x1, y1, slope):
        return y1 + slope * (x - x1)

    if len(swing_highs) >= 2 and len(swing_lows) >= 1:
        sh1, sh2 = swing_highs[-2], swing_highs[-1]
        slope = (sh2[1] - sh1[1]) / (sh2[0] - sh1[0]) if sh2[0] != sh1[0] else 0
        upper_end = line_at(last_x, sh1[0], sh1[1], slope)
        xl, yl = swing_lows[-1]
        lower_end = slope * last_x + (yl - slope * xl)
        ch_h = upper_end - lower_end
        if ch_h > 20:
            return {
                "slope": slope, "upper": round(upper_end, 2),
                "lower": round(lower_end, 2),
                "mid": round((upper_end+lower_end)/2, 2),
                "upper_third": round(upper_end - ch_h/3, 2),
                "lower_third": round(lower_end + ch_h/3, 2),
                "std": round(ch_h/3, 2), "mode": "auto_2H1L", "manual": False
            }

    if len(swing_lows) >= 2 and len(swing_highs) >= 1:
        sl1, sl2 = swing_lows[-2], swing_lows[-1]
        slope = (sl2[1] - sl1[1]) / (sl2[0] - sl1[0]) if sl2[0] != sl1[0] else 0
        lower_end = line_at(last_x, sl1[0], sl1[1], slope)
        xh, yh = swing_highs[-1]
        upper_end = slope * last_x + (yh - slope * xh)
        ch_h = upper_end - lower_end
        if ch_h > 20:
            return {
                "slope": slope, "upper": round(upper_end, 2),
                "lower": round(lower_end, 2),
                "mid": round((upper_end+lower_end)/2, 2),
                "upper_third": round(upper_end - ch_h/3, 2),
                "lower_third": round(lower_end + ch_h/3, 2),
                "std": round(ch_h/3, 2), "mode": "auto_2L1H", "manual": False
            }

    x = np.arange(n)
    slope, intercept = np.polyfit(x, closes, 1)
    std = np.std(closes - (slope * x + intercept))
    mid = slope * last_x + intercept
    upper, lower = mid + 1.5*std, mid - 1.5*std
    return {
        "slope": slope, "upper": round(upper, 2), "lower": round(lower, 2),
        "mid": round(mid, 2), "upper_third": round(upper - (upper-lower)/3, 2),
        "lower_third": round(lower + (upper-lower)/3, 2),
        "std": round(std, 2), "mode": "regression", "manual": False
    }

def get_h4_bias(ch, price):
    if price >= ch["upper_third"]: return "SELL"
    elif price <= ch["lower_third"]: return "BUY"
    return "SKIP"

def calc_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return round(float((100 - (100/(1+rs))).iloc[-1]), 1)

def detect_sd_base(df, bias):
    bodies = np.abs(df["Close"].values - df["Open"].values)
    n = len(df)
    if n < 15: return None
    for base_end in range(n-2, n-15, -1):
        for base_len in range(2, 7):
            base_start = base_end - base_len
            if base_start < 5: continue
            base_slice  = df.iloc[base_start:base_end+1]
            base_range  = base_slice["High"].max() - base_slice["Low"].min()
            base_bodies = bodies[base_start:base_end+1].mean()
            avg_before  = bodies[max(0,base_start-5):base_start].mean()
            if avg_before == 0 or base_bodies > 0.6*avg_before: continue
            move_start  = max(0, base_start-6)
            move_slice  = df.iloc[move_start:base_start]
            if len(move_slice) < 2: continue
            move_range  = move_slice["High"].max() - move_slice["Low"].min()
            if base_range >= move_range*0.8: continue
            if bodies[move_start:base_start].mean() < bodies.mean()*0.8: continue
            move_dir = "UP" if move_slice["Close"].iloc[-1] > move_slice["Close"].iloc[0] else "DOWN"
            if bias == "BUY" and move_dir != "UP": continue
            if bias == "SELL" and move_dir != "DOWN": continue
            return {
                "found": True,
                "type": "RBR" if bias == "BUY" else "DBD",
                "base_high": round(base_slice["High"].max(), 2),
                "base_low":  round(base_slice["Low"].min(), 2),
                "base_mid":  round((base_slice["High"].max()+base_slice["Low"].min())/2, 2),
                "candles_in_base": base_len,
            }
    return None

def find_sr_levels(df, min_distance=15):
    highs, lows = df["High"].values, df["Low"].values
    price = float(df["Close"].iloc[-1])
    levels = []
    for i in range(2, len(highs)-2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
           highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            if abs(highs[i]-price) >= min_distance: levels.append(round(highs[i],2))
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
           lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            if abs(lows[i]-price) >= min_distance: levels.append(round(lows[i],2))
    if not levels: return []
    levels.sort()
    clustered = [levels[0]]
    for lv in levels[1:]:
        if lv - clustered[-1] > 5: clustered.append(lv)
    clustered.sort(key=lambda x: abs(x-price))
    return clustered[:3]

def check_sr_flip_m5(df_m5, sr_levels, bias):
    if not sr_levels: return {"confirmed": False}
    last_close = df_m5["Close"].iloc[-1]
    prev_close = df_m5["Close"].iloc[-2]
    for level in sr_levels:
        if bias == "BUY" and prev_close < level and last_close > level:
            return {"confirmed": True, "detail": f"M5 close {last_close:.2f} tembus ATAS {level:.2f}"}
        if bias == "SELL" and prev_close > level and last_close < level:
            return {"confirmed": True, "detail": f"M5 close {last_close:.2f} tembus BAWAH {level:.2f}"}
    return {"confirmed": False}

def detect_m1_trigger(df_m1, bias):
    if len(df_m1) < 3: return {"found": False}
    c1 = df_m1.iloc[-2]
    c0 = df_m1.iloc[-3]
    o1, c1c = c1["Open"], c1["Close"]
    h1, l1  = c1["High"], c1["Low"]
    o0, c0c = c0["Open"], c0["Close"]
    body1   = abs(c1c-o1)
    range1  = h1-l1
    body0   = abs(c0c-o0)
    if range1 == 0: return {"found": False}
    upper_shadow = h1 - max(o1,c1c)
    lower_shadow = min(o1,c1c) - l1
    if bias == "BUY":
        if c1c>o1 and c0c<o0 and o1<=c0c and c1c>=o0:
            return {"found": True, "type": "Bullish Engulfing", "strength": "KUAT" if body1>body0 else "SEDANG"}
        if c1c>o1 and lower_shadow>=2*body1 and upper_shadow<=0.3*range1:
            return {"found": True, "type": "Bullish Pin Bar", "strength": "KUAT"}
    elif bias == "SELL":
        if c1c<o1 and c0c>o0 and o1>=c0c and c1c<=o0:
            return {"found": True, "type": "Bearish Engulfing", "strength": "KUAT" if body1>body0 else "SEDANG"}
        if c1c<o1 and upper_shadow>=2*body1 and lower_shadow<=0.3*range1:
            return {"found": True, "type": "Bearish Pin Bar", "strength": "KUAT"}
    return {"found": False}

def calc_star_rating(bias_h4, sd_base, sr_flip, m1_trigger, ch_m30, price):
    """
    Sistem bintang sesuai ZEXLY Method ebook:
    ★1 — Searah bias H4 channel
    ★2 — Base valid di level S&R M30 (RBR/DBD terkonfirmasi)
    ★3 — Candle M5 sudah close konfirmasi (S&R flip valid)
    ★4 — Ada candle trigger jelas di M1 (Engulfing/Pin Bar)
    Minimal 3/4 bintang untuk entry
    """
    stars, reasons = 0, []

    # Bintang 1 — Searah bias H4
    stars += 1
    reasons.append(f"★ Searah bias H4 ({bias_h4})")

    # Bintang 2 — Base RBR/DBD valid di S&R M30
    if sd_base and sd_base.get("found"):
        stars += 1
        reasons.append(f"★ Base {sd_base['type']} valid ({sd_base['candles_in_base']} candle) di S&R M30")

    # Bintang 3 — Candle M5 close konfirmasi (S&R flip)
    if sr_flip.get("confirmed"):
        stars += 1
        reasons.append(f"★ M5 close konfirmasi: {sr_flip['detail']}")

    # Bintang 4 — Candle trigger M1 jelas
    if m1_trigger.get("found"):
        stars += 1
        reasons.append(f"★ Trigger M1: {m1_trigger['type']} ({m1_trigger['strength']})")

    return stars, reasons

def calc_sl_tp(price, bias, sd_base, sr_levels, ch_m30):
    """
    SL: di luar base + 5-7 pips buffer, total max ~15 pips (sesuai ebook)
    TP1: S&R berikutnya, min RR 1:1.5
    TP2: tepi channel M30, min RR 1:3
    """
    buffer  = 6.0   # 5-7 pips buffer sesuai ebook
    max_sl  = 15.0  # max SL ~15 pips sesuai ebook
    min_rr1 = 1.5   # RR minimum sesuai ebook

    if bias == "BUY":
        sl_base = sd_base["base_low"] if sd_base and sd_base.get("found") else price - max_sl
        sl      = round(sl_base - buffer, 2)
        risk    = abs(price - sl)
        if risk > max_sl:
            sl   = round(price - max_sl, 2)
            risk = max_sl

        min_tp1_dist = risk * min_rr1
        tp1_c = [lv for lv in sr_levels if lv > price + min_tp1_dist]
        tp1   = round(min(tp1_c), 2) if tp1_c else round(price + risk * min_rr1, 2)

        tp2 = round(ch_m30["upper"], 2)
        if tp2 <= tp1 or abs(tp2 - price) < risk * 3:
            tp2 = round(price + risk * 3, 2)

    else:
        sl_base = sd_base["base_high"] if sd_base and sd_base.get("found") else price + max_sl
        sl      = round(sl_base + buffer, 2)
        risk    = abs(sl - price)
        if risk > max_sl:
            sl   = round(price + max_sl, 2)
            risk = max_sl

        min_tp1_dist = risk * min_rr1
        tp1_c = [lv for lv in sr_levels if lv < price - min_tp1_dist]
        tp1   = round(max(tp1_c), 2) if tp1_c else round(price - risk * min_rr1, 2)

        tp2 = round(ch_m30["lower"], 2)
        if tp2 >= tp1 or abs(tp2 - price) < risk * 3:
            tp2 = round(price - risk * 3, 2)

    rr1 = round(abs(tp1 - price) / risk, 2) if risk > 0 else 0
    rr2 = round(abs(tp2 - price) / risk, 2) if risk > 0 else 0
    return {"sl":sl,"tp1":tp1,"tp2":tp2,"risk_pips":round(risk,1),"rr1":rr1,"rr2":rr2}

# ══════════════════════════════════════════════════════════════════
#  CHART via chart-img.com
# ══════════════════════════════════════════════════════════════════

INTERVAL_MAP = {
    "M1":"1m","M5":"5m","M15":"15m","M30":"30m","H1":"1h","H4":"4h"
}

TF_YFINANCE = {
    "M1":  ("1d",  "1m"),
    "M5":  ("3d",  "5m"),
    "M15": ("5d",  "15m"),
    "M30": ("10d", "30m"),
    "H1":  ("1mo", "1h"),
    "H4":  ("2mo", "1h"),
}

def generate_chart(tf="M5", entry=None, sl=None, tp1=None, tp2=None, sr_levels=None, sd_base=None):
    try:
        import mplfinance as mpf
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.lines as mlines
        import matplotlib.patches as mpatches
        import matplotlib.ticker as mticker

        tf_up = tf.upper()
        period, interval = TF_YFINANCE.get(tf_up, ("3d", "5m"))
        df = yf.Ticker("GC=F").history(period=period, interval=interval)
        if df is None or df.empty:
            log.error("Chart: data kosong")
            return None
        df.dropna(inplace=True)
        if tf_up == "H4":
            df = df.resample("4h").agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna()
        df = df.tail(150)
        path = f"zexly_chart_{tf}.png"

        # Hitung EMA
        ema20 = df["Close"].ewm(span=20, adjust=False).mean()
        ema50 = df["Close"].ewm(span=50, adjust=False).mean()

        # Style TradingView-like
        mc = mpf.make_marketcolors(
            up="#26a69a", down="#ef5350",
            edge={"up":"#26a69a","down":"#ef5350"},
            wick={"up":"#26a69a","down":"#ef5350"},
            volume={"up":"#26a69a88","down":"#ef535088"}
        )
        style = mpf.make_mpf_style(
            marketcolors=mc,
            base_mpf_style="nightclouds",
            gridstyle=":",
            gridcolor="#1e2130",
            facecolor="#131722",
            figcolor="#0e1117",
            rc={
                "axes.labelcolor":"#787b86",
                "xtick.color":"#787b86",
                "ytick.color":"#787b86",
                "xtick.labelsize": 9,
                "ytick.labelsize": 9,
                "axes.edgecolor": "#2a2e39",
                "font.family": "monospace"
            }
        )

        apds = []
        # EMA lines
        apds.append(mpf.make_addplot(ema20, color="#f9ca24", width=1.2, secondary_y=False))
        apds.append(mpf.make_addplot(ema50, color="#6c5ce7", width=1.2, secondary_y=False))

        # Signal lines
        if entry: apds.append(mpf.make_addplot([entry]*len(df), color="#00bcd4", linestyle="--", width=1.2, secondary_y=False))
        if sl:    apds.append(mpf.make_addplot([sl]*len(df),    color="#ef5350", linestyle="--", width=1.2, secondary_y=False))
        if tp1:   apds.append(mpf.make_addplot([tp1]*len(df),   color="#26a69a", linestyle="--", width=1.0, secondary_y=False))
        if tp2:   apds.append(mpf.make_addplot([tp2]*len(df),   color="#66bb6a", linestyle=":",  width=1.0, secondary_y=False))
        if sr_levels:
            for lv in sr_levels:
                apds.append(mpf.make_addplot([lv]*len(df), color="#ff9800", linestyle="-", width=0.7, alpha=0.6, secondary_y=False))

        fig, axes = mpf.plot(
            df, type="candle", style=style,
            addplot=apds,
            volume=True,
            figsize=(16, 9),
            returnfig=True,
            tight_layout=False,
            scale_padding={"left":0.1,"right":0.8,"top":0.3,"bottom":0.5}
        )

        ax  = axes[0]
        axv = axes[2] if len(axes) > 2 else None

        # S&D zone shading
        if sd_base and sd_base.get("found"):
            color_zone = "#26a69a" if sd_base.get("type","").startswith("R") else "#ef5350"
            ax.axhspan(sd_base["base_low"], sd_base["base_high"], alpha=0.12, color=color_zone, zorder=0)
            ax.axhline(sd_base["base_mid"], color=color_zone, linestyle="-", linewidth=0.8, alpha=0.5)
            ax.axhline(sd_base["base_high"], color=color_zone, linestyle="-", linewidth=0.5, alpha=0.4)
            ax.axhline(sd_base["base_low"],  color=color_zone, linestyle="-", linewidth=0.5, alpha=0.4)

        # Label harga di kanan (kayak TradingView)
        def add_price_label(ax, price, color, label, linestyle="--"):
            ax.axhline(price, color=color, linestyle=linestyle, linewidth=1.0, alpha=0.8)
            xlim = ax.get_xlim()
            ax.text(xlim[1] + 0.3, price, f" {label} | {price}", color=color,
                    fontsize=7.5, va="center", ha="left",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="#0e1117", edgecolor=color, alpha=0.8))

        if entry: add_price_label(ax, entry, "#00bcd4", "ENTRY")
        if sl:    add_price_label(ax, sl,    "#ef5350", "SL")
        if tp1:   add_price_label(ax, tp1,   "#26a69a", "TP1")
        if tp2:   add_price_label(ax, tp2,   "#66bb6a", "TP2", ":")

        # Legend EMA + signal
        legend_items = [
            mlines.Line2D([],[],color="#f9ca24", linewidth=1.2, label="EMA 20"),
            mlines.Line2D([],[],color="#6c5ce7", linewidth=1.2, label="EMA 50"),
        ]
        if sd_base and sd_base.get("found"):
            color_zone = "#26a69a" if sd_base.get("type","").startswith("R") else "#ef5350"
            legend_items.append(mpatches.Patch(color=color_zone, alpha=0.3, label=f"S&D {sd_base.get('type','')}"))
        ax.legend(handles=legend_items, loc="upper left", fontsize=8,
                  framealpha=0.15, facecolor="#131722", edgecolor="#2a2e39",
                  labelcolor="white")

        # Title custom
        last_price = float(df["Close"].iloc[-1])
        bias_txt   = ""
        if entry and sl:
            bias_txt = "  🟢 BUY" if entry > sl else "  🔴 SELL"
        ax.set_title(
            f"XAUUSD {tf_up}  |  ${last_price:.2f}{bias_txt}  |  ZEXINFO",
            color="#d1d4dc", fontsize=12, fontweight="bold", pad=10,
            loc="left"
        )

        # Watermark
        fig.text(0.5, 0.5, "ZEXINFO", fontsize=52, color="#ffffff",
                 alpha=0.03, ha="center", va="center", fontweight="bold",
                 rotation=25, transform=ax.transAxes)

        # Volume label
        if axv:
            axv.set_ylabel("Volume", color="#787b86", fontsize=8)

        plt.subplots_adjust(left=0.05, right=0.88, top=0.93, bottom=0.08)
        plt.savefig(path, dpi=150, bbox_inches=None, facecolor="#0e1117")
        plt.close(fig)
        log.info(f"Chart {tf_up} generated: {path}")
        return path
    except Exception as e:
        log.error(f"Chart error: {e}")
        return None

# ══════════════════════════════════════════════════════════════════
#  FORMAT PESAN
# ══════════════════════════════════════════════════════════════════

def format_signal_msg(price, bias, stars, reasons, sd_base,
                      trigger, sr_flip, sl_tp, rsi, session, ch_h4, ch_m30, force=False):
    stars_str    = "★"*stars + "☆"*(4-stars)
    signal_emoji = "🔴 SELL" if bias=="SELL" else "🟢 BUY"
    header       = "⚡ *FORCE ENTRY*" if force else "🦅 *ZEXLY — SINYAL ENTRY*"
    base_txt     = (
        f"`{sd_base['type']} — {sd_base['candles_in_base']} candle`\n"
        f"   Zone: `{sd_base['base_low']} - {sd_base['base_high']}`"
    ) if sd_base and sd_base.get("found") else "`Tidak terdeteksi`"
    trigger_txt  = f"`{trigger['type']} ({trigger['strength']})`" if trigger.get("found") else "`Belum muncul`"
    flip_txt     = f"`{sr_flip['detail']}`" if sr_flip.get("confirmed") else "`Belum flip`"
    rsi_label    = "⚠️ OB" if rsi>=70 else "🔶 Near OB" if rsi>=65 else "⚠️ OS" if rsi<=30 else "🔷 Near OS" if rsi<=35 else "➖ Netral"
    reasons_str  = "\n".join([f"  {r}" for r in reasons])
    rr_warn      = f"\n   ⚠️ RR rendah ({sl_tp['rr1']}:1)" if sl_tp["rr1"]<1.5 else ""
    ch_tag = " (manual)" if ch_h4.get("manual") else f" [{ch_h4.get('mode','auto')}]"

    return (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Price:* `${price}`\n"
        f"⚡ *Signal:* {signal_emoji}\n"
        f"⭐ *Kualitas:* `{stars_str}` ({stars}/4)\n"
        f"📡 *Sesi:* {session}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏗️ *H4 Channel*{ch_tag}\n"
        f"   Upper: `{ch_h4['upper']}` | Lower: `{ch_h4['lower']}`\n"
        f"   Bias: `{bias} ONLY`\n\n"
        f"📐 *M30 Channel*\n"
        f"   Upper: `{ch_m30['upper']}` | Lower: `{ch_m30['lower']}`\n\n"
        f"🎯 *S&D Base:* {base_txt}\n\n"
        f"🔀 *S&R Flip M5:* {flip_txt}\n\n"
        f"🕯️ *Trigger M1:* {trigger_txt}\n\n"
        f"📈 *RSI M30:* `{rsi}` — {rsi_label}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💼 *TRADE PLAN*\n"
        f"   Entry: `${price}`\n"
        f"   SL   : `${sl_tp['sl']}` ({sl_tp['risk_pips']} pips)\n"
        f"   TP1  : `${sl_tp['tp1']}` (RR `{sl_tp['rr1']}:1`) → 70%\n"
        f"   TP2  : `${sl_tp['tp2']}` (RR `{sl_tp['rr2']}:1`) → 30%{rr_warn}\n\n"
        f"   TP1 hit → geser SL ke breakeven!\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ *ALASAN:*\n{reasons_str}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏰ Konfirmasi M1 sebelum entry!\n"
        f"`{get_waktu()}`"
    )

# ══════════════════════════════════════════════════════════════════
#  BROADCAST
# ══════════════════════════════════════════════════════════════════

async def broadcast(bot, caption, chart=None):
    targets = BROADCAST_IDS
    if CHAT_ID and CHAT_ID not in targets:
        targets = [CHAT_ID] + targets
    for cid in targets:
        try:
            if chart and os.path.exists(chart):
                with open(chart, "rb") as ph:
                    await bot.send_photo(chat_id=cid, photo=ph, caption=caption, parse_mode="Markdown")
            else:
                await bot.send_message(chat_id=cid, text=caption, parse_mode="Markdown")
        except Exception as e:
            log.error(f"Broadcast ke {cid} gagal: {e}")

# ══════════════════════════════════════════════════════════════════
#  AUTO SCAN
# ══════════════════════════════════════════════════════════════════

# Tracking sinyal terakhir untuk hindari duplikat
_last_signal = {"bias": None, "price": None, "stars": 0}

async def auto_scan(context: ContextTypes.DEFAULT_TYPE):
    global _last_signal
    ok_ses, session = get_session_status()
    if not ok_ses:
        log.info(f"Auto scan skip — {session}")
        return

    log.info("Auto scan running...")
    data = fetch_data()
    if not data: return

    price     = round(float(data["m1"]["Close"].iloc[-1]), 2)
    manual_ch = load_manual_channel()
    ch_h4     = manual_ch if manual_ch else calc_auto_channel(data["h4"])
    ch_m30    = calc_auto_channel(data["m30"])
    bias      = get_h4_bias(ch_h4, price)

    if bias == "SKIP":
        log.info("Auto scan: middle zone, skip")
        return

    sd_base = detect_sd_base(data["m30"], bias)
    sr_lvls = find_sr_levels(data["m30"])
    sr_flip = check_sr_flip_m5(data["m5"], sr_lvls, bias)
    trigger = detect_m1_trigger(data["m1"], bias)
    stars, reasons = calc_star_rating(bias, sd_base, sr_flip, trigger, ch_m30, price)

    # Filter: minimal 3 bintang sesuai ebook
    if stars < 3:
        log.info(f"Auto scan: {stars} bintang — skip (min 3)")
        return

    # Anti duplikat: skip kalau sinyal sama dengan sebelumnya
    price_diff = abs(price - (_last_signal["price"] or 0))
    if _last_signal["bias"] == bias and _last_signal["stars"] == stars and price_diff < 5:
        log.info("Auto scan: sinyal duplikat, skip")
        return

    _last_signal = {"bias": bias, "price": price, "stars": stars}

    sl_tp   = calc_sl_tp(price, bias, sd_base, sr_lvls, ch_m30)

    # Validasi RR minimum 1:1.5
    if sl_tp["rr1"] < 1.5:
        log.info(f"Auto scan: RR {sl_tp['rr1']} < 1.5, skip")
        return

    _, session = get_session_status()
    rsi     = calc_rsi(data["m30"]["Close"])
    caption = format_signal_msg(price, bias, stars, reasons, sd_base,
                                trigger, sr_flip, sl_tp, rsi, session, ch_h4, ch_m30)
    chart   = generate_chart("M5", entry=price, sl=sl_tp["sl"],
                             tp1=sl_tp["tp1"], tp2=sl_tp["tp2"],
                             sr_levels=sr_lvls, sd_base=sd_base)
    await broadcast(context.bot, caption, chart)
    log.info(f"Auto scan: sinyal {stars}★ {bias} dikirim")

# ══════════════════════════════════════════════════════════════════
#  CORE SCAN
# ══════════════════════════════════════════════════════════════════

async def do_full_scan(force=False):
    data = fetch_data()
    if not data: return "❌ Gagal ambil data market.", None

    price     = round(float(data["m1"]["Close"].iloc[-1]), 2)
    manual_ch = load_manual_channel()
    ch_h4     = manual_ch if manual_ch else calc_auto_channel(data["h4"])
    ch_m30    = calc_auto_channel(data["m30"])
    bias      = get_h4_bias(ch_h4, price)
    _, session = get_session_status()

    if bias == "SKIP" and not force:
        return (
            f"⏸ *SCAN RESULT*\n"
            f"💰 Price: `${price}`\n"
            f"Bias: `SKIP` — Middle Zone, tidak trading\n"
            f"`{get_waktu()}`"
        ), None

    if bias == "SKIP" and force:
        bias = "SELL"

    rsi      = calc_rsi(data["m30"]["Close"])
    sd_base  = detect_sd_base(data["m30"], bias)
    sr_lvls  = find_sr_levels(data["m30"])
    sr_flip  = check_sr_flip_m5(data["m5"], sr_lvls, bias)
    trigger  = detect_m1_trigger(data["m1"], bias)
    stars, reasons = calc_star_rating(bias, sd_base, sr_flip, trigger, ch_m30, price)

    if force: reasons.append("⚡ Manual override via /force")

    sl_tp   = calc_sl_tp(price, bias, sd_base, sr_lvls, ch_m30)
    caption = format_signal_msg(price, bias, stars, reasons, sd_base,
                                trigger, sr_flip, sl_tp, rsi, session, ch_h4, ch_m30, force)

    # Save position
    save_json(POSITION_FILE, {
        "bias": bias, "entry": price,
        "sl": sl_tp["sl"], "tp1": sl_tp["tp1"], "tp2": sl_tp["tp2"],
        "tp1_hit": False, "tp2_hit": False, "sl_hit": False
    })

    chart = generate_chart("M5", entry=price, sl=sl_tp["sl"], tp1=sl_tp["tp1"], tp2=sl_tp["tp2"], sr_levels=sr_lvls, sd_base=sd_base)
    return caption, chart

# ══════════════════════════════════════════════════════════════════
#  TP/SL MONITOR
# ══════════════════════════════════════════════════════════════════

async def monitor_tp_sl(context: ContextTypes.DEFAULT_TYPE):
    pos = load_json(POSITION_FILE)
    if not pos or not pos.get("bias"): return

    price = get_current_price()
    if not price: return

    bias  = pos["bias"]
    entry = pos["entry"]
    sl, tp1, tp2 = pos["sl"], pos["tp1"], pos["tp2"]
    tp1_hit = pos.get("tp1_hit", False)
    tp2_hit = pos.get("tp2_hit", False)
    sl_hit  = pos.get("sl_hit", False)

    if sl_hit or tp2_hit:
        try: os.remove(POSITION_FILE)
        except Exception: pass
        return

    alert = ""
    if bias == "SELL":
        if not tp1_hit and price <= tp1:
            alert = f"🎯 *TP1 HIT!* `${tp1}`\nTutup 70% & geser SL ke `${entry}` (breakeven)"
            pos["tp1_hit"] = True
        elif tp1_hit and not tp2_hit and price <= tp2:
            alert = f"🏆 *TP2 HIT!* `${tp2}`\nTutup sisa 30% — FULL PROFIT!"
            pos["tp2_hit"] = True
        elif not sl_hit and price >= sl:
            alert = f"🛑 *SL HIT!* `${sl}`\nPosisi ditutup."
            pos["sl_hit"] = True
    elif bias == "BUY":
        if not tp1_hit and price >= tp1:
            alert = f"🎯 *TP1 HIT!* `${tp1}`\nTutup 70% & geser SL ke `${entry}` (breakeven)"
            pos["tp1_hit"] = True
        elif tp1_hit and not tp2_hit and price >= tp2:
            alert = f"🏆 *TP2 HIT!* `${tp2}`\nTutup sisa 30% — FULL PROFIT!"
            pos["tp2_hit"] = True
        elif not sl_hit and price <= sl:
            alert = f"🛑 *SL HIT!* `${sl}`\nPosisi ditutup."
            pos["sl_hit"] = True

    if alert:
        msg = (
            f"{alert}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Entry: `${entry}` | Now: `${price}`\n"
            f"`{get_waktu()}`"
        )
        await broadcast(context.bot, msg)
        save_json(POSITION_FILE, pos)
        if pos.get("sl_hit") or pos.get("tp2_hit"):
            try: os.remove(POSITION_FILE)
            except Exception: pass

# ══════════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔍 Scan", callback_data="scan"),
         InlineKeyboardButton("⚡ Force", callback_data="force")],
        [InlineKeyboardButton("📊 Chart M5", callback_data="chart_M5"),
         InlineKeyboardButton("📊 Chart M30", callback_data="chart_M30")],
        [InlineKeyboardButton("📈 Chart H4", callback_data="chart_H4"),
         InlineKeyboardButton("📋 Summary", callback_data="summary")],
        [InlineKeyboardButton("ℹ️ Status", callback_data="status")],
    ]
    await update.message.reply_text(
        f"🦅 *ZEXLY COMMAND CENTER*\n`{get_waktu()}`",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Scanning...")
    caption, chart = await do_full_scan(force=False)
    await msg.delete()
    if chart and os.path.exists(chart):
        with open(chart,"rb") as ph:
            await update.message.reply_photo(photo=ph, caption=caption, parse_mode="Markdown")
    else:
        await update.message.reply_text(caption, parse_mode="Markdown")

async def cmd_force(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⚡ Force scanning...")
    caption, chart = await do_full_scan(force=True)
    await msg.delete()
    if chart and os.path.exists(chart):
        with open(chart,"rb") as ph:
            await update.message.reply_photo(photo=ph, caption=caption, parse_mode="Markdown")
    else:
        await update.message.reply_text(caption, parse_mode="Markdown")

async def cmd_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    tf   = args[0].upper() if args else "M5"
    if tf not in INTERVAL_MAP:
        await update.message.reply_text(f"TF tidak valid. Pilihan: {', '.join(INTERVAL_MAP.keys())}")
        return
    msg = await update.message.reply_text(f"📸 Mengambil chart {tf}...")
    chart = generate_chart(tf)
    price = get_current_price()
    await msg.delete()
    if chart and os.path.exists(chart):
        with open(chart,"rb") as ph:
            await update.message.reply_photo(
                photo=ph,
                caption=f"📊 *XAUUSD {tf}*\n💰 `${price}`\n`{get_waktu()}`",
                parse_mode="Markdown"
            )
    else:
        await update.message.reply_text("❌ Gagal ambil chart.")

async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📊 Mengambil data...")
    data = fetch_data()
    if not data:
        await msg.edit_text("❌ Gagal ambil data.")
        return
    price     = round(float(data["m1"]["Close"].iloc[-1]), 2)
    manual_ch = load_manual_channel()
    ch_h4     = manual_ch if manual_ch else calc_auto_channel(data["h4"])
    ch_m30    = calc_auto_channel(data["m30"])
    bias      = get_h4_bias(ch_h4, price)
    rsi       = calc_rsi(data["m30"]["Close"])
    sr_levels = find_sr_levels(data["m30"])
    bias_emoji = "🔴 SELL ONLY" if bias=="SELL" else "🟢 BUY ONLY" if bias=="BUY" else "⏸ SKIP"
    ch_mode    = "manual" if ch_h4.get("manual") else ch_h4.get("mode","auto")
    sr_txt     = " | ".join([f"`{lv}`" for lv in sr_levels]) if sr_levels else "`Tidak ada`"
    ok_ses, session = get_session_status()
    text = (
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
        f"📡 *Sesi:* {session}\n"
        f"`{get_waktu()}`"
    )
    await msg.delete()
    chart = generate_chart("M30")
    if chart and os.path.exists(chart):
        with open(chart,"rb") as ph:
            await update.message.reply_photo(photo=ph, caption=text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price     = get_current_price()
    ok_ses, session = get_session_status()
    manual_ch = load_manual_channel()
    ch_mode   = "manual" if manual_ch else "auto"
    pos       = load_json(POSITION_FILE)
    pos_txt   = (
        f"📌 Posisi: `{pos['bias']}` entry `${pos['entry']}`\n"
        f"   SL:`${pos['sl']}` TP1:`${pos['tp1']}` TP2:`${pos['tp2']}`"
    ) if pos and pos.get("bias") else "📌 Tidak ada posisi aktif"
    await update.message.reply_text(
        f"📊 *ZEXLY STATUS*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 Harga: `${price or 'N/A'}`\n"
        f"📡 Sesi: {session}\n"
        f"🟢 Trading: {'AKTIF' if ok_ses else 'OFF'}\n"
        f"🏗️ Channel: `{ch_mode}`\n"
        f"{pos_txt}\n"
        f"`{get_waktu()}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"`/scan` `/force` `/chart [tf]`\n"
        f"`/summary` `/status`\n"
        f"`/setchannel p1 p2 p3`\n"
        f"`/delchannel`",
        parse_mode="Markdown"
    )

async def cmd_setchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) != 3:
        await update.message.reply_text(
            "*Format:* `/setchannel p1 p2 p3`\n\n"
            "Contoh 2 upper 1 lower:\n`/setchannel 4920 4880 4660`\n\n"
            "Contoh 1 upper 2 lower:\n`/setchannel 4920 4700 4660`",
            parse_mode="Markdown"
        )
        return
    try:
        p1, p2, p3 = float(args[0]), float(args[1]), float(args[2])
        ch = calc_channel_from_3points(p1, p2, p3)
        save_manual_channel(ch)
        await update.message.reply_text(
            f"✅ *CHANNEL DISIMPAN*\n"
            f"Mode: `{ch['mode']}`\n"
            f"Upper: `{ch['upper']}` | Mid: `{ch['mid']}` | Lower: `{ch['lower']}`\n"
            f"Upper Zone: > `{ch['upper_third']}`\n"
            f"Lower Zone: < `{ch['lower_third']}`",
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("❌ Angka tidak valid.")

async def cmd_delchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    delete_manual_channel()
    await update.message.reply_text(
        "🗑️ *Channel manual dihapus.*\nBot kembali pakai auto detect.",
        parse_mode="Markdown"
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "scan":
        await query.edit_message_text("🔍 Scanning...")
        caption, chart = await do_full_scan(force=False)
        await query.delete_message()
        if chart and os.path.exists(chart):
            with open(chart,"rb") as ph:
                await context.bot.send_photo(chat_id=query.message.chat_id,
                                              photo=ph, caption=caption, parse_mode="Markdown")
        else:
            await context.bot.send_message(chat_id=query.message.chat_id,
                                            text=caption, parse_mode="Markdown")

    elif data == "force":
        await query.edit_message_text("⚡ Force scanning...")
        caption, chart = await do_full_scan(force=True)
        await query.delete_message()
        if chart and os.path.exists(chart):
            with open(chart,"rb") as ph:
                await context.bot.send_photo(chat_id=query.message.chat_id,
                                              photo=ph, caption=caption, parse_mode="Markdown")
        else:
            await context.bot.send_message(chat_id=query.message.chat_id,
                                            text=caption, parse_mode="Markdown")

    elif data.startswith("chart_"):
        tf = data.split("_")[1]
        await query.edit_message_text(f"📸 Mengambil chart {tf}...")
        chart = generate_chart(tf)
        price = get_current_price()
        await query.delete_message()
        if chart and os.path.exists(chart):
            with open(chart,"rb") as ph:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id, photo=ph,
                    caption=f"📊 *XAUUSD {tf}*\n💰 `${price}`\n`{get_waktu()}`",
                    parse_mode="Markdown"
                )
        else:
            await context.bot.send_message(chat_id=query.message.chat_id,
                                            text="❌ Gagal ambil chart.")

    elif data == "summary":
        await query.edit_message_text("📊 Mengambil data...")
        # Reuse cmd_summary logic
        data_market = fetch_data()
        if not data_market:
            await query.edit_message_text("❌ Gagal ambil data.")
            return
        price     = round(float(data_market["m1"]["Close"].iloc[-1]), 2)
        manual_ch = load_manual_channel()
        ch_h4     = manual_ch if manual_ch else calc_auto_channel(data_market["h4"])
        ch_m30    = calc_auto_channel(data_market["m30"])
        bias      = get_h4_bias(ch_h4, price)
        rsi       = calc_rsi(data_market["m30"]["Close"])
        sr_levels = find_sr_levels(data_market["m30"])
        bias_emoji = "🔴 SELL ONLY" if bias=="SELL" else "🟢 BUY ONLY" if bias=="BUY" else "⏸ SKIP"
        ch_mode    = "manual" if ch_h4.get("manual") else ch_h4.get("mode","auto")
        sr_txt     = " | ".join([f"`{lv}`" for lv in sr_levels]) if sr_levels else "`Tidak ada`"
        _, session = get_session_status()
        text = (
            f"📊 *ZEXLY SUMMARY*\n"
            f"💰 Price: `${price}` | Bias: {bias_emoji}\n"
            f"🏗️ H4 _{ch_mode}_: `{ch_h4['upper']}` - `{ch_h4['lower']}`\n"
            f"📐 M30: `{ch_m30['upper']}` - `{ch_m30['lower']}`\n"
            f"🎯 S&R: {sr_txt}\n"
            f"📈 RSI: `{rsi}` | 📡 {session}\n"
            f"`{get_waktu()}`"
        )
        await query.delete_message()
        chart = generate_chart("M30")
        if chart and os.path.exists(chart):
            with open(chart,"rb") as ph:
                await context.bot.send_photo(chat_id=query.message.chat_id,
                                              photo=ph, caption=text, parse_mode="Markdown")
        else:
            await context.bot.send_message(chat_id=query.message.chat_id,
                                            text=text, parse_mode="Markdown")

    elif data == "status":
        price     = get_current_price()
        ok_ses, session = get_session_status()
        manual_ch = load_manual_channel()
        await query.edit_message_text(
            f"📊 *STATUS*\n"
            f"💰 `${price}` | 📡 {session}\n"
            f"🏗️ Channel: `{'manual' if manual_ch else 'auto'}`\n"
            f"`{get_waktu()}`",
            parse_mode="Markdown"
        )

# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()

    # TP/SL monitor tiap 30 detik
    app.job_queue.run_repeating(monitor_tp_sl, interval=30, first=10)
    # Auto scan tiap 5 menit saat sesi aktif
    app.job_queue.run_repeating(auto_scan, interval=300, first=60)

    # Commands
    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("scan",       cmd_scan))
    app.add_handler(CommandHandler("force",      cmd_force))
    app.add_handler(CommandHandler("chart",      cmd_chart))
    app.add_handler(CommandHandler("summary",    cmd_summary))
    app.add_handler(CommandHandler("status",     cmd_status))
    app.add_handler(CommandHandler("setchannel", cmd_setchannel))
    app.add_handler(CommandHandler("delchannel", cmd_delchannel))
    app.add_handler(CallbackQueryHandler(callback_handler))

    log.info("🦅 ZEXLY Command Bot running on Railway...")
    app.run_polling(drop_pending_updates=True)
