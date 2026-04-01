# ============================================================
# 独立策略：成交额冷门股
# 平台：聚宽 (JoinQuant)
# 单股票账户，无子账户
# Algo ID: JQ-COLD-STOCK
# ============================================================

from jqdata import *
import numpy as np
import pandas as pd
import requests
import json
from datetime import datetime

WEBHOOK_URL = "https://www.quanttogo.com/receiveJQWebhook?token=b39b4e3e4cd2e55e8432d039e3112edf76d1ab4d7bb060feb42d2c4134362bc8"
ALGO_ID = "JQ-COLD-STOCK"


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)

    # 股票手续费
    set_order_cost(OrderCost(
        open_tax=0, close_tax=0.001,
        open_commission=0.0003, close_commission=0.0003,
        min_commission=5
    ), type='stock')

    set_slippage(FixedSlippage(0.02))

    # === 部署参数（从2020-01-01~2026-03-11回测提取）===
    # 回测最后持有的10只股票（用于首日建仓）
    g.cold_target_stocks = [
        '003040.XSHE',  # 楚天龙
        '600081.XSHG',  # 东风科技
        '601177.XSHG',  # 杭齿前进
        '300333.XSHE',  # 兆日科技
        '603955.XSHG',  # 大千生态
        '603677.XSHG',  # 奇精机械
        '300546.XSHE',  # 雄帝科技
        '301602.XSHE',  # 超研股份
        '600571.XSHG',  # 信雅达
        '002570.XSHE',  # 贝因美
    ]
    g.cold_holding_counts = []

    # NAV: chart从2020-01-02起始值1.0，回测total从1M涨到3,406,330
    # nav_base = total_03-11 / starting_cash = 3406330 / 1000000
    g.nav_base = 3.406330                        # chart值(2026-03-11), 部署续写点

    # 首日建仓标记（仅执行一次）
    g.need_initial_buy = True

    # 调度：月末选股，月初调仓，每日首日建仓检查
    run_monthly(cold_calc_signal, monthday=-1, time='after_close')
    run_monthly(cold_execute_trades, monthday=1, time='open')
    run_daily(cold_initial_restore, time='09:31')
    run_daily(send_daily_nav, time='after_close')
    run_daily(send_index_raw_data, time='after_close')


# ============================================================
# 选股池构建
# ============================================================
def cold_get_stock_pool(context):
    date = context.current_dt.date()
    securities = get_all_securities(types=['stock'], date=date)
    one_year_ago = date - pd.Timedelta(days=365)
    securities = securities[securities['start_date'] <= one_year_ago]
    pool = securities.index.tolist()

    # 排除ST
    st_info = get_extras('is_st', pool, end_date=date, count=1).iloc[0].astype(bool)
    pool = st_info[~st_info].index.tolist()

    # 排除停牌
    paused = get_price(pool, end_date=date, count=1, fields=['paused'])['paused'].iloc[0].astype(bool)
    pool = paused[~paused].index.tolist()

    # 流动性地板：日均成交额>1000万
    money_250d = get_price(pool, end_date=date, count=250, fields=['money'])['money']
    avg_money = money_250d.mean()
    liquid_stocks = avg_money[avg_money > 1e7].index.tolist()

    # 市值>30亿
    q = query(valuation.code, valuation.market_cap).filter(
        valuation.code.in_(liquid_stocks),
        valuation.market_cap > 30
    )
    df = get_fundamentals(q, date=date)
    pool = df['code'].tolist()

    # 60日动量 > -5%
    if len(pool) > 0:
        price_60d = get_price(pool, end_date=date, count=60, fields=['close'])['close']
        if len(price_60d) >= 60:
            ret_60d = (price_60d.iloc[-1] / price_60d.iloc[0]) - 1
            pool = ret_60d[ret_60d > -0.05].index.tolist()

    log.info(f'[冷门股] 流动性>{len(liquid_stocks)}, 市值>{len(df)}, 动量>{len(pool)}')
    return pool


def cold_calc_volume_cold(stock_pool, date):
    money_df = get_price(stock_pool, end_date=date, count=270, fields=['money'])['money']
    if len(money_df) < 260:
        return pd.Series()
    avg_250 = money_df.rolling(250).mean()
    ratio = money_df / avg_250
    cold_indicator = ratio.tail(20).max()
    cold_indicator = cold_indicator.dropna()
    cold_indicator = cold_indicator[cold_indicator > 0]
    return cold_indicator


# ============================================================
# 月末选股
# ============================================================
def cold_calc_signal(context):
    date = context.current_dt.date()
    log.info(f'=== [冷门股] 计算信号: {date} ===')

    pool = cold_get_stock_pool(context)
    log.info(f'[冷门股] 股票池: {len(pool)} 只')

    if len(pool) == 0:
        g.cold_target_stocks = []
        return

    cold = cold_calc_volume_cold(pool, date)
    if len(cold) == 0:
        g.cold_target_stocks = []
        return

    cold_sorted = cold.sort_values(ascending=True)
    g.cold_target_stocks = cold_sorted.head(10).index.tolist()
    g.cold_holding_counts.append(len(g.cold_target_stocks))

    for s in g.cold_target_stocks:
        name = get_security_info(s).display_name
        log.info(f'  {name} ({s}) 指标={cold_sorted[s]:.4f}')


# ============================================================
# 科创板限价单处理
# ============================================================
def cold_get_order_style(stock, context, is_buy=True):
    """科创板(688xxx)市价单需要保护限价，改用限价单"""
    if stock.startswith('688'):
        cp = get_price(stock, end_date=context.current_dt, count=1, fields=['close'])
        if cp is not None and len(cp) > 0:
            price = cp['close'].iloc[-1]
            # 科创板涨跌幅±20%，用宽裕限价确保成交
            limit = round(price * 1.05, 2) if is_buy else round(price * 0.95, 2)
            return LimitOrderStyle(limit)
    return None


# ============================================================
# 月初调仓
# ============================================================
def cold_execute_trades(context):
    date = context.current_dt.date()
    log.info(f'=== [冷门股] 调仓: {date} ===')

    # 卖出不在目标中的持仓
    for stock in list(context.portfolio.positions.keys()):
        if stock not in g.cold_target_stocks:
            pos = context.portfolio.positions[stock]
            qty = pos.total_amount if pos else 0
            style = cold_get_order_style(stock, context, is_buy=False)
            if style:
                order_target(stock, 0, style=style)
            else:
                order_target(stock, 0)
            send_webhook('sell', stock, qty,
                        notes='冷门股调仓卖出 %s' % stock)

    # 等权买入
    if len(g.cold_target_stocks) > 0:
        weight = 1.0 / len(g.cold_target_stocks)
        target_value = context.portfolio.total_value * weight
        for stock in g.cold_target_stocks:
            style = cold_get_order_style(stock, context, is_buy=True)
            if style:
                order_target_value(stock, target_value, style=style)
            else:
                order_target_value(stock, target_value)
            send_webhook('buy', stock, 0,
                        notes='冷门股等权买入 %s 目标%.0f元' % (stock, target_value))


# ============================================================
# 首日建仓（部署用，仅执行一次）
# ============================================================
def cold_initial_restore(context):
    """部署首日：按目标股票等权建仓（仅执行一次）"""
    if not g.need_initial_buy:
        return
    g.need_initial_buy = False
    if len(g.cold_target_stocks) == 0:
        log.info('[冷门股] 无目标股票，跳过首日建仓')
        return
    log.info(f'[冷门股] === 首日建仓: {len(g.cold_target_stocks)}只 ===')
    cold_execute_trades(context)


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
    held = list(context.portfolio.positions.keys())
    status = {
        "data_ok": True,
        "signal": f"{len(held)}只持仓",
        "holding": ",".join(held[:5]),
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


def send_index_raw_data(context):
    """每日发送CSI300和创业板收盘价，供calculateIndices计算DA-MOMENTUM"""
    date = context.previous_date.strftime('%Y-%m-%d')
    for index_id, security in [('CSI300', '000300.XSHG'), ('CHINEXT', '399006.XSHE')]:
        try:
            df = get_price(security, end_date=context.previous_date, count=1, fields=['close'])
            if df is not None and len(df) > 0:
                close_price = float(df['close'].iloc[-1])
                payload = {
                    "algo": ALGO_ID,
                    "event": "index_raw_data",
                    "indexId": index_id,
                    "date": date,
                    "close": close_price,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "timestamp": datetime.now().isoformat()
                }
                requests.post(WEBHOOK_URL, json=payload,
                             headers={"Content-Type": "application/json"}, timeout=5)
                log.info(f"[冷门股] 指数数据: {index_id}={close_price:.2f} ({date})")
        except Exception as e:
            log.error(f"[冷门股] 指数数据发送失败 {index_id}: {e}")


def on_strategy_end(context):
    if g.cold_holding_counts:
        log.info(f'=== [冷门股] 回测统计 ===')
        log.info(f'调仓 {len(g.cold_holding_counts)} 次, 平均持股 {np.mean(g.cold_holding_counts):.1f}')
