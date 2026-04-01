# ============================================================
# 独立策略：CNH-CHAU 离岸人民币对冲（JQ版）
# 平台：聚宽 (JoinQuant)
# 信号模式：USDCNH vs SMA5/10/30
#   - 价格 < 三条均线 → LONG（人民币走强→买CHAU）
#   - 价格 > 三条均线 → SHORT（人民币走弱→空CHAU）
#   - 死区过滤 < 0.1%
# Algo ID: JQ-CHAU
#
# NAV追踪：基于 CHAU ETF（2x杠杆沪深300）价格变动
# 数据源：USDCNH → AV FX_DAILY（信号）
#         CHAU   → AV TIME_SERIES_DAILY（NAV）
# ============================================================

from jqdata import *
import requests
import time
from datetime import datetime, timedelta

WEBHOOK_URL = "https://www.quanttogo.com/receiveJQWebhook?token=b39b4e3e4cd2e55e8432d039e3112edf76d1ab4d7bb060feb42d2c4134362bc8"
ALGO_ID = "JQ-CHAU"
AV_API_KEY = "VPC2QYD308YNNCDN"
DEADZONE_PCT = 0.001  # 0.1%


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)

    g.cnh_signal = "LONG"
    g.nav = 7.728385
    g.entry_price = 21.38      # 最后一个backfill日(3/4)的CHAU收盘价
    g.direction = "LONG"       # LONG / SHORT / NONE
    g.data_ok = True
    g.us_trade_date = None     # 美股实际交易日

    run_daily(daily_check, time='14:20')


# ============================================================
# 数据获取
# ============================================================
def fetch_usdcnh(count=35):
    """AV获取USDCNH最近count天日收盘价（升序）"""
    try:
        resp = requests.get("https://www.alphavantage.co/query", params={
            "function": "FX_DAILY",
            "from_symbol": "USD",
            "to_symbol": "CNH",
            "outputsize": "compact",
            "apikey": AV_API_KEY,
        }, timeout=15)
        ts = resp.json().get("Time Series FX (Daily)", {})
        if not ts:
            log.warn(f"[CHAU] USDCNH AV返回空")
            return None
        prices = [float(ts[d]["4. close"]) for d in sorted(ts.keys())]
        if len(prices) < count:
            return prices if len(prices) >= 5 else None
        return prices[-count:]
    except Exception as e:
        log.error(f"[CHAU] USDCNH获取失败: {e}")
        return None


def fetch_chau_price():
    """AV获取CHAU ETF最新收盘价，同时记录美股交易日"""
    try:
        time.sleep(13)  # AV限频
        resp = requests.get("https://www.alphavantage.co/query", params={
            "function": "TIME_SERIES_DAILY",
            "symbol": "CHAU",
            "outputsize": "compact",
            "apikey": AV_API_KEY,
        }, timeout=30)
        ts = resp.json().get("Time Series (Daily)", {})
        if not ts:
            log.warn("[CHAU] CHAU ETF AV返回空")
            return None
        latest = sorted(ts.keys())[-1]
        g.us_trade_date = latest  # 记录美股交易日
        price = float(ts[latest]["4. close"])
        log.info(f"[CHAU] CHAU ETF = {price:.2f} ({latest})")
        return price
    except Exception as e:
        log.error(f"[CHAU] CHAU ETF获取失败: {e}")
        return None


# ============================================================
# 每日检查
# ============================================================
def daily_check(context):
    today = context.current_dt.strftime("%Y-%m-%d")

    # 1. 获取 USDCNH（信号用）
    usdcnh = fetch_usdcnh(35)
    if not usdcnh or len(usdcnh) < 30:
        g.data_ok = False
        log.warn(f"[CHAU] {today} USDCNH数据不足")
        # 仍尝试获取CHAU价格发送NAV
        chau_price = fetch_chau_price()
        send_nav_webhook(context, chau_price)
        return
    g.data_ok = True

    current_cnh = usdcnh[-1]
    sma5 = sum(usdcnh[-5:]) / 5
    sma10 = sum(usdcnh[-10:]) / 10
    sma30 = sum(usdcnh[-30:]) / 30

    below_all = current_cnh < sma5 and current_cnh < sma10 and current_cnh < sma30
    above_all = current_cnh > sma5 and current_cnh > sma10 and current_cnh > sma30

    # 2. 获取 CHAU ETF 价格（NAV用）
    chau_price = fetch_chau_price()

    if not below_all and not above_all:
        send_nav_webhook(context, chau_price)
        return

    # 死区过滤
    nearest_ma = min(sma5, sma10, sma30) if below_all else max(sma5, sma10, sma30)
    distance_pct = abs(current_cnh - nearest_ma) / current_cnh
    if distance_pct < DEADZONE_PCT:
        send_nav_webhook(context, chau_price)
        return

    new_signal = "LONG" if below_all else "SHORT"

    if new_signal != g.cnh_signal:
        old = g.cnh_signal

        # 平旧仓（用 CHAU ETF 价格计算盈亏）
        if g.entry_price is not None and g.direction != "NONE" and chau_price:
            move = (chau_price - g.entry_price) / g.entry_price
            if g.direction == "SHORT":
                move = -move
            g.nav *= (1 + move)
            log.info(f"[CHAU] 平仓 {g.direction} CHAU@{g.entry_price:.2f}→{chau_price:.2f} {move*100:+.2f}% NAV={g.nav:.6f}")

        # 开新仓（CHAU ETF 价格作为入场价）
        if chau_price:
            g.entry_price = chau_price
        g.direction = new_signal
        g.cnh_signal = new_signal

        log.info(f"[CHAU] {old}→{new_signal} CNH={current_cnh:.4f} CHAU={chau_price} dz={distance_pct*100:.3f}%")

        send_signal_webhook({
            "algo": ALGO_ID,
            "action": new_signal,
            "symbol": "CHAU",
            "signalMode": "direction_switch",
            "notes": f"CNH={current_cnh:.4f} {'<' if below_all else '>'} 均线 → {new_signal} CHAU@{chau_price}, dz={distance_pct*100:.3f}%"
        })

    send_nav_webhook(context, chau_price)


# ============================================================
# NAV（基于 CHAU ETF 价格）
# ============================================================
def calc_nav(chau_price):
    if g.direction == "NONE" or g.entry_price is None or chau_price is None:
        return g.nav
    move = (chau_price - g.entry_price) / g.entry_price
    if g.direction == "SHORT":
        move = -move
    return g.nav * (1 + move)


# ============================================================
# Webhook
# ============================================================
def send_signal_webhook(payload):
    try:
        payload["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload["timestamp"] = datetime.now().isoformat()
        payload["event"] = "order_fill"
        resp = requests.post(WEBHOOK_URL, json=payload,
                           headers={"Content-Type": "application/json"}, timeout=5)
        log.info(f"[CHAU] Signal webhook: {resp.status_code}")
    except Exception as e:
        log.error(f"[CHAU] Signal webhook error: {e}")


def send_nav_webhook(context, chau_price):
    # 使用AV返回的美股交易日
    trade_date = g.us_trade_date or (context.current_dt - timedelta(days=1)).strftime('%Y-%m-%d')
    nav = calc_nav(chau_price)
    status = {
        "data_ok": g.data_ok,
        "signal": g.cnh_signal,
        "holding": g.direction,
        "error": "数据获取失败" if not g.data_ok else None
    }
    try:
        payload = {
            "algo": ALGO_ID,
            "event": "daily_nav",
            "nav": round(nav, 6),
            "date": trade_date,
            "total_value": round(nav * 100000, 2),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": datetime.now().isoformat(),
            "status": status
        }
        requests.post(WEBHOOK_URL, json=payload,
                     headers={"Content-Type": "application/json"}, timeout=5)
        log.info(f"[CHAU] NAV: {nav:.6f} CHAU={chau_price} date={trade_date}")
    except Exception as e:
        log.error(f"[CHAU] NAV webhook error: {e}")
