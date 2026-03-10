#!/usr/bin/env node
/**
 * QuantToGo MCP Server - SSE Transport (for Coze integration)
 *
 * This is a standalone SSE server that wraps the same QuantToGo API
 * used by the stdio MCP server. It does NOT modify the original code.
 *
 * Usage:
 *   cd coze-sse && npm install && node server.js
 *   Server starts at http://localhost:3100/sse
 *
 * For public access, use cloudflare tunnel or ngrok:
 *   npx cloudflared tunnel --url http://localhost:3100
 */

const express = require("express");
const { McpServer } = require("@modelcontextprotocol/sdk/server/mcp.js");
const { SSEServerTransport } = require("@modelcontextprotocol/sdk/server/sse.js");
const { z } = require("zod");

const API_BASE = "https://www.quanttogo.com";
const PORT = process.env.PORT || 3100;

// ── Helpers ──────────────────────────────────────────────────

async function callAPI(fn, body = {}) {
  const resp = await fetch(`${API_BASE}/${fn}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`API ${fn} returned ${resp.status}`);
  return resp.json();
}

// ── Server Factory ──────────────────────────────────────────

function createServer() {
  const server = new McpServer({
    name: "quanttogo-mcp",
    version: "0.1.2",
  });

  // ── Tool: list_strategies ──
  server.tool(
    "list_strategies",
    "List all quantitative trading strategies on QuantToGo with live performance metrics.",
    {},
    async () => {
      const res = await callAPI("getProducts");
      if (res.code !== 0 || !Array.isArray(res.data)) {
        return { content: [{ type: "text", text: "Failed to fetch strategies" }] };
      }
      const strategies = res.data.map((p) => ({
        productId: p.productId,
        name: p.name,
        market: p.market || "—",
        totalReturn: p.totalReturn ?? p.totalReturn5Y ?? null,
        maxDrawdown: p.maxDrawdown ?? null,
        recent1dReturn: p.recent1dReturn ?? null,
        recent30dReturn: p.recent30dReturn ?? null,
        status: p.status,
      }));
      return { content: [{ type: "text", text: JSON.stringify(strategies, null, 2) }] };
    }
  );

  // ── Tool: get_strategy_performance ──
  server.tool(
    "get_strategy_performance",
    "Get detailed performance data for a specific strategy, including daily NAV history.",
    {
      productId: z.string().describe("Strategy product ID, e.g. 'PROD-E3X'"),
      includeChart: z.boolean().optional().default(true).describe("Include daily NAV data points"),
    },
    async ({ productId, includeChart }) => {
      const [detailRes, chartRes] = await Promise.all([
        callAPI("getProductDetail", { productId }),
        includeChart ? callAPI("getProductChart", { productId }) : Promise.resolve(null),
      ]);
      if (detailRes.code !== 0 || !detailRes.data) {
        return { content: [{ type: "text", text: `Strategy '${productId}' not found` }] };
      }
      const d = detailRes.data;
      const result = {
        productId: d.productId, name: d.name, market: d.market,
        description: d.description || d.shortDescription,
        totalReturn: d.totalReturn ?? d.totalReturn5Y,
        maxDrawdown: d.maxDrawdown,
        recent1dReturn: d.recent1dReturn, recent30dReturn: d.recent30dReturn,
        tradeCount: d.tradeCount ?? d.tradeCount5Y, status: d.status,
      };
      if (chartRes?.data) {
        result.chart = {
          totalPoints: chartRes.data.totalPoints,
          lastUpdated: chartRes.data.lastUpdated,
          dataPoints: chartRes.data.dataPoints,
        };
      }
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    }
  );

  // ── Tool: get_index_data ──
  server.tool(
    "get_index_data",
    "Get QuantToGo custom market indices: DA-MOMENTUM or QTG-MOMENTUM.",
    {
      indexId: z.enum(["DA-MOMENTUM", "QTG-MOMENTUM"]).optional()
        .describe("Index ID. Omit to get summary of all indices."),
    },
    async ({ indexId }) => {
      if (!indexId) {
        const res = await callAPI("getIndexData", { action: "summary" });
        if (res.code !== 0) return { content: [{ type: "text", text: "Failed to fetch indices" }] };
        return { content: [{ type: "text", text: JSON.stringify(res.data, null, 2) }] };
      }
      const res = await callAPI("getIndexData", { action: "detail", indexId });
      if (res.code !== 0 || !res.data) return { content: [{ type: "text", text: `Index '${indexId}' not found` }] };
      return { content: [{ type: "text", text: JSON.stringify(res.data, null, 2) }] };
    }
  );

  // ── Tool: compare_strategies ──
  server.tool(
    "compare_strategies",
    "Compare multiple strategies side-by-side with key metrics.",
    {
      productIds: z.array(z.string()).min(2).max(8)
        .describe("Array of product IDs to compare"),
    },
    async ({ productIds }) => {
      const res = await callAPI("getProducts");
      if (res.code !== 0 || !Array.isArray(res.data)) {
        return { content: [{ type: "text", text: "Failed to fetch strategies" }] };
      }
      const selected = res.data.filter((p) => productIds.includes(p.productId));
      if (selected.length === 0) {
        return { content: [{ type: "text", text: "None of the specified IDs found. Use list_strategies first." }] };
      }
      const comparison = selected.map((p) => ({
        productId: p.productId, name: p.name, market: p.market || "—",
        totalReturn: p.totalReturn ?? p.totalReturn5Y ?? null,
        maxDrawdown: p.maxDrawdown ?? null,
        recent1dReturn: p.recent1dReturn ?? null,
        recent30dReturn: p.recent30dReturn ?? null,
      }));
      return { content: [{ type: "text", text: JSON.stringify(comparison, null, 2) }] };
    }
  );

  // ── Resource: strategy-overview ──
  server.resource(
    "strategy-overview",
    "quanttogo://strategies/overview",
    { description: "Overview of all QuantToGo strategies", mimeType: "application/json" },
    async () => {
      const res = await callAPI("getProducts");
      const data = res.code === 0 && Array.isArray(res.data) ? res.data : [];
      return {
        contents: [{ uri: "quanttogo://strategies/overview", mimeType: "application/json", text: JSON.stringify(data, null, 2) }],
      };
    }
  );

  return server;
}

// ── Express + SSE ────────────────────────────────────────────

const app = express();
const transports = {};

app.get("/sse", async (req, res) => {
  console.log("[SSE] New connection from", req.ip);
  const transport = new SSEServerTransport("/message", res);
  transports[transport.sessionId] = transport;

  const server = createServer();

  res.on("close", () => {
    console.log("[SSE] Connection closed:", transport.sessionId);
    delete transports[transport.sessionId];
  });

  await server.connect(transport);
});

app.post("/message", express.json(), async (req, res) => {
  const sessionId = req.query.sessionId;
  const transport = transports[sessionId];
  if (!transport) {
    res.status(400).json({ error: "Unknown session" });
    return;
  }
  await transport.handlePostMessage(req, res);
});

// Health check
app.get("/health", (req, res) => {
  res.json({ status: "ok", server: "quanttogo-mcp", transport: "sse" });
});

app.listen(PORT, () => {
  console.log(`QuantToGo MCP SSE Server running on http://localhost:${PORT}/sse`);
  console.log(`Health check: http://localhost:${PORT}/health`);
});
