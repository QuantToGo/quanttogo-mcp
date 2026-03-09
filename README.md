# quanttogo-mcp

A Model Context Protocol (MCP) server that provides AI agents with access to QuantToGo's quantitative trading strategies, live-tracked performance data, and custom market indices.

## Features

### Tools

| Tool | Description |
|------|-------------|
| `list_strategies` | List all strategies with live performance metrics |
| `get_strategy_performance` | Get detailed strategy data including daily NAV history |
| `get_index_data` | Get custom market indices (DA-MOMENTUM, QTG-MOMENTUM) |
| `compare_strategies` | Compare multiple strategies side-by-side |

### Resources

| URI | Description |
|-----|-------------|
| `quanttogo://strategies/overview` | Strategy overview with current performance |

## What is QuantToGo?

QuantToGo is a quantitative trading platform offering:

- **8 live-tracked strategies** spanning US equities and China A-shares
- **2 custom indices**: DA-MOMENTUM (China A-share momentum) and QTG-MOMENTUM (strategy-weighted)
- **Verified live track records** with daily NAV updates via automated signal pipelines
- Strategies include: options PCR signals, momentum rotation, dip-buying, and index futures

## Installation

### Claude Desktop / Claude Code

Add to your MCP config:

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

### Manual

```bash
npm install -g quanttogo-mcp
quanttogo-mcp
```

## Example Usage

Once connected, an AI agent can:

```
"List all QuantToGo strategies and their recent performance"
→ calls list_strategies

"Show me the NAV history for the E3X momentum strategy"
→ calls get_strategy_performance({productId: "PROD-E3X"})

"Compare the PCR and DIP-US strategies"
→ calls compare_strategies({productIds: ["PROD-PCR", "PROD-DIP-US"]})

"What's the latest DA-MOMENTUM index value?"
→ calls get_index_data({indexId: "DA-MOMENTUM"})
```

## Data Sources

All data is live from QuantToGo's production platform:

- Strategy NAVs updated daily via JoinQuant webhook pipeline
- Index values calculated daily from East Money market data
- All performance is forward-tracked (not backtested)

## License

MIT
