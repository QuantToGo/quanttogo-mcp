# 风控单 QuantToGo — MCP Server

**QuantToGo 说法百科**：大家买卖股票的理由，用 A 股和美股的历史数据查过一遍。网址 [quanttogo.com](https://quanttogo.com)。本项目是它的 MCP 服务「风控单 QuantToGo」，在你自己的 AI 里用。

[![npm](https://img.shields.io/npm/v/quanttogo-mcp)](https://www.npmjs.com/package/quanttogo-mcp) [![Downloads](https://img.shields.io/npm/dw/quanttogo-mcp)](https://www.npmjs.com/package/quanttogo-mcp)

[中文](#中文) | [English](#english)

**替你盯着手上的 A 股持仓。** 给一个标的（个股、行业、ETF、基金、宽基指数），返回它三个月内跌 ≥15% 的概率、平时的概率、在不在安全区、过热档和红灯、警戒线三档；核对你的持有理由；建一张风控单，每天收盘后检查理由、过热档、警戒线，有变化才告诉你。

- 远程地址（Streamable HTTP）：`https://mcp.quanttogo.com/v2`
- 旧式 SSE：`https://mcp.quanttogo.com/v2/sse`
- 网站：[www.quanttogo.com/risk](https://www.quanttogo.com/risk/)

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

只认旧式 SSE 的平台填 `https://mcp.quanttogo.com/v2/sse`。

### 工具

| 工具 | 做什么 | 要手机号 |
|---|---|---|
| `risk_check` | 查风险读数：三个月内跌 ≥15% 的概率、平时的概率、它自己历史的概率、在不在安全区、最坏情况、过热档和红灯、警戒线三档（1.0 / 1.5 / 2.0 倍波动带）、按哪个标的代算 | 否 |
| `verify_reasons` | 核对持有理由（九类标签逐条成立 / 已证伪，附依据）；七类「不算理由」回一句话 | 否 |
| `create_risk_order` | 建风控单：理由必填，没有理由不建；同标的已在盯不重复建 | 是 |
| `my_risk_orders` | 查我的风控单（在盯 / 已结束 / 单张） | 是 |
| `market_now` | 市场环境：全市场过热档、大盘波动、亮红灯的行业、31 个行业各自的概率 | 否 |
| `ledger_review` | 台账复盘：红灯亮了之后真的跌了吗，最近几次逐条 | 否 |
| `evidence_card` | 广成子证据卡：某行业今天的机会分和证据充分度（只读） | 否 |
| `login` | 手机号登录 / 注册，和网站同一个账户 | 是 |

### 账户

建单、查单要手机号。和网站 QuantToGo 是同一套账户：手机号查到就是你，查不到就按这个手机号新建（限时免费）。手机号是标识，不是密码。

### 试一试

对你的 AI 助手说：

> 我拿着招商蛇口，帮我看看风险。

> 今天市场热不热？哪些行业亮红灯了？

> 帮我建一张风控单：招商蛇口，理由是估值见底。

> 红灯亮了之后，历史上真的跌了吗？

---

<a id="english"></a>
## English

**A risk desk for A-share holdings, exposed as MCP tools.** Give it a ticker, an industry, an ETF or a fund; it returns the probability of a ≥15% drop within three months (vs. the base rate and the name's own history), whether it sits in the safe zone, the overheat level and red-light status, and three stop-line options (1.0 / 1.5 / 2.0 × the 60-day volatility band). It checks the reasons you hold a position, and opens a "risk order" that is re-checked after every close — you are told only when something changes.

Remote endpoint (Streamable HTTP): `https://mcp.quanttogo.com/v2` · legacy SSE: `https://mcp.quanttogo.com/v2/sse`

This npm package is a thin stdio bridge to that endpoint; the tool list is fetched from the server at start.

| Tool | Purpose | Phone needed |
|---|---|---|
| `risk_check` | Risk readings for one name | no |
| `verify_reasons` | Check holding reasons against data | no |
| `create_risk_order` | Open a risk order (reason required) | yes |
| `my_risk_orders` | List / inspect my risk orders | yes |
| `market_now` | Market-wide overheat, volatility, red lights | no |
| `ledger_review` | Did red lights actually precede drops? | no |
| `evidence_card` | Industry evidence card (read-only) | no |
| `login` | Sign in / sign up with a phone number | yes |

Accounts are shared with the website; a phone number identifies the user (same as the website).

## License

MIT
