# QuantToGo 理由指数 — MCP Server

[![npm](https://img.shields.io/npm/v/quanttogo-mcp)](https://www.npmjs.com/package/quanttogo-mcp) [![Downloads](https://img.shields.io/npm/dw/quanttogo-mcp)](https://www.npmjs.com/package/quanttogo-mcp)

[中文](#中文) | [English](#english)

**QuantToGo 理由指数：把买卖股票的理由做成指数**——腰斩指数、放量新高指数、国家队增持指数……每条理由今天有多少只股票符合、比昨天多了还是少了、2015 年以来走了多少，A 股和美股分开算。另有 QTG 风险指数，把 31 个行业的过热程度合成一个数。

- 网站：[quanttogo.com](https://quanttogo.com)
- 远程地址（Streamable HTTP）：`https://mcp.quanttogo.com/v2`
- 旧式 SSE：`https://mcp.quanttogo.com/v2/sse`

---

<a id="中文"></a>
## 中文

### 接入

**Claude Desktop / Claude Code / Cursor**（本包是到远程服务的 stdio 桥）

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

**扣子（Coze）/ 任何支持远程 MCP 的平台**

```json
{
  "mcpServers": {
    "quanttogo": {
      "url": "https://mcp.quanttogo.com/v2",
      "transportType": "streamable-http"
    }
  }
}
```

### 工具

| 工具 | 做什么 |
|---|---|
| `reason_index` | 列出全部理由指数；或者查一个指数：今天符合的只数和它在一年里的位置、A 股和美股点位、比上一个交易日涨跌、2015 年以来涨跌和同期大盘 |
| `reason_index_stocks` | 某个理由指数今天的成分股，按市值排 |
| `stock_reasons` | 一只股票今天在哪几个理由指数里 |
| `qtg_risk_index` | QTG 风险指数：全市场和 31 个申万一级行业的风险指数、今天亮红灯的行业、历史上同一区间之后沪深300 跌 15% 以上的概率 |
| `risk_check` | 一只 A 股标的的风险读数：三个月内跌 ≥15% 的概率、过热档、警戒线三档 |
| `verify_reasons` | 核对用户的持有理由今天还成不成立 |
| `create_risk_order` | 建一张单子，每天收盘后检查理由和警戒线，有变化才告诉用户（要手机号） |
| `my_risk_orders` | 查这个手机号名下的单子 |
| `market_now` | 今天的市场环境和 31 个行业的过热档 |
| `ledger_review` | 红灯亮了之后真的跌了吗：历次记录 |
| `evidence_card` | 某个行业的证据卡 |
| `login` | 手机号登录/注册，和网站同一套账户 |

### 问法举例

- 腰斩指数今天多少点？
- 今天有哪些股票符合「放量新高」？
- 贵州茅台今天在哪几个理由指数里？
- QTG 风险指数现在多少？医药生物风险大不大？

---

<a id="english"></a>
## English

**QuantToGo Reason Index: every reason people buy or sell stocks, turned into an index** — Halved Index, Breakout Index, National Team Index… how many stocks fit each reason today, versus yesterday, and since 2015, for China A-shares and US stocks separately. Plus the QTG Risk Index: overheating across 31 sectors in one number.

- Website: [quanttogo.com](https://quanttogo.com)
- Remote (Streamable HTTP): `https://mcp.quanttogo.com/v2`
- Legacy SSE: `https://mcp.quanttogo.com/v2/sse`

### Install

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

### Tools

| Tool | What it does |
|---|---|
| `reason_index` | List all reason indexes, or look up one: stocks that fit today and where that count sits in the past year, A-share and US index level, change vs the previous trading day, change since 2015 vs the market |
| `reason_index_stocks` | Today's member stocks of a reason index, by market cap |
| `stock_reasons` | Which reason indexes a stock is in today |
| `qtg_risk_index` | QTG Risk Index for the whole market and 31 SW level-1 sectors, sectors with a red light today, and how often CSI 300 fell 15%+ afterwards |
| `risk_check` | Risk readings for one A-share target |
| `verify_reasons` | Check whether a holder's reasons still hold today |
| `create_risk_order` | Watch a holding and its reasons daily after close (phone number required) |
| `my_risk_orders` | Orders under a phone number |
| `market_now` | Today's market and overheating across 31 sectors |
| `ledger_review` | What happened after past red lights |
| `evidence_card` | Evidence card for a sector |
| `login` | Phone login / sign-up, same account as the website |

Tool descriptions and answers are in Chinese.

## License

MIT
