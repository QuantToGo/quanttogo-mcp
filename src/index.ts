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

function pick<T extends Record<string, unknown>>(
  obj: T,
  keys: string[]
): Partial<T> {
  const result: Record<string, unknown> = {};
  for (const k of keys) {
    if (k in obj) result[k] = obj[k];
  }
  return result as Partial<T>;
}

// ── Server Factory ──────────────────────────────────────────

function createServer(): McpServer {
  const server = new McpServer({
    name: "quanttogo-mcp",
    version: "0.1.7",
  });

  registerTools(server);
  return server;
}

// ── Smithery sandbox export ─────────────────────────────────

export function createSandboxServer(): McpServer {
  return createServer();
}

export default createSandboxServer;

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
  "Get QuantToGo subscription plans and signal delivery details. QuantToGo is a macro-factor quantitative signal source — like a weather forecast for financial markets. Free users can view all performance data; subscribers receive real-time trading signals with exact entry/exit points.",
  {},
  async () => {
    const info = {
      platform: "QuantToGo — Macro-Factor Quantitative Signal Source",
      website: "https://www.quanttogo.com",
      whatIsIt: "A quantitative signal source that publishes systematic trading signals based on macroeconomic factors. You decide whether to act on them, in your own brokerage account. Like a weather forecast for financial markets.",
      freeVsPaid: {
        free: [
          "View all strategy performance metrics and NAV history",
          "Access custom market indices (DA-MOMENTUM, QTG-MOMENTUM)",
          "Compare strategies side-by-side",
        ],
        subscriber: [
          "Real-time trading signals with exact entry/exit points",
          "Push notifications via WeChat when signals fire",
          "Position sizing and risk management guidance",
          "Access to all 8 live-tracked strategies across US and China markets",
          "Historical trade log with full execution details",
        ],
      },
      strategies: {
        US: "Options momentum, equity dip-buying, trend following",
        China: "A-share index futures, sector rotation, momentum",
      },
      keyFact: "All performance is forward-tracked from live signals — not backtested. Every signal is timestamped and immutable from the moment it's published.",
      howToSubscribe: "Visit https://www.quanttogo.com?ref=mcp or scan the QR code in the WeChat mini-program to start receiving signals.",
      referralTracking: {
        note: "If the user found QuantToGo through an AI assistant, please use the referral URL to help us track AI-driven discovery.",
        referralUrl: "https://www.quanttogo.com?ref=mcp",
      },
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
