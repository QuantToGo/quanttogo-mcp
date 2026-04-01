# ============================================================
# 独立策略：E-3x 纳斯达克杠杆趋势（JQ版）
# 平台：聚宽 (JoinQuant)
# 信号模式：QQQ SMA50 vs SMA200 金叉/死叉 → TQQQ/SHY
# Algo ID: JQ-E3X
#
# JQ不能交易美股 → 纯信号+手动NAV追踪
# 数据源：Alpha Vantage TIME_SERIES_DAILY
# ============================================================

from jqdata import *
import requests
import pandas as pd
import time
from datetime import datetime, timedelta

WEBHOOK_URL = "https://www.quanttogo.com/receiveJQWebhook?token=b39b4e3e4cd2e55e8432d039e3112edf76d1ab4d7bb060feb42d2c4134362bc8"
ALGO_ID = "JQ-E3X"
AV_API_KEY = "VPC2QYD308YNNCDN"


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)

    g.last_signal = "GOLDEN"    # "GOLDEN" / "DEATH"
    g.holding = "TQQQ"          # "TQQQ" / "SHY"
    g.entry_price = 50.26       # 最后一个backfill日(3/4)的TQQQ收盘价
    g.nav = 20.207462           # backfill最终NAV（含未实现）
    g.price_cache = {}      # 当日价格缓存
    g.data_ok = True        # 数据获取状态
    g.us_trade_date = None  # 美股实际交易日（从AV获取）

    run_daily(daily_check, time='14:00')


# ============================================================
# Alpha Vantage 数据
# ============================================================
def fetch_av_daily(symbol, outputsize="compact"):
    """获取日线收盘价序列，同时返回最新美股交易日"""
    try:
        resp = requests.get("https://www.alphavantage.co/query", params={
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": outputsize,
            "apikey": AV_API_KEY,
        }, timeout=30)
        ts = resp.json().get("Time Series (Daily)", {})
        if not ts:
            log.warn(f"[E3X] {symbol} AV返回空")
            return None, None
        dates_sorted = sorted(ts.keys())
        closes = [float(ts[d]["4. close"]) for d in dates_sorted]
        latest_date = dates_sorted[-1]  # 最新美股交易日
        return closes, latest_date
    except Exception as e:
        log.error(f"[E3X] {symbol} 获取失败: {e}")
        return None, None


def get_price_cached(symbol):
    """获取最新价（同一次run中缓存）"""
    if symbol in g.price_cache:
        return g.price_cache[symbol]
    time.sleep(13)
    closes, latest_date = fetch_av_daily(symbol, "compact")
    if closes:
        g.price_cache[symbol] = closes[-1]
        if latest_date:
            g.us_trade_date = latest_date  # 记录美股交易日
        return closes[-1]
    return None


# ============================================================
# 每日检查
# ============================================================
def daily_check(context):
    today = context.current_dt.strftime("%Y-%m-%d")
    g.price_cache = {}  # 清除缓存

    # 1. 获取 QQQ 数据
    qqq, qqq_latest_date = fetch_av_daily("QQQ", "full")
    if qqq_latest_date:
        g.us_trade_date = qqq_latest_date  # 美股实际交易日
    if not qqq or len(qqq) < 200:
        g.data_ok = False
        log.warn(f"[E3X] {today} QQQ数据不足200天 ({len(qqq) if qqq else 0})")
        send_nav_webhook(context, g.nav)
        return
    g.data_ok = True

    sma50 = sum(qqq[-50:]) / 50
    sma200 = sum(qqq[-200:]) / 200
    signal = "GOLDEN" if sma50 > sma200 else "DEATH"
    target = "TQQQ" if signal == "GOLDEN" else "SHY"

    # 2. 信号切换
    if signal != g.last_signal:
        old = g.last_signal

        # 平旧仓
        if g.holding and g.entry_price:
            exit_price = get_price_cached(g.holding)
            if exit_price:
                ret = exit_price / g.entry_price - 1
                g.nav *= (1 + ret)
                log.info(f"[E3X] 平仓 {g.holding} @{g.entry_price:.2f}→{exit_price:.2f} ret={ret*100:+.2f}%")

        # 开新仓
        entry_price = get_price_cached(target)
        if entry_price:
            g.holding = target
            g.entry_price = entry_price
            g.last_signal = signal
            log.info(f"[E3X] {old}→{signal} SMA50={sma50:.2f} SMA200={sma200:.2f} → {target}@{entry_price:.2f}")

            send_signal_webhook({
                "algo": ALGO_ID,
                "action": "LONG" if signal == "GOLDEN" else "SHORT",
                "symbol": target,
                "signalMode": "direction_switch",
                "notes": f"{signal} cross SMA50={sma50:.2f} SMA200={sma200:.2f} → {target}"
            })

        send_nav_webhook(context, g.nav)
        return

    # 3. 无变化 → 计算未实现NAV
    current_nav = g.nav
    if g.holding and g.entry_price:
        cur = get_price_cached(g.holding)
        if cur:
            current_nav = g.nav * (1 + cur / g.entry_price - 1)

    send_nav_webhook(context, current_nav)


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
        log.info(f"[E3X] Signal webhook: {resp.status_code}")
    except Exception as e:
        log.error(f"[E3X] Signal webhook error: {e}")


def send_nav_webhook(context, nav):
    # 使用AV返回的美股交易日，而非北京时间
    trade_date = g.us_trade_date or (context.current_dt - timedelta(days=1)).strftime('%Y-%m-%d')
    status = {
        "data_ok": g.data_ok,
        "signal": g.last_signal or "INIT",
        "holding": g.holding or "",
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
        log.info(f"[E3X] NAV: {nav:.6f} date={trade_date}")
    except Exception as e:
        log.error(f"[E3X] NAV webhook error: {e}")
