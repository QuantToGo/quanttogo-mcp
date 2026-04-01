#!/usr/bin/env python3
# ============================================================
# 本地回测：CNH-IF 多空策略
# 用 CNH（离岸人民币）信号 + IF（沪深300期货）执行
# 对标 CNY-IF（在岸）和 CNH-CHAU（离岸ETF），验证 CNH 波动率优势
#
# 数据来源：
#   IF: JQ导出 CSV (export-if-data-jq.py)
#   CNH: Alpha Vantage FX_DAILY (USD/CNH)
#
# 用法：
#   pip install requests pandas
#   python cnh-if-backtest.py
#   或指定 IF CSV: python cnh-if-backtest.py --if-csv path/to/if_dominant_daily.csv
# ============================================================

import argparse
import pandas as pd
import numpy as np
import sys
import os
import time
import requests
from datetime import datetime

AV_API_KEY = 'VPC2QYD308YNNCDN'
AV_BASE_URL = 'https://www.alphavantage.co/query'

# === 策略参数 ===
SMA_SHORT = 5
SMA_MID = 10
SMA_LONG = 30
LEVERAGE_RATIO = 2
DEADZONE_PCT = 0.001     # 0.1% 死区过滤
IF_MULTIPLIER = 300

# === 回测区间 ===
BT_START = '2020-01-01'
BT_END = '2026-03-14'
CNH_FETCH_START = '2019-10-01'  # 提前拉取给SMA预热


def fetch_cnh_data(start, end):
    """从 Alpha Vantage 获取 USD/CNH 日线（FX_DAILY full history）"""
    print(f"正在从 Alpha Vantage 获取 USD/CNH ({start} ~ {end}) ...")
    try:
        resp = requests.get(AV_BASE_URL, params={
            'function': 'FX_DAILY',
            'from_symbol': 'USD',
            'to_symbol': 'CNH',
            'outputsize': 'full',
            'apikey': AV_API_KEY,
        }, timeout=30)
        data = resp.json()
        ts = data.get('Time Series FX (Daily)', {})
        if not ts:
            note = data.get('Note') or data.get('Information') or ''
            print(f"警告: Alpha Vantage 返回空数据. {note[:120]}")
            return None
        # 解析为 DataFrame
        records = []
        for d in sorted(ts.keys()):
            if d < start or d > end:
                continue
            records.append({'date': d, 'cnh_rate': float(ts[d]['4. close'])})
        df = pd.DataFrame(records).set_index('date')
        print(f"  获取到 {len(df)} 行 CNH 数据 ({df.index[0]} ~ {df.index[-1]})")
        return df
    except Exception as e:
        print(f"错误: Alpha Vantage 获取失败: {e}")
        return None


def load_if_data(csv_path):
    """加载 JQ 导出的 IF 主力合约日线"""
    if not os.path.exists(csv_path):
        print(f"错误: 找不到 IF 数据文件: {csv_path}")
        print("请先在 JQ 研究环境运行 export-if-data-jq.py 并保存 CSV")
        sys.exit(1)
    df = pd.read_csv(csv_path)
    df['date'] = df['date'].astype(str)
    df = df.set_index('date')
    print(f"  加载 {len(df)} 行 IF 数据 ({df.index[0]} ~ {df.index[-1]})")
    return df


def run_backtest(cnh_df, if_df):
    """运行 CNH-IF 回测"""
    # 合并数据（取交集日期）
    merged = cnh_df.join(if_df, how='inner')
    merged = merged.dropna(subset=['cnh_rate', 'close'])
    merged = merged.sort_index()

    # 过滤回测区间
    merged = merged[(merged.index >= BT_START) & (merged.index <= BT_END)]
    print(f"\n回测区间: {merged.index[0]} ~ {merged.index[-1]}, 共 {len(merged)} 交易日")

    # === 回测状态 ===
    nav_value = 1.0
    direction = 'NONE'      # LONG / SHORT / NONE
    entry_price = None       # IF 开仓价
    current_signal = 'NONE'
    prev_signal = 'NONE'

    # 统计
    trades = []
    daily_records = []
    signal_changes = 0

    cnh_rates = merged['cnh_rate'].values
    if_opens = merged['open'].values
    if_closes = merged['close'].values
    dates = merged.index.values

    for i in range(SMA_LONG + 1, len(merged)):
        date = dates[i]
        if_close = if_closes[i]
        if_open = if_opens[i]

        # --- CNH 信号（用前一天收盘，避免 look-ahead bias）---
        # AV FX_DAILY close = 5PM ET，比 IF open（北京9:30=ET前日20:30）晚约21小时
        # 所以信号只能用 T-1 的 CNH 数据，T 日执行
        cnh_current = cnh_rates[i-1]
        sma5 = cnh_rates[i-1-SMA_SHORT+1:i].mean()
        sma10 = cnh_rates[i-1-SMA_MID+1:i].mean()
        sma30 = cnh_rates[i-1-SMA_LONG+1:i].mean()

        prev_signal = current_signal

        below_all = cnh_current < sma5 and cnh_current < sma10 and cnh_current < sma30
        above_all = cnh_current > sma5 and cnh_current > sma10 and cnh_current > sma30

        if below_all or above_all:
            if below_all:
                nearest_ma = min(sma5, sma10, sma30)
            else:
                nearest_ma = max(sma5, sma10, sma30)
            distance_pct = abs(cnh_current - nearest_ma) / cnh_current
            if distance_pct >= DEADZONE_PCT:
                if below_all:
                    current_signal = 'LONG'
                elif above_all:
                    current_signal = 'SHORT'

        # --- 信号切换 → 交易 ---
        if current_signal != prev_signal and current_signal != 'NONE':
            signal_changes += 1

            # 平仓旧持仓
            if direction != 'NONE' and entry_price is not None:
                move = (if_open - entry_price) / entry_price * LEVERAGE_RATIO
                if direction == 'SHORT':
                    move = -move
                nav_value *= (1 + move)
                trades.append({
                    'date': date,
                    'action': f'close_{direction.lower()}',
                    'entry': entry_price,
                    'exit': if_open,
                    'move': move,
                    'nav': nav_value,
                    'win': 1 if move > 0 else 0
                })

            # 开新仓
            entry_price = if_open
            direction = current_signal

        # --- 每日 mark-to-market NAV ---
        if direction != 'NONE' and entry_price is not None:
            mtm_move = (if_close - entry_price) / entry_price * LEVERAGE_RATIO
            if direction == 'SHORT':
                mtm_move = -mtm_move
            display_nav = nav_value * (1 + mtm_move)
        else:
            display_nav = nav_value

        daily_records.append({
            'date': date,
            'signal': current_signal,
            'direction': direction,
            'cnh': round(cnh_current, 4),
            'if_close': round(if_close, 2),
            'nav': round(display_nav, 6)
        })

    return daily_records, trades, nav_value


def print_summary(daily_records, trades, final_nav):
    """打印回测摘要"""
    df = pd.DataFrame(daily_records)
    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()

    print("\n" + "=" * 60)
    print("CNH-IF 回测结果")
    print("=" * 60)

    print(f"\n最终 NAV (realized): {final_nav:.6f}")
    print(f"最终 NAV (mark-to-market): {df['nav'].iloc[-1]:.6f}")
    print(f"交易日数: {len(df)}")

    if len(trades_df) > 0:
        wins = trades_df['win'].sum()
        losses = len(trades_df) - wins
        print(f"\n交易次数: {len(trades_df)}")
        print(f"胜率: {wins}/{len(trades_df)} = {wins/len(trades_df)*100:.1f}%")

        win_trades = trades_df[trades_df['move'] > 0]['move']
        loss_trades = trades_df[trades_df['move'] <= 0]['move']
        if len(win_trades) > 0 and len(loss_trades) > 0:
            avg_win = win_trades.mean()
            avg_loss = abs(loss_trades.mean())
            print(f"平均盈利: {avg_win*100:.2f}%  平均亏损: {avg_loss*100:.2f}%")
            print(f"盈亏比: {avg_win/avg_loss:.2f}")

    # 最大回撤
    navs = df['nav'].values
    peak = navs[0]
    max_dd = 0
    for n in navs:
        if n > peak:
            peak = n
        dd = (peak - n) / peak
        if dd > max_dd:
            max_dd = dd
    print(f"\n最大回撤: {max_dd*100:.1f}%")

    # 对比表
    print("\n--- 对比 ---")
    print(f"CNH-IF (本次):  NAV = {df['nav'].iloc[-1]:.2f}x")
    print(f"CNY-IF (在岸):  NAV = 8.07x  (JQ 回测)")
    print(f"CNH-CHAU (ETF): NAV = ??.?x  (VA 回测)")

    # 输出每日 NAV CSV
    csv_path = os.path.join(os.path.dirname(__file__), 'cnh-if-daily-nav.csv')
    df[['date', 'nav']].to_csv(csv_path, index=False)
    print(f"\n每日 NAV 已保存: {csv_path}")

    # 输出最后信号状态（用于部署）
    last = df.iloc[-1]
    print(f"\n最终状态 ({last['date']}):")
    print(f"  signal = {last['signal']}")
    print(f"  direction = {last['direction']}")
    print(f"  CNH = {last['cnh']}")


def main():
    parser = argparse.ArgumentParser(description='CNH-IF 合成回测')
    parser.add_argument('--if-csv', default=None,
                        help='IF 日线 CSV 路径 (JQ导出)')
    parser.add_argument('--cnh-csv', default=None,
                        help='CNH 日线 CSV 路径 (可选, 默认从 Alpha Vantage 获取)')
    args = parser.parse_args()

    # IF 数据
    if args.if_csv:
        if_csv = args.if_csv
    else:
        if_csv = os.path.join(os.path.dirname(__file__), 'if_dominant_daily.csv')
    if_df = load_if_data(if_csv)

    # CNH 数据
    if args.cnh_csv:
        cnh_df = pd.read_csv(args.cnh_csv)
        cnh_df['date'] = cnh_df['date'].astype(str)
        cnh_df = cnh_df.set_index('date')
        print(f"  加载 {len(cnh_df)} 行 CNH 数据 (本地 CSV)")
    else:
        cnh_df = fetch_cnh_data(CNH_FETCH_START, BT_END)
        if cnh_df is None:
            print("无法获取 CNH 数据，退出")
            sys.exit(1)
        # 保存一份本地 CSV 备用
        csv_path = os.path.join(os.path.dirname(__file__), 'cnh_av_daily.csv')
        cnh_df.to_csv(csv_path)
        print(f"  CNH 数据已缓存: {csv_path}")

    # 运行回测
    daily_records, trades, final_nav = run_backtest(cnh_df, if_df)
    print_summary(daily_records, trades, final_nav)


if __name__ == '__main__':
    main()
