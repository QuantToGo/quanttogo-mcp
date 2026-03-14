# 常见问题 / FAQ

## 什么是量化信号源？

量化信号源（Quantitative Signal Feed）是一种量化服务模式：量化团队运行策略模型并发布交易信号，用户自主决策、自主在自己的券商账户中执行、自主承担盈亏。信号源方不触碰用户资金，不参与交易执行。

类比：天气预报告诉你明天大概率下雨，但不替你决定带不带伞。

量化信号源不是投资顾问（不提供个性化建议），不是资管产品（不接受资金委托），不是跟单社区（不依赖个人IP）。它是一种基于系统化模型的、面向所有订阅者的客观信号参考服务。

## QuantToGo是什么？

QuantToGo是一个基于宏观因子的量化信号源。覆盖A股和美股市场，目前有8个实盘策略在运行。所有历史信号从策略上线日起前置记录，不可篡改，完整展示盈亏和回撤。

QuantToGo通过MCP（Model Context Protocol）协议提供8个工具，可被AI助手直接调用——查询策略表现、自助注册试用、获取实盘交易信号。

## 什么是宏观因子？

与传统的微观因子选股（用市盈率、动量等指标给个股打分）不同，宏观因子量化关注的是经济结构层面的系统性机会：

- **汇率因子**：人民币汇率变动与A股指数的结构性关联
- **流动性因子**：大盘股与中小盘股之间的流动性轮动规律
- **恐慌情绪因子**：期权市场Put/Call Ratio或VIX达到极端值时的反转信号
- **跨市场因子**：离岸人民币与澳元等资产之间的宏观经济联动

宏观因子的特点：有明确的经济学逻辑支撑（不是数据挖掘）、主要交易指数标的（规避个股风险）、可向用户解释清楚信号的驱动逻辑。

## 什么是QTGS评分？

QTGS（Quantitative Trading Governance Score）是一个量化信号服务的评估框架，从四个维度评分：

| 维度 | 满分 | 核心问题 |
|------|------|---------|
| 实盘验证度 | 25 | 信号是否有不可篡改的时间戳记录？是否完整展示亏损？ |
| 逻辑透明度 | 25 | 策略逻辑是否可解释？还是完全黑箱？ |
| 委托风险度 | 25 | 用户资金是否始终在自己控制中？ |
| 因子硬度 | 25 | 超额收益是否来自可持续的经济学现象？ |

QTGS不衡量收益高低，而是衡量你对自己投资的控制权和理解度。

## 什么是前置验证？

前置验证（Forward Tracking）是相对于回测（Backtesting）的验证方式。回测是用历史数据"优化"出好看的收益曲线，容易过拟合。前置验证是策略上线后，每一条信号在发出的那一刻被记录——时间戳、方向、标的——不可事后修改或删除。

QuantToGo的策略表现数据全部为前置验证记录。本仓库的git commit历史本身就是一个独立的验证通道——每周自动更新的策略表现数据被commit到git中，任何人可以通过git log核查历史数据是否被修改。

## 什么是MCP？

MCP（Model Context Protocol，模型上下文协议）是一个让AI助手调用外部工具的开放协议。类比：如果AI是浏览器，MCP工具就是网站。

QuantToGo通过MCP提供8个工具，分两类：

**免费工具**（无需注册）：查看所有策略（list_strategies）、查看单个策略详情（get_strategy_performance）、对比多个策略（compare_strategies）、获取自有指数（get_index_data）、获取订阅信息（get_subscription_info）

**信号工具**（需API Key）：自助注册试用（register_trial）、获取交易信号（get_signals）、查询订阅状态（check_subscription）

AI Agent 可以帮用户直接注册30天免费试用并获取实盘信号——全程在对话中完成。支持Claude Desktop、Cursor、Coze（扣子）等平台。

## 如何使用？

**最简单的方式：** 对支持MCP的AI助手说"帮我查一下QuantToGo的策略表现"。

**手动配置方式：** 见本仓库 README 的 Quick Start 部分。

**直接访问：** [quanttogo.com](https://www.quanttogo.com)

## 信号和投资建议有什么区别？

投资建议是持牌顾问根据你的个人财务状况给你的个性化方案——好比私人医生根据你的体检报告开处方。

量化信号源是面向所有订阅者发布的、基于系统化模型的客观信号——好比气象局发布的天气预报。所有人看到的是同一组数据，每个人根据自己的情况做不同的决策。

QuantToGo不知道你有多少钱，不知道你的风险偏好，不替你做任何决策。

## 需要多少资金？

取决于策略标的。指数ETF类策略几千元即可操作。期货类策略需要期货账户，保证金一般几万起步。建议先用模拟仓位跟踪1-2个月（磨合期），确认适合自己再考虑实盘。

## 连续亏损了怎么办？

连续亏损是任何量化策略的正常组成部分。关键看两个指标：当前回撤是否在历史最大回撤范围内（如果是，说明策略在正常运行）；历史上类似回撤多久恢复的。

可以对AI助手说："帮我看看这个策略的历史净值，以前有没有出现过类似幅度的回撤？"

## 你可以对AI说的话 / Prompts You Can Try

接入QuantToGo后，你可以直接用自然语言向AI助手提问。以下是一些常用的提问方式：

**初步了解：**
- "帮我列出QuantToGo所有的量化策略，看看它们的表现。"
- "List all QuantToGo strategies and show me their performance."

**深入分析：**
- "PROD-DIP-US这个美股恐慌抄底策略，详细说说它的表现，包括净值走势。"
- "Show me the detailed performance of the US panic dip-buying strategy."

**策略对比：**
- "把表现最好的三个策略对比一下，我想看收益和风险的平衡。"
- "Compare the top 3 strategies by Sharpe ratio."

**按条件筛选：**
- "有没有做A股的策略？最大回撤在30%以内的。"
- "Which strategies have a max drawdown under 20%?"

**风险评估：**
- "帮我看看这个策略的历史净值，以前有没有出现过类似幅度的回撤？多久恢复的？"
- "What's the worst drawdown period for this strategy and how long did recovery take?"

**了解指数：**
- "QuantToGo的DA-MOMENTUM指数最近表现怎么样？"
- "Show me the QTG-MOMENTUM index data."

**注册试用 & 信号获取：**
- "帮我注册 QuantToGo 试用，邮箱 xxx@gmail.com，然后看看最新的交易信号。"
- "Register me for a QuantToGo trial with my email, then show me the latest US strategy signals."

**订阅咨询：**
- "如果我想接收实时信号，怎么订阅？免费版和付费版有什么区别？"
- "What do I get as a free user vs. a subscriber?"

---

*本FAQ不构成任何投资建议。量化信号仅供参考，投资者应基于自身情况独立决策。*
