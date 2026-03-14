# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] - 2026-03-11

### Added
- **`register_trial`** — AI Agents can register a 30-day free trial with just an email. Returns API key instantly. Idempotent (same email = same key).
- **`get_signals`** — Retrieve timestamped buy/sell trading signals for any strategy. Requires API key from `register_trial`.
- **`check_subscription`** — Check trial status, remaining days, and account details.
- Complete agent self-service flow: `register_trial` → `get_signals` → `check_subscription`, all within a single conversation.
- Confirmation email sent on registration with credentials and next steps.

### Changed
- `get_subscription_info` now guides users to `register_trial` instead of manual email-based onboarding.
- Tool descriptions updated with richer context for better AI agent discovery.

## [0.1.9] - 2026-03-09

### Added
- Initial public release on npm, GitHub, and remote endpoints.
- 5 discovery tools: `list_strategies`, `get_strategy_performance`, `compare_strategies`, `get_index_data`, `get_subscription_info`.
- 1 MCP resource: `quanttogo://strategies/overview`.
- Support for stdio (npm), Streamable HTTP (remote), and SSE (legacy) transports.
- GitHub Actions workflow for weekly auto-update of strategy performance in README.
- Listed on [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers).
