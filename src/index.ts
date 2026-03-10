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

// ── Server ───────────────────────────────────────────────────

const server = new McpServer({
  name: "quanttogo-mcp",
  version: "0.1.1",
});

// ── Tool: list_strategies ────────────────────────────────────

server.tool(
  "list_strategies",
  "List all quantitative trading strategies on QuantToGo with live-tracked performance metrics. Returns strategy name, market (US/China), total return, max drawdown, and recent returns.",
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
  "Get detailed performance data for a specific QuantToGo strategy, including daily NAV history (net asset value) for charting. Use productId from list_strategies.",
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
  "Get QuantToGo custom market indices: DA-MOMENTUM (China A-share momentum index based on CSI300/ChiNext) or QTG-MOMENTUM (QuantToGo strategy-weighted momentum index). Returns latest value, daily change, and historical data.",
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
  "Compare multiple QuantToGo strategies side-by-side. Returns a comparison table of key metrics (return, drawdown, recent performance) for the specified strategy IDs.",
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

// ── Resource: strategy-overview ──────────────────────────────

server.resource(
  "strategy-overview",
  "quanttogo://strategies/overview",
  {
    description:
      "Overview of all QuantToGo quantitative trading strategies and their current performance",
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

// ── Start ────────────────────────────────────────────────────

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
