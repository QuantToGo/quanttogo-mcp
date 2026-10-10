#!/usr/bin/env node
/**
 * 风控单 QuantToGo — MCP (stdio bridge)
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
const VERSION = "1.0.0";

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
        "风控单 QuantToGo：替用户盯着她手上的 A 股持仓。先用 risk_check 看读数，再用 verify_reasons 核对理由，理由成立才用 create_risk_order 建单。标的写「名字（代码）」；数字一律带数据日期。",
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
