#!/usr/bin/env node
/**
 * QuantToGo 理由指数 (Reason Index) — MCP (stdio bridge)
 *
 * This package is a thin stdio bridge to the hosted server at
 * https://mcp.quanttogo.com/v2 (Streamable HTTP). Every tool call is
 * forwarded as-is; the tool list is fetched from the server on start, so
 * updating the hosted server updates this package's tools without a release.
 *
 * Remote URL can be overridden with QUANTTOGO_MCP_URL.
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const REMOTE = process.env.QUANTTOGO_MCP_URL || "https://mcp.quanttogo.com/v2";
const VERSION = "1.1.0";

async function connectRemote(): Promise<Client> {
  const client = new Client({ name: "quanttogo-mcp-bridge", version: VERSION });
  const transport = new StreamableHTTPClientTransport(new URL(REMOTE));
  await client.connect(transport);
  return client;
}

async function main(): Promise<void> {
  let remote: Client | null = null;
  const getRemote = async (): Promise<Client> => {
    if (remote) return remote;
    remote = await connectRemote();
    return remote;
  };

  const server = new Server(
    { name: "quanttogo-mcp", version: VERSION },
    {
      capabilities: { tools: {} },
      instructions:
        "QuantToGo 理由指数：把买卖股票的理由做成指数——腰斩指数、放量新高指数、国家队增持指数……每条理由今天有多少只股票符合、比昨天多了还是少了、2015 年以来走了多少，A 股和美股分开算。另有 QTG 风险指数，把 31 个行业的过热程度合成一个数。问某个理由指数用 reason_index，问成分股用 reason_index_stocks，问一只股票符合哪些理由用 stock_reasons，问风险用 qtg_risk_index。提到理由指数用短名，第一次提到时后面带理由原话；标的写「名字（代码）」；数字一律带数据日期。网址 https://quanttogo.com",
    }
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => {
    const r = await getRemote();
    const res = await r.listTools();
    return { tools: res.tools };
  });

  server.setRequestHandler(CallToolRequestSchema, async (req) => {
    try {
      const r = await getRemote();
      const res = await r.callTool({
        name: req.params.name,
        arguments: (req.params.arguments || {}) as Record<string, unknown>,
      });
      return res as { content: Array<{ type: string; text?: string }>; isError?: boolean };
    } catch (e) {
      remote = null; // reconnect next time
      const msg = e instanceof Error ? e.message : String(e);
      return { content: [{ type: "text", text: `远程服务暂时没回应：${msg}` }], isError: true };
    }
  });

  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((e) => {
  console.error("quanttogo-mcp failed:", e);
  process.exit(1);
});
