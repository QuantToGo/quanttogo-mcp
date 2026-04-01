# ============================================================
# JQ 研究环境运行：导出 IF 主力合约日线数据
# 在 JQ "研究" 页面新建 notebook，粘贴运行
# 输出 CSV 格式，复制保存为 if_dominant_daily.csv
# ============================================================

from jqdata import *
import pandas as pd

START = '2019-11-01'   # 提前2个月，给SMA30预热
END = '2026-03-14'

dates = get_trade_days(start_date=START, end_date=END)

# 按日获取主力合约 + 价格
records = []
prev_dom = None
for d in dates:
    dom = get_dominant_future('IF', d)
    if not dom:
        continue
    data = get_price(dom, end_date=d, count=1, fields=['open', 'close'])
    if data is not None and len(data) > 0:
        records.append({
            'date': str(d),
            'contract': dom,
            'open': round(data['open'].iloc[-1], 2),
            'close': round(data['close'].iloc[-1], 2),
            'rolled': 1 if dom != prev_dom and prev_dom is not None else 0
        })
        prev_dom = dom

df = pd.DataFrame(records)
print(f"共 {len(df)} 行, {df['date'].iloc[0]} ~ {df['date'].iloc[-1]}")
print(f"换月次数: {df['rolled'].sum()}")
print()

# 写入文件（从 JQ 文件管理器下载）
csv_path = 'if_dominant_daily.csv'
df.to_csv(csv_path, index=False)
print(f"已保存: {csv_path}，请从 JQ 文件管理器下载")
