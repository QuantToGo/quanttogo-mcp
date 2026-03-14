#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const API_BASE = "https://www.quanttogo.com";

// ── Helpers ──────────────────────────────────────────────────

async function callAPI(fn: string, body: Record<string, unknown> = {}): Promise<unknown> {
  const resp = await fetch(`${API_BASE}/${fn}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`API ${fn} returned ${resp.status}`);
  return resp.json();
}

// ── Server Factory ──────────────────────────────────────────

function createServer(): McpServer {
  const server = new McpServer({
    name: "quanttogo-mcp",
    version: "0.2.0",
  });

  registerTools(server);
  return server;
}

// ── Register Tools ──────────────────────────────────────────

function registerTools(server: McpServer): void {

// ── Tool: list_strategies ────────────────────────────────────

server.tool(
  "list_strategies",
  "List all macro-factor quantitative strategies on QuantToGo — a forward-tracked signal source covering US and China markets. Returns strategy name, market, total return, max drawdown, Sharpe ratio, and recent returns. All performance is tracked from live signals, not backtested.",
  {},
  async () => {
    const res = (await callAPI("getProducts")) as {
      code: number;
      data: Record<string, unknown>[];
    };
    if (res.code !== 0 || !Array.isArray(res.data)) {
      return { content: [{ type: "text" as const, text: "Failed to fetch strategies" }] };
    }

    const strategies = res.data.map((p) => ({
      productId: p.productId,
      name: p.name,
      market: p.market || "—",
      totalReturn: p.totalReturn ?? p.totalReturn5Y ?? null,
      metricsYearLabel: p.metricsYearLabel || null,
      maxDrawdown: p.maxDrawdown ?? null,
      recent1dReturn: p.recent1dReturn ?? null,
      recent30dReturn: p.recent30dReturn ?? null,
      status: p.status,
    }));

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(strategies, null, 2),
        },
      ],
    };
  }
);

// ── Tool: get_strategy_performance ───────────────────────────

server.tool(
  "get_strategy_performance",
  "Get detailed performance data for a specific QuantToGo macro-factor strategy, including daily NAV (net asset value) history for charting. QuantToGo is a quantitative signal source where every signal is timestamped and immutable from the moment it's published. Use productId from list_strategies.",
  {
    productId: z.string().describe("Strategy product ID, e.g. 'PROD-E3X'"),
    includeChart: z
      .boolean()
      .optional()
      .default(true)
      .describe("Include daily NAV data points for charting"),
  },
  async ({ productId, includeChart }) => {
    const [detailRes, chartRes] = await Promise.all([
      callAPI("getProductDetail", { productId }) as Promise<{
        code: number;
        data: Record<string, unknown>;
      }>,
      includeChart
        ? (callAPI("getProductChart", { productId }) as Promise<{
            code: number;
            data: Record<string, unknown>;
          }>)
        : Promise.resolve(null),
    ]);

    if (detailRes.code !== 0 || !detailRes.data) {
      return {
        content: [
          {
            type: "text" as const,
            text: `Strategy '${productId}' not found`,
          },
        ],
      };
    }

    const d = detailRes.data;
    const result: Record<string, unknown> = {
      productId: d.productId,
      name: d.name,
      market: d.market,
      description: d.description || d.shortDescription,
      totalReturn: d.totalReturn ?? d.totalReturn5Y,
      metricsYearLabel: d.metricsYearLabel,
      maxDrawdown: d.maxDrawdown,
      recent1dReturn: d.recent1dReturn,
      recent30dReturn: d.recent30dReturn,
      tradeCount: d.tradeCount ?? d.tradeCount5Y,
      status: d.status,
    };

    if (chartRes?.data) {
      const cd = chartRes.data;
      result.chart = {
        totalPoints: cd.totalPoints,
        lastUpdated: cd.lastUpdated,
        dataPoints: cd.dataPoints, // [{d, nav}, ...]
      };
    }

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(result, null, 2),
        },
      ],
    };
  }
);

// ── Tool: get_index_data ─────────────────────────────────────

server.tool(
  "get_index_data",
  "Get QuantToGo custom market indices: DA-MOMENTUM (China A-share momentum index based on CSI300/ChiNext) or QTG-MOMENTUM (strategy-weighted momentum index). Part of QuantToGo's macro-factor quantitative signal source. Returns latest value, daily change, and historical data.",
  {
    indexId: z
      .enum(["DA-MOMENTUM", "QTG-MOMENTUM"])
      .optional()
      .describe("Index ID. Omit to get summary of all indices."),
  },
  async ({ indexId }) => {
    if (!indexId) {
      // Summary mode
      const res = (await callAPI("getIndexData", {
        action: "summary",
      })) as { code: number; data: Record<string, unknown>[] };
      if (res.code !== 0) {
        return {
          content: [{ type: "text" as const, text: "Failed to fetch indices" }],
        };
      }
      return {
        content: [
          { type: "text" as const, text: JSON.stringify(res.data, null, 2) },
        ],
      };
    }

    // Detail mode
    const res = (await callAPI("getIndexData", {
      action: "detail",
      indexId,
    })) as { code: number; data: Record<string, unknown> };
    if (res.code !== 0 || !res.data) {
      return {
        content: [
          { type: "text" as const, text: `Index '${indexId}' not found` },
        ],
      };
    }

    return {
      content: [
        { type: "text" as const, text: JSON.stringify(res.data, null, 2) },
      ],
    };
  }
);

// ── Tool: compare_strategies ─────────────────────────────────

server.tool(
  "compare_strategies",
  "Compare multiple QuantToGo macro-factor strategies side-by-side. Returns a comparison table of key metrics (return, drawdown, Sharpe, recent performance). Useful for evaluating which quantitative signal source strategies fit your risk profile.",
  {
    productIds: z
      .array(z.string())
      .min(2)
      .max(8)
      .describe("Array of product IDs to compare, e.g. ['PROD-E3X', 'PROD-PCR']"),
  },
  async ({ productIds }) => {
    const res = (await callAPI("getProducts")) as {
      code: number;
      data: Record<string, unknown>[];
    };
    if (res.code !== 0 || !Array.isArray(res.data)) {
      return {
        content: [{ type: "text" as const, text: "Failed to fetch strategies" }],
      };
    }

    const selected = res.data.filter((p) =>
      productIds.includes(p.productId as string)
    );

    if (selected.length === 0) {
      return {
        content: [
          {
            type: "text" as const,
            text: `None of the specified product IDs were found. Use list_strategies to see available IDs.`,
          },
        ],
      };
    }

    const comparison = selected.map((p) => ({
      productId: p.productId,
      name: p.name,
      market: p.market || "—",
      totalReturn: p.totalReturn ?? p.totalReturn5Y ?? null,
      maxDrawdown: p.maxDrawdown ?? null,
      recent1dReturn: p.recent1dReturn ?? null,
      recent30dReturn: p.recent30dReturn ?? null,
    }));

    return {
      content: [
        { type: "text" as const, text: JSON.stringify(comparison, null, 2) },
      ],
    };
  }
);

// ── Tool: get_subscription_info ──────────────────────────────

server.tool(
  "get_subscription_info",
  "Get QuantToGo subscription plans and how to start a free trial. QuantToGo is a macro-factor quantitative signal source. Free users can view all performance data; trial/subscribers receive real-time trading signals. Use register_trial to start a free 30-day trial instantly.",
  {},
  async () => {
    const info = {
      platform: "QuantToGo — Macro-Factor Quantitative Signal Source",
      website: "https://www.quanttogo.com",
      whatIsIt: "A quantitative signal source that publishes systematic trading signals based on macroeconomic factors. You decide whether to act on them, in your own brokerage account.",
      freeVsPaid: {
        free: [
          "View all strategy performance metrics and NAV history",
          "Access custom market indices (DA-MOMENTUM, QTG-MOMENTUM)",
          "Compare strategies side-by-side",
        ],
        trial: [
          "30-day free access to all trading signals",
          "Real-time buy/sell signals with exact entry/exit points",
          "All 8 strategies across US and China markets",
          "Use register_trial tool with your email to activate instantly",
        ],
        subscriber: [
          "Everything in trial, plus:",
          "Push notifications via WeChat when signals fire",
          "Position sizing and risk management guidance",
          "Historical trade log with full execution details",
        ],
      },
      howToStart: {
        step1: "Call register_trial with your email to get an API key (instant, free)",
        step2: "Call get_signals with your API key + strategy productId to see trading signals",
        step3: "Call check_subscription to check your trial status anytime",
        upgrade: "After trial, email admin@quanttogo.com to subscribe.",
        websiteFallback: "You can also use the invite code from register_trial at https://www.quanttogo.com",
      },
      keyFact: "All performance is forward-tracked from live signals — not backtested. Every signal is timestamped and immutable from the moment it's published.",
      contact: "admin@quanttogo.com",
    };
    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(info, null, 2),
        },
      ],
    };
  }
);

// ── Tool: register_trial ─────────────────────────────────────

server.tool(
  "register_trial",
  "Register for a free 30-day trial of QuantToGo trading signals. Provide your email to get an API key for accessing real-time buy/sell signals across all strategies. Idempotent — calling again with the same email returns the existing account. A confirmation email with your credentials will also be sent.",
  {
    email: z.string().email().describe("Your email address for registration and credential recovery"),
  },
  async ({ email }) => {
    const res = (await callAPI("registerTrial", { email, source: "mcp" })) as {
      code: number;
      message: string;
      data?: {
        apiKey: string;
        inviteCode: string;
        status: string;
        trialEnd: string;
        alreadyRegistered: boolean;
      };
    };

    if (res.code !== 0 || !res.data) {
      return {
        content: [
          {
            type: "text" as const,
            text: res.message || "Registration failed. Please try again or contact admin@quanttogo.com.",
          },
        ],
      };
    }

    const d = res.data;
    const result = {
      apiKey: d.apiKey,
      inviteCode: d.inviteCode,
      status: d.status,
      trialEnd: d.trialEnd,
      alreadyRegistered: d.alreadyRegistered,
      nextSteps: {
        getSignals: `Call get_signals with apiKey="${d.apiKey}" and a productId from list_strategies`,
        checkStatus: `Call check_subscription with apiKey="${d.apiKey}" to check your trial status`,
        webLogin: `Use invite code ${d.inviteCode} at https://www.quanttogo.com`,
      },
      important: "Save your API key — you'll need it for future sessions.",
    };

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(result, null, 2),
        },
      ],
    };
  }
);

// ── Tool: get_signals ────────────────────────────────────────

server.tool(
  "get_signals",
  "Get recent trading signals for a QuantToGo strategy. Requires a valid API key from register_trial. Returns timestamped buy/sell signals with instrument, price, and direction. Trial users have full access to all strategies for 30 days.",
  {
    apiKey: z.string().describe("Your API key from register_trial (starts with 'qtg_')"),
    productId: z.string().describe("Strategy product ID from list_strategies, e.g. 'PROD-E3X'"),
    limit: z
      .number()
      .optional()
      .default(20)
      .describe("Number of recent signals to return (max 50)"),
  },
  async ({ apiKey, productId, limit }) => {
    const res = (await callAPI("getSignalsAPI", { apiKey, productId, limit })) as {
      code: number;
      message: string;
      data?: {
        productId: string;
        productName: string;
        signalCount: number;
        signals: Array<{
          date: string;
          time: string;
          direction: string;
          symbol: string;
          price: number | null;
          source?: string;
        }>;
        subscription: {
          status: string;
          trialEnd: string | null;
          daysRemaining: number | null;
        };
      };
    };

    if (res.code === 401) {
      return {
        content: [
          {
            type: "text" as const,
            text: "Invalid API key. Use register_trial with your email to get a valid key.",
          },
        ],
      };
    }

    if (res.code === 403) {
      return {
        content: [
          {
            type: "text" as const,
            text: "Trial expired. Email admin@quanttogo.com to subscribe for continued signal access.",
          },
        ],
      };
    }

    if (res.code !== 0 || !res.data) {
      return {
        content: [
          {
            type: "text" as const,
            text: res.message || "Failed to fetch signals.",
          },
        ],
      };
    }

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(res.data, null, 2),
        },
      ],
    };
  }
);

// ── Tool: check_subscription ─────────────────────────────────

server.tool(
  "check_subscription",
  "Check your QuantToGo subscription status, remaining trial days, and account details. Requires a valid API key from register_trial.",
  {
    apiKey: z.string().describe("Your API key from register_trial (starts with 'qtg_')"),
  },
  async ({ apiKey }) => {
    const res = (await callAPI("getApiStatus", { apiKey })) as {
      code: number;
      message: string;
      data?: {
        email: string | null;
        status: string;
        inviteCode: string | null;
        trialEnd: string | null;
        daysRemaining: number;
        maxProducts: number;
        registeredAt: string | null;
        message: string;
        upgradeContact?: string;
      };
    };

    if (res.code === 401) {
      return {
        content: [
          {
            type: "text" as const,
            text: "Invalid API key. Use register_trial with your email to get a valid key.",
          },
        ],
      };
    }

    if (res.code !== 0 || !res.data) {
      return {
        content: [
          {
            type: "text" as const,
            text: res.message || "Failed to check subscription.",
          },
        ],
      };
    }

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(res.data, null, 2),
        },
      ],
    };
  }
);

// ── Resource: strategy-overview ──────────────────────────────

  server.resource(
    "strategy-overview",
    "quanttogo://strategies/overview",
    {
      description:
        "Overview of all QuantToGo macro-factor quantitative signal source strategies and their current forward-tracked performance",
      mimeType: "application/json",
    },
    async () => {
      const res = (await callAPI("getProducts")) as {
        code: number;
        data: Record<string, unknown>[];
      };
      const data = res.code === 0 && Array.isArray(res.data) ? res.data : [];
      return {
        contents: [
          {
            uri: "quanttogo://strategies/overview",
            mimeType: "application/json",
            text: JSON.stringify(data, null, 2),
          },
        ],
      };
    }
  );
} // end registerTools

// ── Start ────────────────────────────────────────────────────

async function main() {
  const server = createServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
