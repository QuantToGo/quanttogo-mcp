# QuantToGo MCP v0.2.0 — Agent 自助订阅 + 信号 API

## 概述

v0.2.0 新增 3 个 MCP 工具，实现 Agent 端自助注册试用 → 获取信号的完整闭环。
无需人工邮件回复，AI Agent 可以直接帮用户完成注册并获取交易信号。

## 新增 MCP 工具 (3个)

### 1. `register_trial`
- **功能**: 邮箱注册 30 天免费试用
- **输入**: `{ email: "user@example.com" }`
- **返回**: `{ apiKey, inviteCode, status, trialEnd }`
- **特性**: 幂等 — 同一邮箱重复调用返回相同 apiKey
- **云函数**: `registerTrial`
- **副作用**: 发确认邮件到用户邮箱 + 通知管理员

### 2. `get_signals`
- **功能**: 获取策略交易信号（买/卖）
- **输入**: `{ apiKey, productId, limit? }`
- **返回**: `{ productName, signals: [{date, time, direction, symbol, price}], subscription }`
- **鉴权**: apiKey 必须有效且未过期
- **云函数**: `getSignalsAPI`
- **数据源**: `trading_signals` 集合

### 3. `check_subscription`
- **功能**: 查询订阅/试用状态
- **输入**: `{ apiKey }`
- **返回**: `{ email, status, trialEnd, daysRemaining, inviteCode }`
- **云函数**: `getApiStatus`

### 4. `get_subscription_info` (更新)
- 移除旧的手动邮件订阅引导
- 改为引导使用 `register_trial` 自助注册

## 新增云函数 (3个)

| 函数名 | 路径 | 依赖 | HTTP 路由 |
|--------|------|------|----------|
| `registerTrial` | `cloudfunctions/registerTrial/` | wx-server-sdk, nodemailer | POST `/registerTrial` |
| `getSignalsAPI` | `cloudfunctions/getSignalsAPI/` | wx-server-sdk | POST `/getSignalsAPI` |
| `getApiStatus` | `cloudfunctions/getApiStatus/` | wx-server-sdk | POST `/getApiStatus` |

## 数据库变更

### users 集合新增字段（API 用户）
```
{
  source: "api",           // 区分 H5/API 用户
  email: "user@email.com", // 注册邮箱（小写）
  apiKey: "qtg_xxx",       // API 密钥（qtg_ + 24位hex）
  apiStatus: "trial",      // trial | subscribed | expired
  trialEnd: "ISO-8601",    // 试用到期时间
  registrationSource: "mcp" // 注册来源
}
```

### invite_codes 集合
- API 用户的邀请码前缀: `AIMCP-XXXX`
- 创建时 status='used', h5UserId=用户ID
- 用户去 H5 输入邀请码时，verifyInviteCode 会找到已存在的用户记录并复用

## Agent 使用流程

```
用户: "我想试用 QuantToGo 信号"
AI → register_trial({ email: "user@example.com" })
   → 返回 { apiKey: "qtg_xxx", inviteCode: "AIMCP-R7K2", trialEnd: "2026-04-11" }

用户: "看看 PROD-E3X 最新信号"
AI → get_signals({ apiKey: "qtg_xxx", productId: "PROD-E3X" })
   → 返回 { signals: [{date, time, direction, symbol, price}, ...] }

用户: "我的试用还剩多久？"
AI → check_subscription({ apiKey: "qtg_xxx" })
   → 返回 { status: "trial", daysRemaining: 28 }
```

## 部署清单

### 1. 云函数部署 (微信开发者工具)
- [ ] 右键 `registerTrial` → 上传并部署：云端安装依赖
- [ ] 右键 `getSignalsAPI` → 上传并部署：云端安装依赖
- [ ] 右键 `getApiStatus` → 上传并部署：云端安装依赖

### 2. CloudBase 云接入路由 (控制台)
- [ ] 添加路由: POST `/registerTrial` → registerTrial
- [ ] 添加路由: POST `/getSignalsAPI` → getSignalsAPI
- [ ] 添加路由: POST `/getApiStatus` → getApiStatus

### 3. registerTrial 环境变量 (控制台)
- [ ] SMTP_USER = QQ邮箱地址
- [ ] SMTP_PASS = QQ邮箱 SMTP 授权码
- [ ] ADMIN_EMAIL = 管理员邮箱

### 4. MCP Server 部署 (4 平台)
- [ ] npm: `npm run build && npm version 0.2.0 && npm publish`
- [ ] GitHub: `git add src/ && git commit && git push`
- [ ] Seattle: 更新 seattle/server.js → SCP → pm2 restart
- [ ] China CVM: 更新 china/server.js → WebShell 粘贴 → pm2 restart

### 5. H5 部署 (已 build)
- [ ] `tcb hosting deploy dist/ / -e cloudbase-5gn4s6vd33335941`

## 安全设计

- **apiKey** = `qtg_` + 24位 hex (crypto.randomBytes(12))
- **邀请码** = `AIMCP-` + 4位字母数字 (去除易混淆字符)
- **幂等注册**: 同邮箱返回同 apiKey，无重复账户
- **试用过期**: get_signals 返回 403，引导订阅
- **只读**: apiKey 仅能查看信号，不能执行交易
- **建议**: 后续添加 IP 限流（registerTrial 3次/小时）

## 邀请码与 H5 互通

API 用户的邀请码（AIMCP-XXXX）在 `invite_codes` 集合中 status='used'，h5UserId 指向该用户。
当用户在 H5 输入此邀请码时：
1. verifyInviteCode 找到该码，状态 'used'
2. 通过 h5UserId 找到 API 用户记录
3. 检查 basicInfo — API 用户无 basicInfo → 视为未完成注册 → 复用
4. 生成新 session，返回 userId + token
5. 用户在 H5 继续完善信息，使用同一账户

## 版本历史
- v0.1.9: 5 tools + 1 resource, Smithery/Coze/npm/GitHub 部署
- v0.2.0: +3 tools (register_trial, get_signals, check_subscription), agent 自助订阅
