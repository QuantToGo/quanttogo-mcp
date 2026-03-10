# QuantToGo 量化交易 MCP Server

查询 [QuantToGo](https://www.quanttogo.com) 量化交易平台的实时策略业绩、持仓信号和市场指数数据。

> 提供 4 个工具和 1 个资源。所有数据来自 QuantToGo 生产环境 API，无需 API Key。

## 工具列表

### `list_strategies`

列出所有量化交易策略及实时业绩指标。

- **参数：** 无
- **返回：** 策略数组，包含 `productId`、`name`、`market`（美股/A股）、`totalReturn`、`maxDrawdown`、`recent1dReturn`、`recent30dReturn`、`status`

### `get_strategy_performance`

获取单个策略的详细业绩数据，包括每日净值历史。

- **参数：**
  - `productId`（string，必填）— 策略 ID，如 `"PROD-E3X"`
  - `includeChart`（boolean，可选，默认 true）— 是否包含每日净值数据
- **返回：** 策略详情 + 净值曲线数据

### `get_index_data`

获取 QuantToGo 自定义市场指数。

- **参数：**
  - `indexId`（可选）— `"DA-MOMENTUM"` 或 `"QTG-MOMENTUM"`，不填返回所有指数摘要
- **返回：** 指数最新值、日涨跌、历史数据

| 指数 | 说明 |
|------|------|
| `DA-MOMENTUM` | A股动量加权指数（沪深300+创业板） |
| `QTG-MOMENTUM` | 策略加权动量指数 |

### `compare_strategies`

对比 2-8 个策略的核心指标。

- **参数：**
  - `productIds`（string[]，必填，2-8个）— 策略 ID 数组
- **返回：** 对比表格数据

## 资源

| URI | 说明 |
|-----|------|
| `quanttogo://strategies/overview` | 所有策略及当前业绩的 JSON 概览 |

## 安装配置

```json
{
  "mcpServers": {
    "quanttogo": {
      "command": "npx",
      "args": ["-y", "quanttogo-mcp"]
    }
  }
}
```

## 关于 QuantToGo

QuantToGo 运营 8 个实盘跟踪的量化策略，覆盖美股（期权、动量、抄底）和 A 股（股指期货、板块轮动）市场。所有业绩数据均为实盘前瞻跟踪，非回测数据。

## 远程 MCP

本项目支持[一键部署到腾讯云开发平台](https://docs.cloudbase.net/ai/mcp/develop/host-mcp)，提供远程 Streamable HTTP 访问。

## 许可证

MIT
