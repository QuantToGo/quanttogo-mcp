# ============================================================
# 独立策略：PCR 散户反指（JQ版）
# 平台：聚宽 (JoinQuant)
# 6只美股期权PCR信号，3-slot轮转，持有5天
# Algo ID: JQ-PCR
#
# 逻辑：
#   - 计算每只股票的60日PCR百分位
#   - PCR > 90th百分位 → 散户过度恐慌 → 反向做多
#   - 3个slot，持满5天自动平仓
#
# JQ不能交易美股 → 纯信号+手动NAV追踪
# 数据源：PCR → AV HISTORICAL_OPTIONS（Premium）
#         股价 → AV TIME_SERIES_DAILY
#
# 状态持久化：每日运行后保存到云端，重启自动恢复
# ============================================================

from jqdata import *
import requests
import numpy as np
import time
import json
from datetime import datetime, timedelta

WEBHOOK_URL = "https://www.quanttogo.com/receiveJQWebhook?token=b39b4e3e4cd2e55e8432d039e3112edf76d1ab4d7bb060feb42d2c4134362bc8"
ALGO_ID = "JQ-PCR"
AV_API_KEY = "VPC2QYD308YNNCDN"

PCR_TICKERS = ["SPY", "QQQ", "AMD", "AMZN", "META", "MSFT"]
PCR_HOLD_DAYS = 5
PCR_NUM_SLOTS = 3
PCR_LOOKBACK = 60
PCR_THRESHOLD_PCT = 90


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)

    # 默认值（首次运行或云端无状态时使用）
    g.slots = [None] * PCR_NUM_SLOTS
    g.pcr_history = {}    # ticker -> [(date, pcr), ...]
    g.last_fetch_date = None
    g.initial_capital = 100000
    g.cash = 100000.0
    g.price_cache = {}    # 当日价格缓存
    g.data_ok = True      # 数据获取状态
    g.us_trade_date = None  # 美股实际交易日
    g.state_loaded = False  # 是否已从云端恢复状态
    g.allow_save = True     # 加载失败时设为False，防止覆盖

    run_daily(daily_check, time='14:30')


# ============================================================
# 状态持久化
# ============================================================
def load_strategy_state():
    """从云端恢复策略状态（启动后首次运行时调用）
    返回: "ok" | "empty" | "error"
      ok    = 成功恢复，可以正常保存
      empty = 云端无状态（首次运行），可以正常保存
      error = 加载失败（网络/HTTP），禁止保存以防覆盖
    """
    try:
        resp = requests.post(WEBHOOK_URL, json={
            "algo": ALGO_ID,
            "event": "load_state"
        }, headers={"Content-Type": "application/json"}, timeout=15)

        if resp.status_code != 200:
            log.error(f"[PCR] Load state HTTP {resp.status_code}")
            return "error"

        data = resp.json()
        if data.get("code") != 0:
            log.error(f"[PCR] Load state 云函数错误: {data.get('message', '未知')}")
            return "error"
        state = data.get("state")
        if not state:
            log.info("[PCR] 云端无已保存状态，使用默认值")
            return "empty"

        # 恢复持仓
        g.slots = state.get("slots", g.slots)
        g.cash = state.get("cash", g.cash)
        g.initial_capital = state.get("initial_capital", g.initial_capital)
        g.last_fetch_date = state.get("last_fetch_date", g.last_fetch_date)
        g.us_trade_date = state.get("us_trade_date", g.us_trade_date)
        g.data_ok = state.get("data_ok", g.data_ok)

        # 恢复 pcr_history（JSON 里 tuple 变成了 list，需要转回 tuple）
        raw_history = state.get("pcr_history", {})
        g.pcr_history = {}
        for ticker, entries in raw_history.items():
            g.pcr_history[ticker] = [(e[0], e[1]) for e in entries]

        held = [s['ticker'] for s in g.slots if s]
        pcr_lens = {t: len(v) for t, v in g.pcr_history.items()}
        log.info(f"[PCR] ✅ 状态恢复: cash={g.cash:.2f} slots={held} pcr_history={pcr_lens}")
        return "ok"

    except Exception as e:
        log.error(f"[PCR] Load state failed: {e}，使用默认值，本次不保存状态")
        return "error"


def save_strategy_state():
    """将策略状态保存到云端（每日运行后调用）"""
    if not getattr(g, 'allow_save', True):
        log.warn("[PCR] ⚠️ 跳过保存：状态加载失败，防止覆盖云端数据")
        return
    state = {
        "slots": g.slots,
        "cash": round(g.cash, 2),
        "initial_capital": g.initial_capital,
        # 只保留最近 LOOKBACK 条，避免数据膨胀
        "pcr_history": {k: v[-PCR_LOOKBACK:] for k, v in g.pcr_history.items()},
        "last_fetch_date": g.last_fetch_date,
        "us_trade_date": g.us_trade_date,
        "data_ok": g.data_ok
    }
    try:
        resp = requests.post(WEBHOOK_URL, json={
            "algo": ALGO_ID,
            "event": "save_state",
            "state": state
        }, headers={"Content-Type": "application/json"}, timeout=10)
        log.info(f"[PCR] State saved: {resp.status_code}")
    except Exception as e:
        log.error(f"[PCR] Save state failed: {e}")


# ============================================================
# 数据获取
# ============================================================
def get_stock_price(symbol):
    """获取最新股价（带缓存），同时记录美股交易日"""
    if symbol in g.price_cache:
        return g.price_cache[symbol]
    time.sleep(13)
    try:
        resp = requests.get("https://www.alphavantage.co/query", params={
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": "compact",
            "apikey": AV_API_KEY,
        }, timeout=30)
        ts = resp.json().get("Time Series (Daily)", {})
        if not ts:
            return None
        latest = sorted(ts.keys())[-1]
        g.us_trade_date = latest  # 记录美股交易日
        price = float(ts[latest]["4. close"])
        g.price_cache[symbol] = price
        return price
    except Exception as e:
        log.error(f"[PCR] {symbol} 价格获取失败: {e}")
        return None


def fetch_today_pcr(symbol):
    """获取最新交易日的PCR"""
    try:
        resp = requests.get("https://www.alphavantage.co/query", params={
            "function": "HISTORICAL_OPTIONS",
            "symbol": symbol,
            "apikey": AV_API_KEY,
        }, timeout=20)
        result = resp.json()
        options = result.get("data", [])
        if not options:
            note = result.get("Note") or result.get("Information") or ""
            if note:
                log.warn(f"[PCR] AV限频: {note[:80]}")
            return None

        put_vol, call_vol = 0, 0
        data_date = options[0].get("date", "")
        for opt in options:
            if opt.get("date") != data_date:
                continue
            vol = float(opt.get("volume", 0) or 0)
            opt_type = (opt.get("type") or "").lower()
            if opt_type == "put":
                put_vol += vol
            elif opt_type == "call":
                call_vol += vol

        if call_vol > 0:
            return (data_date, put_vol / call_vol)
        return None
    except Exception as e:
        log.error(f"[PCR] {symbol} PCR获取失败: {e}")
        return None


# ============================================================
# 每日检查
# ============================================================
def daily_check(context):
    today = context.current_dt.strftime("%Y-%m-%d")

    # ── 防御性初始化：JQ容器重启后g被清空但initialize未重新调用 ──
    if not hasattr(g, 'state_loaded'):
        log.warn("[PCR] ⚠️ g 未初始化（JQ容器可能重启），执行内联初始化")
        g.slots = [None] * PCR_NUM_SLOTS
        g.pcr_history = {}
        g.last_fetch_date = None
        g.initial_capital = 100000
        g.cash = 100000.0
        g.data_ok = True
        g.us_trade_date = None
        g.state_loaded = False
        g.allow_save = True

    g.price_cache = {}

    # ── 首次运行：从云端恢复状态 ──
    if not g.state_loaded:
        result = load_strategy_state()
        g.state_loaded = True
        # 加载失败时禁止保存，防止默认值覆盖云端好数据
        g.allow_save = (result != "error")
        if result == "error":
            log.warn("[PCR] ⚠️ 状态加载失败，本次运行结束后不保存状态")

    # ── 0. 获取美股交易日（始终获取SPY价格，即使无持仓） ──
    spy_price = get_stock_price("SPY")
    if spy_price:
        log.info(f"[PCR] SPY={spy_price:.2f} us_trade_date={g.us_trade_date}")
    else:
        log.warn(f"[PCR] ⚠️ SPY价格获取失败，us_trade_date={g.us_trade_date}")

    # 刷新其他持仓价格
    held_tickers = list(set(s['ticker'] for s in g.slots if s))
    for ticker in held_tickers:
        if ticker != "SPY":  # SPY已获取，避免重复
            get_stock_price(ticker)
    if held_tickers:
        log.info(f"[PCR] 持仓价格刷新: {len(held_tickers)}只")

    # ── 1. 到期平仓 ──
    for i in range(PCR_NUM_SLOTS):
        slot = g.slots[i]
        if slot is None:
            continue
        slot['days_held'] += 1
        if slot['days_held'] >= PCR_HOLD_DAYS:
            ticker = slot['ticker']
            exit_price = get_stock_price(ticker) or slot['entry_price']
            proceeds = slot['shares'] * exit_price
            g.cash += proceeds
            gr = (exit_price / slot['entry_price'] - 1) * 100

            log.info(f"[PCR] CLOSE [{i}] {ticker} @{slot['entry_price']:.2f}→{exit_price:.2f} {gr:+.2f}%")
            send_signal_webhook({
                "algo": ALGO_ID,
                "action": "SELL",
                "symbol": ticker,
                "signalMode": "timed_exit",
                "slot": i + 1,
                "notes": f"5天到期 @{slot['entry_price']:.2f}→{exit_price:.2f} {gr:+.2f}%"
            })
            g.slots[i] = None

    # ── 2. 获取PCR（每天一次） ──
    if g.last_fetch_date == today:
        send_nav_webhook(context)
        save_strategy_state()
        return
    g.last_fetch_date = today

    fetched = 0
    for ticker in PCR_TICKERS:
        time.sleep(13)
        result = fetch_today_pcr(ticker)
        if result:
            pcr_date, pcr_val = result
            if ticker not in g.pcr_history:
                g.pcr_history[ticker] = []
            hist = g.pcr_history[ticker]
            if not hist or hist[-1] != (pcr_date, pcr_val):
                hist.append((pcr_date, pcr_val))
            fetched += 1

    g.data_ok = fetched > 0
    hist_lens = {t: len(g.pcr_history.get(t, [])) for t in PCR_TICKERS}
    log.info(f"[PCR] 获取{fetched}/{len(PCR_TICKERS)} 累积: {hist_lens}")

    # ── 3. 生成信号 ──
    signals = []
    for ticker in PCR_TICKERS:
        hist = g.pcr_history.get(ticker, [])
        if len(hist) < PCR_LOOKBACK:
            continue
        pcr_values = [v for _, v in hist[-PCR_LOOKBACK:]]
        today_pcr = pcr_values[-1]
        threshold = float(np.percentile(pcr_values, PCR_THRESHOLD_PCT))
        if today_pcr >= threshold:
            pct_rank = sum(1 for p in pcr_values if p <= today_pcr) / len(pcr_values) * 100
            signals.append((ticker, today_pcr, pct_rank))

    signals.sort(key=lambda x: -x[2])

    # ── 4. 填充空slot ──
    empty_slots = [i for i in range(PCR_NUM_SLOTS) if g.slots[i] is None]
    for sig in signals:
        if not empty_slots:
            break
        ticker, pcr_val, prank = sig

        # 跳过已持仓
        if any(s and s['ticker'] == ticker for s in g.slots):
            continue

        price = get_stock_price(ticker)
        if not price or price <= 0:
            continue

        idx = empty_slots.pop(0)
        slot_alloc = g.initial_capital / PCR_NUM_SLOTS
        shares = int(slot_alloc / price)
        if shares <= 0:
            continue

        cost = shares * price
        g.cash -= cost
        g.slots[idx] = {
            'ticker': ticker,
            'entry_price': price,
            'shares': shares,
            'days_held': 0,
        }

        log.info(f"[PCR] OPEN [{idx}] {ticker} @{price:.2f} x{shares} PCR={pcr_val:.4f} P{prank:.0f}")
        send_signal_webhook({
            "algo": ALGO_ID,
            "action": "BUY",
            "symbol": ticker,
            "signalMode": "timed_exit",
            "slot": idx + 1,
            "notes": f"PCR={pcr_val:.4f} P{prank:.0f} slot{idx+1} 5天后平仓"
        })

    send_nav_webhook(context)
    save_strategy_state()


# ============================================================
# 日期验证
# ============================================================
def get_valid_trade_date():
    """获取有效的美股交易日，确保不返回周末日期"""
    date_str = g.us_trade_date
    if date_str:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            weekday = dt.weekday()  # 0=Mon ... 6=Sun
            if weekday == 5:  # Saturday → 回退到 Friday
                date_str = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
                log.warn(f"[PCR] us_trade_date 是周六({g.us_trade_date})，修正为{date_str}")
            elif weekday == 6:  # Sunday → 回退到 Friday
                date_str = (dt - timedelta(days=2)).strftime("%Y-%m-%d")
                log.warn(f"[PCR] us_trade_date 是周日({g.us_trade_date})，修正为{date_str}")
            return date_str
        except Exception:
            pass
    return None


# ============================================================
# NAV
# ============================================================
def calc_nav():
    total = g.cash
    for slot in g.slots:
        if slot:
            price = g.price_cache.get(slot['ticker'])
            if not price:
                price = slot['entry_price']  # fallback
            total += slot['shares'] * price
    return total / g.initial_capital


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
        log.info(f"[PCR] Signal webhook: {resp.status_code}")
    except Exception as e:
        log.error(f"[PCR] Signal webhook error: {e}")


def send_nav_webhook(context):
    # 优先使用AV返回的美股交易日（经过周末验证），fallback用JQ上一交易日
    trade_date = get_valid_trade_date() or context.previous_date.strftime('%Y-%m-%d')
    log.info(f"[PCR] NAV日期: trade_date={trade_date} (us_trade_date={g.us_trade_date}, fallback={context.previous_date})")
    nav = calc_nav()
    held = [s['ticker'] for s in g.slots if s]
    status = {
        "data_ok": g.data_ok,
        "signal": f"slots={len(held)}/3",
        "holding": ",".join(held) if held else "",
        "error": "PCR数据获取失败" if not g.data_ok else None
    }
    try:
        payload = {
            "algo": ALGO_ID,
            "event": "daily_nav",
            "nav": round(nav, 6),
            "date": trade_date,
            "total_value": round(nav * g.initial_capital, 2),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": datetime.now().isoformat(),
            "status": status
        }
        requests.post(WEBHOOK_URL, json=payload,
                     headers={"Content-Type": "application/json"}, timeout=5)
        log.info(f"[PCR] NAV: {nav:.6f} date={trade_date}")
    except Exception as e:
        log.error(f"[PCR] NAV webhook error: {e}")
