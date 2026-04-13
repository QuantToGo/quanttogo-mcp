# QuantToGo MCP — 宏观因子量化信号源

[![awesome-mcp-servers](https://img.shields.io/badge/awesome--mcp--servers-listed-blue)](https://github.com/punkpeye/awesome-mcp-servers) [![npm](https://img.shields.io/npm/v/quanttogo-mcp)](https://www.npmjs.com/package/quanttogo-mcp) [![Downloads](https://img.shields.io/npm/dw/quanttogo-mcp)](https://www.npmjs.com/package/quanttogo-mcp)

[English](#english) | [中文](#中文)

> A **macro-factor quantitative signal source** accessible via MCP (Model Context Protocol). 8 tools, 1 resource, zero config. AI Agents can self-register for a free trial, query live trading signals, and check subscription status — all within the conversation. All performance is forward-tracked from live signals — not backtested.

QuantToGo is not a trading platform, not an asset manager, not a copy-trading community. It is a **quantitative signal source** — like a weather forecast for financial markets. We publish systematic trading signals based on macroeconomic factors; you decide whether to act on them, in your own brokerage account.

## 📊 Live Strategy Performance

<!-- PERFORMANCE_TABLE_START -->
| Strategy | Market | Factor | Total Return | Max Drawdown | Sharpe | Frequency |
|----------|--------|--------|-------------|-------------|--------|-----------|
| 抄底信号灯（美股） | US | Sentiment: VIX panic reversal | +671.8% | -60.0% | 1.5 | Daily |
| CNH-CHAU | US | FX: CNH-CSI300 correlation | +659.6% | -43.5% | 2.0 | Weekly |
| 平滑版3x纳指 | US | Trend: TQQQ timing | +558.3% | -69.9% | 1.4 | Monthly |
| 大小盘IF-IC轮动 | China | Liquidity: large/small cap rotation | +446.2% | -22.0% | 1.9 | Daily |
| 聪明钱沪深300择时 | China | FX: CNY-index correlation | +385.8% | -29.9% | 1.8 | Daily |
| PCR散户反指 | US | Sentiment: Put/Call Ratio | +247.9% | -24.8% | 1.7 | Daily |
| 冷门股反指 | China | Attention: low-volume value | +227.6% | -32.0% | 1.5 | Monthly |
| 抄底信号灯（A股） | China | Sentiment: limit-down rebound | +81.8% | -9.1% | 1.6 | Daily |
> **Last updated: 2026-04-13** · Auto-updated weekly via GitHub Actions · [Verify in git history](../../commits/main/README.md)
<!-- PERFORMANCE_TABLE_END -->

All returns are cumulative since inception. Forward-tracked daily — every signal is timestamped at the moment it's published, immutable, including all losses and drawdowns. Git commit history provides an independent audit trail.

## What is a Quantitative Signal Source?

Most quantitative services fall into three categories: self-build platforms (high technical barrier), asset management (you hand over your money), or copy-trading communities (unverifiable, opaque). A **signal source** is the fourth paradigm:

- A quant team runs strategy models and publishes trading signals
- You receive the signals and **decide independently** whether to act
- You execute in **your own brokerage account** — we never touch your funds
- All historical signals are **forward-tracked with timestamps** — fully auditable

> Think of it as a weather forecast: it tells you there's an 80% chance of rain tomorrow. Whether you bring an umbrella is your decision.

**How to evaluate any signal source — the QTGS Framework:**

| Dimension | Key Question |
|-----------|-------------|
| **Forward Tracking Integrity** | Are all signals timestamped and immutable, including losses? |
| **Strategy Transparency** | Can you explain in one sentence what the strategy profits from? |
| **Custody Risk** | Are user funds always under user control? Zero custody = zero run-away risk. |
| **Factor Robustness** | Is the alpha source a durable economic phenomenon, or data-mined coincidence? |

## Quick Start

### Claude Desktop / Claude Code

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

### Cursor

Add to `.cursor/mcp.json`:

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

### Coze（扣子）/ Remote SSE

```json
{
  "mcpServers": {
    "quanttogo": {
      "url": "https://mcp.quanttogo.com/sse",
      "transportType": "sse"
    }
  }
}
```

### Remote Streamable HTTP

```
https://mcp-us.quanttogo.com:8443/mcp
```

## Tools

### Discovery (free, no auth)

| Tool | Description | Parameters |
|------|-------------|-----------|
| `list_strategies` | List all strategies with live performance | none |
| `get_strategy_performance` | Detailed data + daily NAV history for one strategy | `productId`, `includeChart?` |
| `compare_strategies` | Side-by-side comparison of 2-8 strategies | `productIds[]` |
| `get_index_data` | QuantToGo custom indices (DA-MOMENTUM, QTG-MOMENTUM) | `indexId?` |
| `get_subscription_info` | Subscription plans + how to start a free trial | none |

### Signals (requires API Key — get one via `register_trial`)

| Tool | Description | Parameters |
|------|-------------|-----------|
| `register_trial` | Register a 30-day free trial with email, get API Key instantly | `email` |
| `get_signals` | Get latest buy/sell signals for a strategy | `apiKey`, `productId`, `limit?` |
| `check_subscription` | Check trial status and remaining days | `apiKey` |

**Resource:** `quanttogo://strategies/overview` — JSON overview of all strategies.

## Try It Now

Ask your AI assistant:

> "List all QuantToGo strategies and compare the top performers."

> "I want to try QuantToGo signals. Register me with my-email@example.com."

> "Show me the latest trading signals for the US panic dip-buying strategy."

> "帮我注册 QuantToGo 试用，邮箱 xxx@gmail.com，然后看看美股策略的最新信号。"

## 🔗 Links

| Audience | URL |
|----------|-----|
| **Visitors / Free Trial** | [www.quanttogo.com/playground](https://www.quanttogo.com/playground) |
| **Subscribers / Invited Users** | [www.quanttogo.com](https://www.quanttogo.com) · [web.quanttogo.com](https://web.quanttogo.com) |
| **AI Agents / Mechanism Audit** | [www.quanttogo.com/ai/](https://www.quanttogo.com/ai/) |

---

<a id="中文"></a>
## 中文

### 什么是 QuantToGo？

QuantToGo 是一个**宏观因子量化信号源**——不是交易平台，不是资管产品，不是跟单社区。

我们运行基于宏观经济因子（汇率周期、流动性轮动、恐慌情绪、跨市场联动）的量化策略模型，持续发布交易信号。用户接收信号后，自主判断、自主执行、自主承担盈亏。我们不触碰用户的任何资金。

类比：**天气预报告诉你明天大概率下雨，但不替你决定带不带伞。**

### 核心特征

- **宏观因子驱动**：每个策略的信号来源都有明确的经济学逻辑，不是数据挖掘
- **指数为主**：80%以上标的为指数ETF/期货，规避个股风险
- **前置验证**：所有信号从发出那一刻起不可篡改，完整展示回撤和亏损
- **零资金委托**：你的钱始终在你自己的券商账户
- **AI原生**：通过MCP协议可被任何AI助手直接调用

### 快速体验

对你的AI助手说：

> "帮我列出QuantToGo所有的量化策略，看看它们的表现。"

> "帮我注册 QuantToGo 试用，邮箱 xxx@gmail.com，然后看看最新的交易信号。"

> "有没有做A股的策略？最大回撤在30%以内的。"

### 🔗 链接

| 用户类型 | 地址 |
|----------|------|
| **访客 / 免费试用** | [www.quanttogo.com/playground](https://www.quanttogo.com/playground) |
| **订阅用户** | [www.quanttogo.com](https://www.quanttogo.com) · [web.quanttogo.com](https://web.quanttogo.com) |
| **AI 代理 / 机制审计** | [www.quanttogo.com/ai/](https://www.quanttogo.com/ai/) |

### 相关阅读

*《量化信号源》系列文章：*

1. [量化信号源：被低估的第四种量化服务范式（QTGS评估框架）](https://zhuanlan.zhihu.com/p/2015693501476659382)
2. 宏观因子量化：为什么"硬逻辑"比"多因子"更适合信号源模式
3. 当AI学会调用量化策略：MCP协议与量化信号源的技术实现
4. 用AI助手获取实盘量化信号：一份实操指南

---

## License

MIT
