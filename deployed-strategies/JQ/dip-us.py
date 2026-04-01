# ============================================================
# 独立策略：US Dip Buying VIX恐慌抄底（JQ版）
# 平台：聚宽 (JoinQuant)
# 信号模式：VIX > 35 买入 TQQQ，VIX < 20 卖出
# Algo ID: JQ-DIP-US
#
# JQ不能交易美股 → 纯信号+手动NAV追踪
# 数据源：VIX → FRED VIXCLS，TQQQ → Alpha Vantage
# ============================================================

from jqdata import *
import requests
import time
from datetime import datetime, timedelta

WEBHOOK_URL = "https://www.quanttogo.com/receiveJQWebhook?token=b39b4e3e4cd2e55e8432d039e3112edf76d1ab4d7bb060feb42d2c4134362bc8"
ALGO_ID = "JQ-DIP-US"
AV_API_KEY = "VPC2QYD308YNNCDN"
FRED_API_KEY = "59091e0d0981151e92593a3c0d391f8b"

DIP_VIX_ENTRY = 35
DIP_VIX_EXIT = 20


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)

    g.in_position = False
    g.entry_price = None
    g.nav = 11.353293              # backfill最终NAV(2026-03-05) TQQQ版
    g.last_vix = None
    g.trade_count = 6
    g.data_ok = True
    g.us_trade_date = None  # 美股实际交易日

    run_daily(daily_check, time='14:10')


# ============================================================
# 数据获取
# ============================================================
def fetch_vix():
    """FRED获取最新VIX"""
    try:
        url = (
            "https://api.stlouisfed.org/fred/series/observations"
            f"?series_id=VIXCLS&api_key={FRED_API_KEY}"
            "&file_type=json&sort_order=desc&limit=5"
        )
        resp = requests.get(url, timeout=10)
        for obs in resp.json().get("observations", []):
            val = obs.get("value", ".")
            if val != ".":
                vix = float(val)
                log.info(f"[DIP-US] VIX={vix:.2f} ({obs.get('date')})")
                return vix
        return None
    except Exception as e:
        log.error(f"[DIP-US] VIX获取失败: {e}")
        return None


def fetch_tqqq_price():
    """AV获取TQQQ最新价，同时记录美股交易日"""
    try:
        resp = requests.get("https://www.alphavantage.co/query", params={
            "function": "TIME_SERIES_DAILY",
            "symbol": "TQQQ",
            "outputsize": "compact",
            "apikey": AV_API_KEY,
        }, timeout=30)
        ts = resp.json().get("Time Series (Daily)", {})
        if not ts:
            return None
        latest = sorted(ts.keys())[-1]
        g.us_trade_date = latest  # 记录美股交易日
        return float(ts[latest]["4. close"])
    except Exception as e:
        log.error(f"[DIP-US] TQQQ获取失败: {e}")
        return None


# ============================================================
# 每日检查
# ============================================================
def daily_check(context):
    today = context.current_dt.strftime("%Y-%m-%d")

    # 获取VIX
    vix = fetch_vix()
    if vix is None:
        g.data_ok = False
        log.warn(f"[DIP-US] {today} VIX获取失败，跳过")
        send_nav_webhook(context)
        return
    g.last_vix = vix

    time.sleep(13)
    tqqq_price = fetch_tqqq_price()
    if tqqq_price is None:
        g.data_ok = False
        log.warn(f"[DIP-US] {today} TQQQ价格获取失败")
        send_nav_webhook(context)
        return
    g.data_ok = True

    # 信号判断
    if not g.in_position:
        if vix > DIP_VIX_ENTRY:
            g.in_position = True
            g.entry_price = tqqq_price
            g.trade_count += 1
            log.info(f"[DIP-US] BUY #{g.trade_count} TQQQ@{tqqq_price:.2f} VIX={vix:.1f}")

            send_signal_webhook({
                "algo": ALGO_ID,
                "action": "BUY",
                "symbol": "TQQQ",
                "signalMode": "direction_switch",
                "notes": f"VIX={vix:.1f} > {DIP_VIX_ENTRY}, buy TQQQ@{tqqq_price:.2f}"
            })
    else:
        if vix < DIP_VIX_EXIT:
            ret = (tqqq_price / g.entry_price - 1) if g.entry_price else 0
            g.nav *= (1 + ret)
            log.info(f"[DIP-US] SELL #{g.trade_count} TQQQ@{g.entry_price:.2f}→{tqqq_price:.2f} ret={ret*100:+.2f}% VIX={vix:.1f}")

            send_signal_webhook({
                "algo": ALGO_ID,
                "action": "SELL",
                "symbol": "TQQQ",
                "signalMode": "direction_switch",
                "notes": f"VIX={vix:.1f} < {DIP_VIX_EXIT}, sell TQQQ ret={ret*100:+.2f}%"
            })

            g.in_position = False
            g.entry_price = None

    send_nav_webhook(context, tqqq_price)


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
        log.info(f"[DIP-US] Signal webhook: {resp.status_code}")
    except Exception as e:
        log.error(f"[DIP-US] Signal webhook error: {e}")


def send_nav_webhook(context, tqqq_price=None):
    # 使用AV返回的美股交易日
    trade_date = g.us_trade_date or (context.current_dt - timedelta(days=1)).strftime('%Y-%m-%d')
    current_nav = g.nav
    if g.in_position and g.entry_price and tqqq_price:
        unrealized = tqqq_price / g.entry_price - 1
        current_nav = g.nav * (1 + unrealized)
    status = {
        "data_ok": g.data_ok,
        "signal": f"VIX={g.last_vix:.1f}" if g.last_vix else "NO_DATA",
        "holding": "TQQQ" if g.in_position else "",
        "error": "数据获取失败" if not g.data_ok else None
    }
    try:
        payload = {
            "algo": ALGO_ID,
            "event": "daily_nav",
            "nav": round(current_nav, 6),
            "date": trade_date,
            "total_value": round(current_nav * 100000, 2),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": datetime.now().isoformat(),
            "status": status
        }
        requests.post(WEBHOOK_URL, json=payload,
                     headers={"Content-Type": "application/json"}, timeout=5)
        log.info(f"[DIP-US] NAV: {current_nav:.6f} date={trade_date}")
    except Exception as e:
        log.error(f"[DIP-US] NAV webhook error: {e}")
