# ============================================================
# 独立策略：A股跌停抄底
# 平台：聚宽 (JoinQuant)
# 单股票账户，交易创业板ETF
# Algo ID: JQ-DIP-BUY
# ============================================================

from jqdata import *
import numpy as np
import pandas as pd
from datetime import datetime
import requests
import json

WEBHOOK_URL = "https://www.quanttogo.com/receiveJQWebhook?token=b39b4e3e4cd2e55e8432d039e3112edf76d1ab4d7bb060feb42d2c4134362bc8"
ALGO_ID = "JQ-DIP-BUY"


def initialize(context):
    set_benchmark('399006.XSHE')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)

    # ETF手续费
    set_order_cost(OrderCost(
        open_tax=0, close_tax=0,
        open_commission=0.0003, close_commission=0.0003,
        min_commission=5
    ), type='fund')

    set_slippage(FixedSlippage(0.02))

    # 策略参数
    g.dip_etf = '159915.XSHE'
    g.dip_index = '399006.XSHE'
    g.dip_threshold = 0.10
    g.dip_dedup_days = 20
    g.dip_hold_days = 20
    g.dip_profit_taking_days = 5
    g.dip_profit_taking_threshold = 0.15

    g.nav_base = 2.2216                          # QC最终NAV(2025-12-31)
    g.dip_last_signal_date = None
    g.dip_holding = False
    g.dip_buy_date = None
    g.dip_hold_count = 0
    g.dip_pending_buy = False
    g.dip_signal_info = {}

    # 调度
    run_daily(dip_check_signal, time='after_close')
    run_daily(dip_execute_trade, time='open')
    run_daily(send_daily_nav, time='after_close')


# ============================================================
# 信号检查（收盘后）
# ============================================================
def dip_check_signal(context):
    today = context.current_dt.date()

    if g.dip_holding:
        return

    if g.dip_last_signal_date is not None:
        gap = (today - g.dip_last_signal_date).days
        if gap < g.dip_dedup_days:
            return

    ld_pct = dip_calc_limit_down_pct(today)
    if ld_pct is None or ld_pct <= g.dip_threshold:
        return

    ret_5d = dip_calc_prior_return(today, g.dip_profit_taking_days)
    if ret_5d is not None and ret_5d > g.dip_profit_taking_threshold:
        log.info(f"[抄底] 信号触发但被过滤 {today} 跌停{ld_pct:.1%}, 前5日涨幅{ret_5d:.1%} > 15%, 跳过")
        g.dip_last_signal_date = today
        return

    g.dip_pending_buy = True
    g.dip_last_signal_date = today
    g.dip_signal_info = {'signal_date': str(today), 'ld_pct': ld_pct, 'ret_5d': ret_5d}
    log.info(f"[抄底] 信号触发 {today} 跌停{ld_pct:.1%} → 明日开盘买入")


# ============================================================
# 交易执行（开盘）
# ============================================================
def dip_execute_trade(context):
    today = context.current_dt.date()

    # 卖出：持仓满20个交易日
    if g.dip_holding:
        g.dip_hold_count += 1
        if g.dip_hold_count > g.dip_hold_days:
            pos = context.portfolio.positions.get(g.dip_etf)
            if pos and pos.closeable_amount > 0:
                order_target(g.dip_etf, 0)
                log.info(f"[抄底] 卖出 {today} 持有{g.dip_hold_count-1}天, 买入日{g.dip_buy_date}")
                send_webhook('sell', g.dip_etf, 0,
                            notes=f'A股抄底卖出 {g.dip_etf} 持有{g.dip_hold_count-1}天')
            g.dip_holding = False
            g.dip_buy_date = None
            g.dip_hold_count = 0
            return

    # 买入：有待执行的信号
    if g.dip_pending_buy:
        g.dip_pending_buy = False
        cash = context.portfolio.available_cash
        if cash > 1000:
            order_value(g.dip_etf, cash * 0.99)
            g.dip_holding = True
            g.dip_buy_date = today
            g.dip_hold_count = 1
            log.info(f"[抄底] 买入 {today} 跌停{g.dip_signal_info.get('ld_pct', 0):.1%}")
            send_webhook('buy', g.dip_etf, 0,
                        notes=f'A股抄底买入 {g.dip_etf} 跌停{g.dip_signal_info.get("ld_pct", 0):.1%}')
        else:
            log.warn(f"[抄底] 买入失败 {today} 资金不足: {cash:.2f}")


# ============================================================
# 辅助计算
# ============================================================
def dip_calc_limit_down_pct(date):
    try:
        stocks = get_all_securities(types=['stock'], date=date)
        stocks = stocks[stocks.index.str.startswith(('0', '3', '6'))]
        if len(stocks) == 0:
            return None

        code_list = list(stocks.index)
        df = get_price(code_list, end_date=date, count=1,
                       fields=['close', 'low_limit', 'paused'],
                       skip_paused=False, panel=False)
        df = df[df['paused'] == 0]
        if len(df) == 0:
            return None

        limit_down_count = (df['close'] <= df['low_limit'] * 1.001).sum()
        return limit_down_count / len(df)
    except Exception as e:
        log.error(f"[抄底] 计算跌停占比失败 {date}: {e}")
        return None


def dip_calc_prior_return(date, n_days):
    try:
        df = get_price(g.dip_index, end_date=date, count=n_days + 1,
                       fields=['close'], frequency='daily')
        if len(df) < n_days + 1:
            return None
        return df['close'].iloc[-1] / df['close'].iloc[0] - 1
    except Exception as e:
        log.error(f"[抄底] 计算前{n_days}日涨幅失败 {date}: {e}")
        return None


# ============================================================
# Webhook
# ============================================================
def send_webhook(action, symbol, quantity, price=0, notes=''):
    try:
        payload = {
            "algo": ALGO_ID,
            "strategy_id": ALGO_ID,
            "action": action.lower(),
            "event": "order_fill",
            "symbol": symbol,
            "qty": quantity,
            "quantity": quantity,
            "price": float(price) if price else 0,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": datetime.now().isoformat(),
            "notes": notes
        }
        response = requests.post(
            WEBHOOK_URL, json=payload,
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 0:
                log.info(f"Webhook OK: {ALGO_ID} {action} {symbol}")
            else:
                log.warn(f"Webhook err: {result.get('message')}")
        else:
            log.error(f"Webhook HTTP {response.status_code}")
    except Exception as e:
        log.error(f"Webhook exception: {str(e)}")


def send_daily_nav(context):
    nav = g.nav_base * context.portfolio.total_value / context.portfolio.starting_cash
    status = {
        "data_ok": True,
        "signal": "HOLDING" if g.dip_holding else "WAITING",
        "holding": g.dip_etf if g.dip_holding else "",
        "error": None
    }
    try:
        payload = {
            "algo": ALGO_ID,
            "event": "daily_nav",
            "nav": round(nav, 6),
            "date": context.current_dt.strftime('%Y-%m-%d'),
            "total_value": round(context.portfolio.total_value, 2),
            "time": context.current_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": context.current_dt.isoformat(),
            "status": status
        }
        requests.post(WEBHOOK_URL, json=payload,
                     headers={"Content-Type": "application/json"}, timeout=5)
        log.info(f"NAV: {ALGO_ID} {nav:.6f}")
    except Exception as e:
        log.error(f"NAV exception: {e}")
