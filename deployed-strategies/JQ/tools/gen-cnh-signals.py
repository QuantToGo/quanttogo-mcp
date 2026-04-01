#!/usr/bin/env python3
# ============================================================
# 从 Alpha Vantage CNH 数据生成每日信号文件
# 输出 CSV: date,signal (LONG/SHORT/NONE)
# 上传到 JQ 研究环境后，由 CNH-IF-jq-backtest.py 读取
# ============================================================

import pandas as pd
import numpy as np
import os
import sys

SMA_SHORT = 5
SMA_MID = 10
SMA_LONG = 30
DEADZONE_PCT = 0.001

# CNH 数据（AV缓存）
cnh_csv = os.path.join(os.path.dirname(__file__), 'cnh_av_daily.csv')
if not os.path.exists(cnh_csv):
    print(f"错误: 找不到 {cnh_csv}")
    print("请先运行 cnh-if-backtest.py 或 cnh-chau-backtest.py 获取 AV 数据缓存")
    sys.exit(1)

cnh_df = pd.read_csv(cnh_csv)
cnh_df['date'] = cnh_df['date'].astype(str)
cnh_df = cnh_df.set_index('date').sort_index()
print(f"加载 {len(cnh_df)} 行 CNH 数据 ({cnh_df.index[0]} ~ {cnh_df.index[-1]})")

cnh_rates = cnh_df['cnh_rate'].values
dates = cnh_df.index.values

current_signal = 'NONE'
signals = []

for i in range(SMA_LONG, len(cnh_df)):
    date = dates[i]
    cnh_current = cnh_rates[i]
    sma5 = cnh_rates[i-SMA_SHORT+1:i+1].mean()
    sma10 = cnh_rates[i-SMA_MID+1:i+1].mean()
    sma30 = cnh_rates[i-SMA_LONG+1:i+1].mean()

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

    signals.append({'date': date, 'signal': current_signal})

df = pd.DataFrame(signals)
out_path = os.path.join(os.path.dirname(__file__), 'cnh_signals.csv')
df.to_csv(out_path, index=False)
print(f"输出 {len(df)} 天信号 → {out_path}")
print(f"  LONG: {(df['signal']=='LONG').sum()} 天")
print(f"  SHORT: {(df['signal']=='SHORT').sum()} 天")
print(f"  NONE: {(df['signal']=='NONE').sum()} 天")
print(f"  信号切换次数: {(df['signal'] != df['signal'].shift()).sum() - 1}")
