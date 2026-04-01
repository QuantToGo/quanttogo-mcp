# ============================================================
# 独立策略：在岸人民币-IF 多空 v2 (平仓复利NAV + 死区过滤)
# 平台：聚宽 (JoinQuant)
# 单期货账户，无子账户
# Algo ID: JQ-CNY-IF
#
# v2-260314 变更：
#   - NAV改为平仓复利（与CHAU一致），仅平仓时更新g.nav_value
#   - 每日webhook发送mark-to-market NAV（不修改基础NAV）
#   - 新增死区过滤 DEADZONE_PCT=0.1%，过滤边缘噪声信号
#   - 删除旧版影子NAV机制（REF_CONTRACTS/ref_value/effective等）
#   - 动态仓位、换月、webhook格式不变
# ============================================================

from jqdata import *
from jqdata import macro
import numpy as np
import requests
import json
from datetime import datetime

WEBHOOK_URL = "https://www.quanttogo.com/receiveJQWebhook?token=b39b4e3e4cd2e55e8432d039e3112edf76d1ab4d7bb060feb42d2c4134362bc8"
ALGO_ID = "JQ-CNY-IF"

# 合约参数
MARGIN_RATE = 0.15               # JQ保证金率(IF为15%)
IF_MULTIPLIER = 300              # IF合约乘数

# NAV参数
LEVERAGE_RATIO = 2               # 杠杆倍数(2=等效CHAU两倍做多)
# 仓位按杠杆倍数计算: 名义市值 = 账户总值 × LEVERAGE_RATIO
# 保证金占比 = LEVERAGE_RATIO × MARGIN_RATE = 30%

# 死区过滤
DEADZONE_PCT = 0.001             # 0.1%，与CHAU一致


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)

    # 单期货账户
    set_subportfolios([
        SubPortfolioConfig(cash=context.portfolio.starting_cash, type='index_futures')
    ])

    set_order_cost(OrderCost(
        open_commission=0.000023,
        close_commission=0.000023,
        close_today_commission=0.000345,
        min_commission=0
    ), type='index_futures')

    set_slippage(FixedSlippage(0))

    # === 信号预设（从2020-01-01~2026-03-13回测提取）===
    context.cny_sma_short = 5
    context.cny_sma_mid = 10
    context.cny_sma_long = 30
    context.cny_current_signal = 'SHORT'           # 回测最终信号(2026-03-13)
    context.cny_prev_signal = 'SHORT'              # 同上，首日自动开仓(无持仓→rebalance)
    context.cny_current_contract = None

    # === 平仓复利NAV（从回测提取）===
    g.nav_value = 8.074748           # 最后实现NAV(2026-03-13平仓)
    g.direction = 'NONE'            # 新实例无持仓，首日rebalance后变SHORT
    g.if_entry_price = None          # 首日开仓时设定
    g.current_contracts = 0

    # 调度
    run_daily(cny_check_signal, time='09:00', reference_security='000300.XSHG')
    run_daily(cny_execute_trade, time='09:31', reference_security='000300.XSHG')
    run_daily(send_daily_nav, time='after_close')


# ============================================================
# 动态仓位计算
# ============================================================
def calc_num_contracts(context):
    """按ETF杠杆倍数计算IF开仓手数: 名义市值 = 账户总值 × LEVERAGE_RATIO"""
    total = context.subportfolios[0].total_value
    target_notional = total * LEVERAGE_RATIO

    if_dom = get_dominant_future('IF')
    if_data = get_price(if_dom, end_date=context.previous_date, count=1, fields=['close'])

    if if_data is None or len(if_data) == 0:
        log.warn('[CNY-IF] 无法获取IF价格，默认1手')
        return 1

    if_price = if_data['close'].iloc[-1]
    contract_notional = if_price * IF_MULTIPLIER

    n = int(target_notional / contract_notional)

    if n < 1:
        log.warn('[CNY-IF] 资金不足 总值%.0f 每手名义%.0f' % (total, contract_notional))
        return 0

    actual_notional = n * contract_notional
    margin_used = actual_notional * MARGIN_RATE
    log.info('[CNY-IF] ETF仓位: %d手 名义%.0f(%.1fx) 保证金%.0f(%.0f%%) 总值%.0f'
             % (n, actual_notional, actual_notional / total,
                margin_used, margin_used / total * 100, total))
    return n


# ============================================================
# USD/CNY 数据获取
# ============================================================
def cny_get_usdcny_data(context, count):
    end_date = context.current_dt.strftime('%Y-%m-%d')
    q = query(
        macro.MAC_RMB_EXCHANGE_RATE.day,
        macro.MAC_RMB_EXCHANGE_RATE.cash_buy_rate
    ).filter(
        macro.MAC_RMB_EXCHANGE_RATE.currency_id == 40,
        macro.MAC_RMB_EXCHANGE_RATE.day <= end_date
    ).order_by(
        macro.MAC_RMB_EXCHANGE_RATE.day.desc()
    ).limit(count + 10)

    df = macro.run_query(q)
    if df is None or df.empty:
        return None
    df = df.sort_values('day').reset_index(drop=True)
    df['cash_buy_rate'] = df['cash_buy_rate'].astype(float)
    return df


# ============================================================
# 平仓复利NAV
# ============================================================
def nav_close_position(exit_price):
    """平仓时更新NAV：计算持仓期间收益率，乘法复利"""
    if g.direction == 'NONE' or g.if_entry_price is None or exit_price is None:
        return
    move = (exit_price - g.if_entry_price) / g.if_entry_price * LEVERAGE_RATIO
    if g.direction == 'SHORT':
        move = -move
    g.nav_value *= (1 + move)
    log.info('[CNY-IF] 平仓NAV: entry=%.2f exit=%.2f dir=%s move=%.4f nav=%.6f'
             % (g.if_entry_price, exit_price, g.direction, move, g.nav_value))
    g.if_entry_price = None
    g.direction = 'NONE'


def calc_mark_to_market_nav(current_if_price):
    """计算mark-to-market NAV（不修改基础NAV）"""
    if g.direction == 'NONE' or g.if_entry_price is None or current_if_price is None:
        return g.nav_value
    move = (current_if_price - g.if_entry_price) / g.if_entry_price * LEVERAGE_RATIO
    if g.direction == 'SHORT':
        move = -move
    return g.nav_value * (1 + move)


def get_today_open(context, security):
    """获取今日开盘价（用于近似交易价）"""
    data = get_price(security, end_date=context.current_dt,
                     count=1, fields=['open'])
    if data is not None and len(data) > 0:
        return data['open'].iloc[-1]
    return None


# ============================================================
# 信号检查（含死区过滤）
# ============================================================
def cny_check_signal(context):
    df = cny_get_usdcny_data(context, context.cny_sma_long + 5)
    if df is None or len(df) < context.cny_sma_long:
        return

    rates = df['cash_buy_rate'].values
    current = rates[-1]
    sma5 = rates[-context.cny_sma_short:].mean()
    sma10 = rates[-context.cny_sma_mid:].mean()
    sma30 = rates[-context.cny_sma_long:].mean()

    context.cny_prev_signal = context.cny_current_signal

    below_all = current < sma5 and current < sma10 and current < sma30
    above_all = current > sma5 and current > sma10 and current > sma30

    if below_all or above_all:
        # 死区过滤：信号边缘太近则忽略
        if below_all:
            nearest_ma = min(sma5, sma10, sma30)
        else:
            nearest_ma = max(sma5, sma10, sma30)
        distance_pct = abs(current - nearest_ma) / current
        if distance_pct < DEADZONE_PCT:
            return  # 在死区内，不切换信号

        if below_all:
            context.cny_current_signal = 'LONG'
        elif above_all:
            context.cny_current_signal = 'SHORT'

    if context.cny_current_signal != context.cny_prev_signal:
        log.info('[CNY-IF] 信号切换: %s -> %s' % (context.cny_prev_signal, context.cny_current_signal))
        log.info('  USDCNY: %.2f  SMA5: %.2f  SMA10: %.2f  SMA30: %.2f' % (current, sma5, sma10, sma30))


# ============================================================
# 交易执行
# ============================================================
def cny_execute_trade(context):
    dominant = get_dominant_future('IF')
    if dominant == '':
        return

    # --- 合约换月处理（含NAV平仓）---
    if context.cny_current_contract is not None and context.cny_current_contract != dominant:
        old_contract = context.cny_current_contract
        has_old_long = old_contract in context.subportfolios[0].long_positions and \
                       context.subportfolios[0].long_positions[old_contract].total_amount > 0
        has_old_short = old_contract in context.subportfolios[0].short_positions and \
                        context.subportfolios[0].short_positions[old_contract].total_amount > 0

        if has_old_long or has_old_short:
            # 换月平仓 → 更新NAV
            roll_exit_price = get_today_open(context, old_contract)
            nav_close_position(roll_exit_price)

            if has_old_long:
                amt = context.subportfolios[0].long_positions[old_contract].total_amount
                order_target(old_contract, 0, side='long', pindex=0)
                order(dominant, amt, side='long', pindex=0)
                g.direction = 'LONG'
                log.info('[CNY-IF] 换月: long %s %d手 -> %s' % (old_contract, amt, dominant))
            elif has_old_short:
                amt = context.subportfolios[0].short_positions[old_contract].total_amount
                order_target(old_contract, 0, side='short', pindex=0)
                order(dominant, amt, side='short', pindex=0)
                g.direction = 'SHORT'
                log.info('[CNY-IF] 换月: short %s %d手 -> %s' % (old_contract, amt, dominant))

            # 新合约开仓价
            g.if_entry_price = get_today_open(context, dominant)
            log.info('[CNY-IF] 换月entry=%.2f' % (g.if_entry_price or 0))

        context.cny_current_contract = dominant
        if context.cny_current_signal == context.cny_prev_signal:
            return

    context.cny_current_contract = dominant

    has_long = dominant in context.subportfolios[0].long_positions and \
               context.subportfolios[0].long_positions[dominant].total_amount > 0
    has_short = dominant in context.subportfolios[0].short_positions and \
                context.subportfolios[0].short_positions[dominant].total_amount > 0

    if context.cny_current_signal == 'LONG':
        if has_short:
            # 平空仓 → 更新NAV
            close_price = get_today_open(context, dominant)
            nav_close_position(close_price)
            order_target(dominant, 0, side='short', pindex=0)
            log.info('[CNY-IF] 平空: %s' % dominant)
        if not has_long:
            n = calc_num_contracts(context)
            if n == 0:
                return
            order(dominant, n, side='long', pindex=0)
            g.current_contracts = n
            g.if_entry_price = get_today_open(context, dominant)
            g.direction = 'LONG'
            log.info('[CNY-IF] 开多 %d手: %s entry=%.2f'
                     % (n, dominant, g.if_entry_price or 0))
            send_webhook('buy', dominant, n,
                        notes='CNY-IF 开多 %d手 %s' % (n, dominant))

    elif context.cny_current_signal == 'SHORT':
        if has_long:
            # 平多仓 → 更新NAV
            close_price = get_today_open(context, dominant)
            nav_close_position(close_price)
            order_target(dominant, 0, side='long', pindex=0)
            log.info('[CNY-IF] 平多: %s' % dominant)
        if not has_short:
            n = calc_num_contracts(context)
            if n == 0:
                return
            order(dominant, n, side='short', pindex=0)
            g.current_contracts = n
            g.if_entry_price = get_today_open(context, dominant)
            g.direction = 'SHORT'
            log.info('[CNY-IF] 开空 %d手: %s entry=%.2f'
                     % (n, dominant, g.if_entry_price or 0))
            send_webhook('sell', dominant, n,
                        notes='CNY-IF 开空 %d手 %s' % (n, dominant))


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
    # Mark-to-market NAV（不修改基础g.nav_value）
    if_dom = get_dominant_future('IF')
    if_data = get_price(if_dom, end_date=context.current_dt,
                        count=1, fields=['close'])
    if if_data is not None and len(if_data) > 0:
        current_if_price = if_data['close'].iloc[-1]
    else:
        current_if_price = None

    nav = calc_mark_to_market_nav(current_if_price)
    total = context.subportfolios[0].total_value

    status = {
        "data_ok": True,
        "signal": context.cny_current_signal,
        "holding": context.cny_current_contract or "",
        "contracts": g.current_contracts,
        "direction": g.direction,
        "entry_price": round(g.if_entry_price, 2) if g.if_entry_price else None,
        "nav_realized": round(g.nav_value, 6),
        "error": None
    }
    try:
        payload = {
            "algo": ALGO_ID,
            "event": "daily_nav",
            "nav": round(nav, 6),
            "date": context.current_dt.strftime('%Y-%m-%d'),
            "total_value": round(total, 2),
            "time": context.current_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": context.current_dt.isoformat(),
            "status": status
        }
        requests.post(WEBHOOK_URL, json=payload,
                     headers={"Content-Type": "application/json"}, timeout=5)
        log.info('[CNY-IF] NAV=%.6f (realized=%.6f, dir=%s, n=%d, total=%.0f)'
                 % (nav, g.nav_value, g.direction, g.current_contracts, total))
    except Exception as e:
        log.error(f"NAV exception: {e}")
