#!/usr/bin/env python3
# ============================================================
# 本地回测：CNH-CHAU 离岸人民币 + CHAU ETF（2x杠杆沪深300）
# 用 CNH 信号做多/空 CHAU ETF
# 对标 CNH-IF（期货版）和 CNY-IF（在岸版），比较不同执行载体
#
# 数据来源：
#   CNH:  Alpha Vantage FX_DAILY (USD/CNH)
#   CHAU: Alpha Vantage TIME_SERIES_DAILY
#
# 用法：
#   pip install requests pandas
#   python cnh-chau-backtest.py
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
AV_CALL_DELAY = 1.0  # AV 限频

# === 策略参数 ===
SMA_SHORT = 5
SMA_MID = 10
SMA_LONG = 30
DEADZONE_PCT = 0.001     # 0.1% 死区过滤
# CHAU 自带 2x 杠杆，不需要额外 LEVERAGE_RATIO

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
            print(f"警告: Alpha Vantage CNH 返回空. {note[:120]}")
            return None
        records = []
        for d in sorted(ts.keys()):
            if d < start or d > end:
                continue
            records.append({'date': d, 'cnh_rate': float(ts[d]['4. close'])})
        df = pd.DataFrame(records).set_index('date')
        print(f"  获取到 {len(df)} 行 CNH 数据 ({df.index[0]} ~ {df.index[-1]})")
        return df
    except Exception as e:
        print(f"错误: Alpha Vantage CNH 获取失败: {e}")
        return None


def fetch_chau_data(start, end):
    """从 Alpha Vantage 获取 CHAU ETF 日线（TIME_SERIES_DAILY full history）"""
    print(f"正在从 Alpha Vantage 获取 CHAU ETF ({start} ~ {end}) ...")
    time.sleep(AV_CALL_DELAY)  # 限频
    try:
        resp = requests.get(AV_BASE_URL, params={
            'function': 'TIME_SERIES_DAILY',
            'symbol': 'CHAU',
            'outputsize': 'full',
            'apikey': AV_API_KEY,
        }, timeout=30)
        data = resp.json()
        ts = data.get('Time Series (Daily)', {})
        if not ts:
            note = data.get('Note') or data.get('Information') or ''
            print(f"警告: Alpha Vantage CHAU 返回空. {note[:120]}")
            return None
        records = []
        for d in sorted(ts.keys()):
            if d < start or d > end:
                continue
            records.append({
                'date': d,
                'chau_open': float(ts[d]['1. open']),
                'chau_close': float(ts[d]['4. close']),
            })
        df = pd.DataFrame(records).set_index('date')
        print(f"  获取到 {len(df)} 行 CHAU 数据 ({df.index[0]} ~ {df.index[-1]})")
        return df
    except Exception as e:
        print(f"错误: Alpha Vantage CHAU 获取失败: {e}")
        return None


def run_backtest(cnh_df, chau_df):
    """运行 CNH-CHAU 回测"""
    # 合并（CNH 是外汇每天都有，CHAU 只有美股交易日）
    # 用 CHAU 交易日为基准，CNH 用 forward-fill 补齐
    merged = chau_df.join(cnh_df, how='left')
    merged['cnh_rate'] = merged['cnh_rate'].ffill()
    merged = merged.dropna(subset=['cnh_rate', 'chau_close'])
    merged = merged.sort_index()

    # 过滤回测区间
    merged = merged[(merged.index >= BT_START) & (merged.index <= BT_END)]
    print(f"\n回测区间: {merged.index[0]} ~ {merged.index[-1]}, 共 {len(merged)} 交易日 (美股)")

    # === 回测状态 ===
    nav_value = 1.0
    direction = 'NONE'
    entry_price = None       # CHAU 开仓价
    current_signal = 'NONE'
    prev_signal = 'NONE'

    trades = []
    daily_records = []
    signal_changes = 0

    cnh_rates = merged['cnh_rate'].values
    chau_opens = merged['chau_open'].values
    chau_closes = merged['chau_close'].values
    dates = merged.index.values

    for i in range(SMA_LONG + 1, len(merged)):
        date = dates[i]
        chau_close = chau_closes[i]
        chau_open = chau_opens[i]

        # --- CNH 信号（用前一天收盘，避免 look-ahead bias）---
        # AV FX_DAILY close = 5PM ET, 比 CHAU open 9:30AM ET 晚 7.5 小时
        # 所以信号只能用 T-1 的 CNH 数据，T 日执行
        cnh_current = cnh_rates[i-1]
        sma5 = cnh_rates[i-1-SMA_SHORT+1:i].mean()
        sma10 = cnh_rates[i-1-SMA_MID+1:i].mean()
        sma30 = cnh_rates[i-1-SMA_LONG+1:i].mean()

        prev_signal = current_signal

        below_all = cnh_current < sma5 and cnh_current < sma10 and cnh_current < sma30
        above_all = cnh_current > sma5 and cnh_current > sma10 and cnh_current > sma30

        if below_all or above_all:
            nearest_ma = min(sma5, sma10, sma30) if below_all else max(sma5, sma10, sma30)
            distance_pct = abs(cnh_current - nearest_ma) / cnh_current
            if distance_pct >= DEADZONE_PCT:
                if below_all:
                    current_signal = 'LONG'
                elif above_all:
                    current_signal = 'SHORT'

        # --- 信号切换 → 交易 ---
        if current_signal != prev_signal and current_signal != 'NONE':
            signal_changes += 1

            # 平旧仓（CHAU 价格，无额外杠杆）
            if direction != 'NONE' and entry_price is not None:
                move = (chau_open - entry_price) / entry_price
                if direction == 'SHORT':
                    move = -move
                nav_value *= (1 + move)
                trades.append({
                    'date': date,
                    'action': f'close_{direction.lower()}',
                    'entry': entry_price,
                    'exit': chau_open,
                    'move': move,
                    'nav': nav_value,
                    'win': 1 if move > 0 else 0
                })

            # 开新仓
            entry_price = chau_open
            direction = current_signal

        # --- 每日 mark-to-market ---
        if direction != 'NONE' and entry_price is not None:
            mtm_move = (chau_close - entry_price) / entry_price
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
            'chau_close': round(chau_close, 2),
            'nav': round(display_nav, 6)
        })

    return daily_records, trades, nav_value


def print_summary(daily_records, trades, final_nav):
    """打印回测摘要"""
    df = pd.DataFrame(daily_records)
    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()

    print("\n" + "=" * 60)
    print("CNH-CHAU 回测结果")
    print("=" * 60)

    print(f"\n最终 NAV (realized): {final_nav:.6f}")
    print(f"最终 NAV (mark-to-market): {df['nav'].iloc[-1]:.6f}")
    print(f"交易日数: {len(df)} (美股)")

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

    # 年化收益
    days = len(df)
    years = days / 252
    final_mtm = df['nav'].iloc[-1]
    ann_return = (final_mtm ** (1 / years) - 1) * 100
    print(f"年化收益: {ann_return:.1f}%")

    # 对比表
    print("\n--- 对比 ---")
    print(f"CNH-CHAU (本次): NAV = {df['nav'].iloc[-1]:.2f}x  (CHAU ETF, 自带2x)")
    print(f"CNH-IF   (期货): NAV = 18.02x  (IF 2x杠杆)")
    print(f"CNY-IF   (在岸): NAV = 8.07x   (CNY信号+IF)")

    # 输出每日 NAV CSV
    csv_path = os.path.join(os.path.dirname(__file__), 'cnh-chau-daily-nav.csv')
    df[['date', 'nav']].to_csv(csv_path, index=False)
    print(f"\n每日 NAV 已保存: {csv_path}")

    # 最后信号状态
    last = df.iloc[-1]
    print(f"\n最终状态 ({last['date']}):")
    print(f"  signal = {last['signal']}")
    print(f"  direction = {last['direction']}")
    print(f"  CNH = {last['cnh']}")
    print(f"  CHAU = {last['chau_close']}")


def main():
    parser = argparse.ArgumentParser(description='CNH-CHAU 合成回测')
    parser.add_argument('--cnh-csv', default=None,
                        help='CNH 日线 CSV 路径 (可选, 默认从 Alpha Vantage 获取)')
    parser.add_argument('--chau-csv', default=None,
                        help='CHAU ETF 日线 CSV 路径 (可选, 默认从 Alpha Vantage 获取)')
    args = parser.parse_args()

    # CNH 数据
    if args.cnh_csv:
        cnh_df = pd.read_csv(args.cnh_csv)
        cnh_df['date'] = cnh_df['date'].astype(str)
        cnh_df = cnh_df.set_index('date')
        print(f"  加载 {len(cnh_df)} 行 CNH 数据 (本地 CSV)")
    else:
        # 优先用缓存
        cache_path = os.path.join(os.path.dirname(__file__), 'cnh_av_daily.csv')
        if os.path.exists(cache_path):
            cnh_df = pd.read_csv(cache_path)
            cnh_df['date'] = cnh_df['date'].astype(str)
            cnh_df = cnh_df.set_index('date')
            print(f"  加载 {len(cnh_df)} 行 CNH 数据 (本地缓存)")
        else:
            cnh_df = fetch_cnh_data(CNH_FETCH_START, BT_END)
            if cnh_df is None:
                print("无法获取 CNH 数据，退出")
                sys.exit(1)
            cnh_df.to_csv(cache_path)
            print(f"  CNH 数据已缓存: {cache_path}")

    # CHAU 数据
    if args.chau_csv:
        chau_df = pd.read_csv(args.chau_csv)
        chau_df['date'] = chau_df['date'].astype(str)
        chau_df = chau_df.set_index('date')
        print(f"  加载 {len(chau_df)} 行 CHAU 数据 (本地 CSV)")
    else:
        cache_path = os.path.join(os.path.dirname(__file__), 'chau_av_daily.csv')
        if os.path.exists(cache_path):
            chau_df = pd.read_csv(cache_path)
            chau_df['date'] = chau_df['date'].astype(str)
            chau_df = chau_df.set_index('date')
            print(f"  加载 {len(chau_df)} 行 CHAU 数据 (本地缓存)")
        else:
            chau_df = fetch_chau_data(CNH_FETCH_START, BT_END)
            if chau_df is None:
                print("无法获取 CHAU 数据，退出")
                sys.exit(1)
            chau_df.to_csv(cache_path)
            print(f"  CHAU 数据已缓存: {cache_path}")

    # 运行回测
    daily_records, trades, final_nav = run_backtest(cnh_df, chau_df)
    print_summary(daily_records, trades, final_nav)


if __name__ == '__main__':
    main()
