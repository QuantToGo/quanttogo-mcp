# quanttogo-mcp

MCP server for [QuantToGo](https://www.quanttogo.com) — a quantitative trading platform with live-tracked strategies across US and China markets.

> **This server exposes exactly 4 tools and 1 resource.** All data comes from QuantToGo's live production API. No API key required.

## Tools

### `list_strategies`

List all quantitative trading strategies with live performance metrics.

- **Parameters:** none
- **Returns:** Array of strategies with fields: `productId`, `name`, `market`, `totalReturn`, `maxDrawdown`, `recent1dReturn`, `recent30dReturn`, `status`

### `get_strategy_performance`

Get detailed performance data for a single strategy, including daily NAV (net asset value) history.

- **Parameters:**
  - `productId` (string, required) — Strategy ID from `list_strategies`, e.g. `"PROD-E3X"`
  - `includeChart` (boolean, optional, default: true) — Include daily NAV data points
- **Returns:** Strategy details + chart data: `{ productId, name, market, totalReturn, maxDrawdown, recent1dReturn, recent30dReturn, tradeCount, chart: { totalPoints, lastUpdated, dataPoints: [{d, nav}] } }`

### `get_index_data`

Get QuantToGo custom market indices.

- **Parameters:**
  - `indexId` (enum, optional) — `"DA-MOMENTUM"` or `"QTG-MOMENTUM"`. Omit for summary of all indices.
- **Returns:**
  - Summary mode: Array of `{ indexId, name, shortDesc, latestValue, dailyChange, dailyChangePercent, updateDate }`
  - Detail mode: Full index data including `dataPoints: [{date, value}]` and `components` (for QTG-MOMENTUM)

**Available indices:**

| Index | Description |
|-------|-------------|
| `DA-MOMENTUM` | China A-share momentum-weighted index (CSI300 + ChiNext) |
| `QTG-MOMENTUM` | Strategy-weighted momentum index across all QuantToGo products |

### `compare_strategies`

Compare 2–8 strategies side by side.

- **Parameters:**
  - `productIds` (string[], required, 2–8 items) — Array of product IDs
- **Returns:** Array of `{ productId, name, market, totalReturn, maxDrawdown, recent1dReturn, recent30dReturn }`

## Resource

| URI | Description |
|-----|-------------|
| `quanttogo://strategies/overview` | JSON overview of all strategies and current performance |

## Installation

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

## About QuantToGo

QuantToGo runs 8 live-tracked quantitative strategies spanning US equities (options, momentum, dip-buying) and China A-shares (index futures, sector rotation). All performance data is forward-tracked daily via automated signal pipelines — not backtested.

## License

MIT
