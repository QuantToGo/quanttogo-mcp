# ============================================================
# 独立策略：双流动性 IF-IC 轮动 v4 (平仓复利NAV + 死区过滤)
# 平台：聚宽 (JoinQuant)
# 单期货账户，无子账户
# Algo ID: JQ-IF-IC
#
# v4-260314 变更：
#   - NAV改为平仓复利（与CHAU一致），仅象限切换平仓时更新g.nav_value
#   - 每日webhook发送mark-to-market NAV（不修改基础NAV）
#   - CNY信号新增死区过滤 DEADZONE_PCT=0.1%
#   - 删除旧版影子NAV机制（REF_CONTRACTS/ref_value/effective等）
#   - 删除止损（双向策略无意义）
#   - 动态仓位改为ETF杠杆模式（LEVERAGE_RATIO=2）
#   - 换月、webhook格式不变
# ============================================================

from jqdata import *
from jqdata import macro
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import requests
import json

WEBHOOK_URL = "https://www.quanttogo.com/receiveJQWebhook?token=b39b4e3e4cd2e55e8432d039e3112edf76d1ab4d7bb060feb42d2c4134362bc8"
ALGO_ID = "JQ-IF-IC"

# 策略参数
SHIBOR_CONFIRM = 5

# 合约参数
MARGIN_RATE = 0.15               # JQ保证金率(IF/IC均为15%)
IF_MULTIPLIER = 300              # IF合约乘数
IC_MULTIPLIER = 200              # IC合约乘数

# NAV参数
LEVERAGE_RATIO = 2               # 杠杆倍数(2=等效CHAU两倍做多)
# 仓位按杠杆倍数计算: 名义市值 = 账户总值 × LEVERAGE_RATIO
# 保证金占比 = LEVERAGE_RATIO × MARGIN_RATE = 30%

# 死区过滤（仅CNY信号）
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
    # 回测最终状态: CNY=-1, Shibor=1, quadrant=Q2
    context.ific_cny_state = -1                    # 回测最终值(2026-03-13)
    context.ific_shibor_state = 1                  # 回测最终值
    context.ific_shibor_tight_count = 0            # Shibor处于宽松期
    context.ific_shibor_loose_count = 10           # ≥5即保持state=1
    # quadrant保持INIT — 第一天check_signals推导出Q2，触发自动建仓(rebalance)
    context.ific_quadrant = 'INIT'
    context.ific_prev_quadrant = 'INIT'
    context.ific_if_contract = None
    context.ific_ic_contract = None

    # === 平仓复利NAV（从回测提取）===
    g.nav_value = 5.335167           # 最后实现NAV(2026-03-13平仓Q3)
    g.entry_quadrant = 'NONE'        # 新实例无持仓，首日rebalance后变Q2
    g.if_entry_price = None           # 首日开仓时设定
    g.ic_entry_price = None           # 首日开仓时设定
    g.current_contracts = 0

    # 调度
    run_daily(ific_check_signals, time='09:00', reference_security='000300.XSHG')
    run_daily(ific_execute_trade, time='09:31', reference_security='000300.XSHG')
    run_daily(send_daily_nav, time='after_close')


# ============================================================
# 动态仓位计算
# ============================================================
def calc_num_contracts(context, quadrant):
    """按ETF杠杆倍数计算开仓手数: 名义市值 = 账户总值 × LEVERAGE_RATIO"""
    total = context.subportfolios[0].total_value
    target_notional = total * LEVERAGE_RATIO

    if_dom = get_dominant_future('IF')
    ic_dom = get_dominant_future('IC')

    if_data = get_price(if_dom, end_date=context.previous_date, count=1, fields=['close'])
    ic_data = get_price(ic_dom, end_date=context.previous_date, count=1, fields=['close'])

    if if_data is None or len(if_data) == 0 or ic_data is None or len(ic_data) == 0:
        log.warn('[IF-IC] 无法获取价格，默认1手')
        return 1

    if_price = if_data['close'].iloc[-1]
    ic_price = ic_data['close'].iloc[-1]

    if quadrant in ['Q1', 'Q2']:
        set_notional = if_price * IF_MULTIPLIER + ic_price * IC_MULTIPLIER
    elif quadrant == 'Q3':
        set_notional = ic_price * IC_MULTIPLIER
    else:
        return 0

    n = int(target_notional / set_notional)
    if n < 1:
        n = 1  # 至少开1手，实际杠杆可能>2x但NAV独立于手数
        log.warn('[IF-IC] 资金不足目标杠杆，最低1手 总值%.0f 名义%.0f(%.1fx)'
                 % (total, set_notional, set_notional / total))

    actual_notional = n * set_notional
    margin_used = actual_notional * MARGIN_RATE
    log.info('[IF-IC] ETF仓位: %d手 名义%.0f(%.1fx) 保证金%.0f(%.0f%%) 总值%.0f'
             % (n, actual_notional, actual_notional / total,
                margin_used, margin_used / total * 100, total))
    return n


# ============================================================
# 数据获取
# ============================================================
def ific_get_usdcny(context, count=35):
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
    return df['cash_buy_rate'].values


def ific_get_shibor_3m(context, count=65):
    end_date = context.current_dt.strftime('%Y-%m-%d')
    q = query(
        macro.MAC_LEND_RATE.day,
        macro.MAC_LEND_RATE.interest_rate
    ).filter(
        macro.MAC_LEND_RATE.currency_id == 1,
        macro.MAC_LEND_RATE.market_id == 3,
        macro.MAC_LEND_RATE.term_id == 3,
        macro.MAC_LEND_RATE.day <= end_date
    ).order_by(
        macro.MAC_LEND_RATE.day.desc()
    ).limit(count + 10)

    df = macro.run_query(q)
    if df is None or df.empty:
        return None
    df = df.sort_values('day').reset_index(drop=True)
    df['interest_rate'] = df['interest_rate'].astype(float)
    return df['interest_rate'].values


# ============================================================
# 平仓复利NAV
# ============================================================
def nav_close_position(if_exit_price, ic_exit_price):
    """平仓时更新NAV：按象限计算持仓期间组合收益率"""
    q = g.entry_quadrant
    if q == 'NONE' or q == 'Q4':
        return

    if q in ['Q1', 'Q2']:
        if g.if_entry_price is None or g.ic_entry_price is None:
            return
        if if_exit_price is None or ic_exit_price is None:
            return
        if_notional = g.if_entry_price * IF_MULTIPLIER
        ic_notional = g.ic_entry_price * IC_MULTIPLIER
        capital = (if_notional + ic_notional) / LEVERAGE_RATIO

        if_pnl = (if_exit_price - g.if_entry_price) * IF_MULTIPLIER
        ic_pnl = (ic_exit_price - g.ic_entry_price) * IC_MULTIPLIER

        if q == 'Q1':   # 多IF + 空IC
            combined_pnl = if_pnl - ic_pnl
        else:            # Q2: 空IF + 多IC
            combined_pnl = -if_pnl + ic_pnl
        move = combined_pnl / capital

    elif q == 'Q3':
        if g.ic_entry_price is None or ic_exit_price is None:
            return
        ic_notional = g.ic_entry_price * IC_MULTIPLIER
        capital = ic_notional / LEVERAGE_RATIO
        ic_pnl = (ic_exit_price - g.ic_entry_price) * IC_MULTIPLIER
        move = ic_pnl / capital
    else:
        return

    g.nav_value *= (1 + move)
    log.info('[IF-IC] 平仓NAV: quad=%s if_entry=%.2f ic_entry=%.2f move=%.4f nav=%.6f'
             % (q,
                g.if_entry_price or 0, g.ic_entry_price or 0,
                move, g.nav_value))
    g.if_entry_price = None
    g.ic_entry_price = None
    g.entry_quadrant = 'NONE'


def calc_mark_to_market_nav(current_if_price, current_ic_price):
    """计算mark-to-market NAV（不修改基础NAV）"""
    q = g.entry_quadrant
    if q == 'NONE' or q == 'Q4':
        return g.nav_value

    if q in ['Q1', 'Q2']:
        if g.if_entry_price is None or g.ic_entry_price is None:
            return g.nav_value
        if current_if_price is None or current_ic_price is None:
            return g.nav_value
        if_notional = g.if_entry_price * IF_MULTIPLIER
        ic_notional = g.ic_entry_price * IC_MULTIPLIER
        capital = (if_notional + ic_notional) / LEVERAGE_RATIO
        if_pnl = (current_if_price - g.if_entry_price) * IF_MULTIPLIER
        ic_pnl = (current_ic_price - g.ic_entry_price) * IC_MULTIPLIER
        if q == 'Q1':
            combined_pnl = if_pnl - ic_pnl
        else:
            combined_pnl = -if_pnl + ic_pnl
        move = combined_pnl / capital

    elif q == 'Q3':
        if g.ic_entry_price is None or current_ic_price is None:
            return g.nav_value
        ic_notional = g.ic_entry_price * IC_MULTIPLIER
        capital = ic_notional / LEVERAGE_RATIO
        ic_pnl = (current_ic_price - g.ic_entry_price) * IC_MULTIPLIER
        move = ic_pnl / capital
    else:
        return g.nav_value

    return g.nav_value * (1 + move)


def get_today_open(context, security):
    """获取今日开盘价（用于近似交易价）"""
    data = get_price(security, end_date=context.current_dt,
                     count=1, fields=['open'])
    if data is not None and len(data) > 0:
        return data['open'].iloc[-1]
    return None



# ============================================================
# 双信号检查（CNY含死区过滤）
# ============================================================
def ific_check_signals(context):
    # --- CNY信号 + 死区过滤 ---
    rates = ific_get_usdcny(context, 35)
    if rates is not None and len(rates) >= 30:
        current = rates[-1]
        sma5 = rates[-5:].mean()
        sma10 = rates[-10:].mean()
        sma30 = rates[-30:].mean()

        old_cny = context.ific_cny_state

        below_all = current < sma5 and current < sma10 and current < sma30
        above_all = current > sma5 and current > sma10 and current > sma30

        if below_all or above_all:
            # 死区过滤
            if below_all:
                nearest_ma = min(sma5, sma10, sma30)
            else:
                nearest_ma = max(sma5, sma10, sma30)
            distance_pct = abs(current - nearest_ma) / current
            if distance_pct >= DEADZONE_PCT:
                if below_all:
                    context.ific_cny_state = 1
                elif above_all:
                    context.ific_cny_state = -1

        if context.ific_cny_state != old_cny:
            log.info('[IF-IC] CNY信号: %d -> %d | USDCNY=%.2f SMA5=%.2f SMA10=%.2f SMA30=%.2f'
                     % (old_cny, context.ific_cny_state, current, sma5, sma10, sma30))

    # --- Shibor信号（无死区，已有5日确认） ---
    shibor = ific_get_shibor_3m(context, 65)
    if shibor is not None and len(shibor) >= 60:
        ma20 = shibor[-20:].mean()
        ma60 = shibor[-60:].mean()
        diff = ma20 - ma60

        old_shibor = context.ific_shibor_state
        if diff > 0:
            context.ific_shibor_tight_count += 1
            context.ific_shibor_loose_count = 0
        elif diff < 0:
            context.ific_shibor_loose_count += 1
            context.ific_shibor_tight_count = 0

        if context.ific_shibor_tight_count >= SHIBOR_CONFIRM:
            context.ific_shibor_state = -1
        elif context.ific_shibor_loose_count >= SHIBOR_CONFIRM:
            context.ific_shibor_state = 1

        if context.ific_shibor_state != old_shibor:
            log.info('[IF-IC] Shibor信号: %d -> %d | MA20=%.4f MA60=%.4f diff=%.4f'
                     % (old_shibor, context.ific_shibor_state, ma20, ma60, diff))

    # --- 象限判定 ---
    c, s = context.ific_cny_state, context.ific_shibor_state
    context.ific_prev_quadrant = context.ific_quadrant

    if c == 1 and s == -1:
        context.ific_quadrant = 'Q1'
    elif c == -1 and s == 1:
        context.ific_quadrant = 'Q2'
    elif c == 1 and s == 1:
        context.ific_quadrant = 'Q3'
    elif c == -1 and s == -1:
        context.ific_quadrant = 'Q4'

    if context.ific_quadrant != context.ific_prev_quadrant:
        log.info('[IF-IC] === 象限切换: %s -> %s === (CNY=%d, Shibor=%d)'
                 % (context.ific_prev_quadrant, context.ific_quadrant, c, s))


# ============================================================
# 交易执行
# ============================================================
def ific_execute_trade(context):
    if context.ific_quadrant == 'INIT':
        return
    if_dom = get_dominant_future('IF')
    ic_dom = get_dominant_future('IC')
    if if_dom == '' or ic_dom == '':
        log.warn('[IF-IC] 无法获取主力合约')
        return

    rolled = ific_handle_rollover(context, if_dom, ic_dom)
    context.ific_if_contract = if_dom
    context.ific_ic_contract = ic_dom

    if rolled and context.ific_quadrant == context.ific_prev_quadrant:
        return

    if context.ific_quadrant == context.ific_prev_quadrant:
        return

    # 动态计算手数
    n = calc_num_contracts(context, context.ific_quadrant)
    if n == 0:
        return

    # 涨跌停检查
    if context.ific_quadrant in ['Q1', 'Q2', 'Q3']:
        targets = []
        if context.ific_quadrant in ['Q1', 'Q2']:
            targets = [if_dom, ic_dom]
        elif context.ific_quadrant == 'Q3':
            targets = [ic_dom]

        for sec in targets:
            prev_date = context.previous_date
            cp = get_price(sec, end_date=prev_date, count=1, fields=['close', 'high_limit', 'low_limit'])
            if cp is not None and len(cp) > 0:
                close = cp['close'].iloc[-1]
                hi = cp['high_limit'].iloc[-1]
                lo = cp['low_limit'].iloc[-1]
                if close >= hi or close <= lo:
                    log.warn('[IF-IC] 涨跌停: %s close=%.2f limit=[%.2f, %.2f], 跳过' % (sec, close, lo, hi))
                    return

    # --- 平仓旧持仓 → 更新NAV ---
    if g.entry_quadrant not in ['NONE', 'Q4']:
        if_exit = get_today_open(context, if_dom)
        ic_exit = get_today_open(context, ic_dom)
        nav_close_position(if_exit, ic_exit)

    # 先全部平仓
    ific_close_all(context)

    # --- 开新仓 ---
    if_open = get_today_open(context, if_dom)
    ic_open = get_today_open(context, ic_dom)

    if context.ific_quadrant == 'Q1':
        order(if_dom, n, side='long', pindex=0)
        order(ic_dom, n, side='short', pindex=0)
        g.current_contracts = n
        g.entry_quadrant = 'Q1'
        g.if_entry_price = if_open
        g.ic_entry_price = ic_open
        log.info('[IF-IC] Q1开仓: 多IF %d手 + 空IC %d手 if_entry=%.2f ic_entry=%.2f'
                 % (n, n, if_open or 0, ic_open or 0))
        send_webhook('buy', if_dom, n,
                    notes='IF-IC Q1: 多IF %d手 + 空IC %d手' % (n, n))
    elif context.ific_quadrant == 'Q2':
        order(if_dom, n, side='short', pindex=0)
        order(ic_dom, n, side='long', pindex=0)
        g.current_contracts = n
        g.entry_quadrant = 'Q2'
        g.if_entry_price = if_open
        g.ic_entry_price = ic_open
        log.info('[IF-IC] Q2开仓: 空IF %d手 + 多IC %d手 if_entry=%.2f ic_entry=%.2f'
                 % (n, n, if_open or 0, ic_open or 0))
        send_webhook('buy', ic_dom, n,
                    notes='IF-IC Q2: 空IF %d手 + 多IC %d手' % (n, n))
    elif context.ific_quadrant == 'Q3':
        order(ic_dom, n, side='long', pindex=0)
        g.current_contracts = n
        g.entry_quadrant = 'Q3'
        g.if_entry_price = None
        g.ic_entry_price = ic_open
        log.info('[IF-IC] Q3开仓: 多IC %d手 ic_entry=%.2f' % (n, ic_open or 0))
        send_webhook('buy', ic_dom, n,
                    notes='IF-IC Q3: 多IC %d手' % n)
    elif context.ific_quadrant == 'Q4':
        g.current_contracts = 0
        g.entry_quadrant = 'Q4'
        g.if_entry_price = None
        g.ic_entry_price = None
        log.info('[IF-IC] Q4: 空仓')
        send_webhook('sell', 'FLAT', 0,
                    notes='IF-IC Q4: 空仓')


def ific_handle_rollover(context, new_if, new_ic):
    rolled = False

    if context.ific_if_contract is not None and context.ific_if_contract != new_if:
        old = context.ific_if_contract
        for side in ['long', 'short']:
            amt = ific_get_pos_amount(context, old, side)
            if amt > 0:
                # 换月：先平仓更新NAV，再开新合约
                if not rolled and g.entry_quadrant not in ['NONE', 'Q4']:
                    if_exit = get_today_open(context, old)
                    ic_exit = get_today_open(context, context.ific_ic_contract or new_ic)
                    nav_close_position(if_exit, ic_exit)
                    rolled = True
                order_target(old, 0, side=side, pindex=0)
                order(new_if, amt, side=side, pindex=0)
                log.info('[IF-IC] IF换月: %s %s %d手 -> %s' % (side, old, amt, new_if))

    if context.ific_ic_contract is not None and context.ific_ic_contract != new_ic:
        old = context.ific_ic_contract
        for side in ['long', 'short']:
            amt = ific_get_pos_amount(context, old, side)
            if amt > 0:
                if not rolled and g.entry_quadrant not in ['NONE', 'Q4']:
                    if_exit = get_today_open(context, context.ific_if_contract or new_if)
                    ic_exit = get_today_open(context, old)
                    nav_close_position(if_exit, ic_exit)
                    rolled = True
                order_target(old, 0, side=side, pindex=0)
                order(new_ic, amt, side=side, pindex=0)
                log.info('[IF-IC] IC换月: %s %s %d手 -> %s' % (side, old, amt, new_ic))

    if rolled:
        # 重新设定entry_price为新合约开盘价
        g.if_entry_price = get_today_open(context, new_if)
        g.ic_entry_price = get_today_open(context, new_ic)
        g.entry_quadrant = context.ific_quadrant
        log.info('[IF-IC] 换月NAV重置: if_entry=%.2f ic_entry=%.2f quad=%s'
                 % (g.if_entry_price or 0, g.ic_entry_price or 0, g.entry_quadrant))

    return rolled


def ific_close_all(context):
    for pos in list(context.subportfolios[0].long_positions.values()):
        if pos.total_amount > 0:
            order_target(pos.security, 0, side='long', pindex=0)
    for pos in list(context.subportfolios[0].short_positions.values()):
        if pos.total_amount > 0:
            order_target(pos.security, 0, side='short', pindex=0)


def ific_get_pos_amount(context, security, side):
    if side == 'long':
        positions = context.subportfolios[0].long_positions
    else:
        positions = context.subportfolios[0].short_positions
    if security not in positions:
        return 0
    pos = positions[security]
    return pos.total_amount if pos.total_amount > 0 else 0



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
    ic_dom = get_dominant_future('IC')

    if_data = get_price(if_dom, end_date=context.current_dt,
                        count=1, fields=['close'])
    ic_data = get_price(ic_dom, end_date=context.current_dt,
                        count=1, fields=['close'])

    if_price = if_data['close'].iloc[-1] if if_data is not None and len(if_data) > 0 else None
    ic_price = ic_data['close'].iloc[-1] if ic_data is not None and len(ic_data) > 0 else None

    nav = calc_mark_to_market_nav(if_price, ic_price)
    total = context.subportfolios[0].total_value

    status = {
        "data_ok": True,
        "signal": context.ific_quadrant,
        "holding": context.ific_if_contract or "",
        "contracts": g.current_contracts,
        "entry_quadrant": g.entry_quadrant,
        "if_entry": round(g.if_entry_price, 2) if g.if_entry_price else None,
        "ic_entry": round(g.ic_entry_price, 2) if g.ic_entry_price else None,
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
        log.info('[IF-IC] NAV=%.6f (realized=%.6f, quad=%s, n=%d, total=%.0f)'
                 % (nav, g.nav_value, g.entry_quadrant, g.current_contracts, total))
    except Exception as e:
        log.error(f"NAV exception: {e}")
