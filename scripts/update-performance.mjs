#!/usr/bin/env node
/**
 * Fetches live strategy performance from QuantToGo API
 * and updates the performance table in README.md.
 *
 * Run manually: node scripts/update-performance.mjs
 * Or via GitHub Actions (weekly schedule).
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const API_URL = "https://www.quanttogo.com/getProducts";
const README_PATH = path.join(__dirname, "..", "README.md");

const FACTOR_MAP = {
  "PROD-CHAU": "FX: CNH-CSI300 correlation",
  "PROD-CNY-IF": "FX: CNY-index correlation",
  "PROD-COLD-STOCK": "Attention: low-volume value",
  "PROD-DIP-A": "Sentiment: limit-down rebound",
  "PROD-DIP-US": "Sentiment: VIX panic reversal",
  "PROD-E3X": "Trend: TQQQ timing",
  "PROD-IF-IC": "Liquidity: large/small cap rotation",
  "PROD-PCR": "Sentiment: Put/Call Ratio",
};

const MARKET_MAP = {
  美股: "US",
  A股: "A-Share",
};

async function fetchStrategies() {
  const resp = await fetch(API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!resp.ok) throw new Error(`API returned ${resp.status}`);
  const json = await resp.json();
  if (json.code !== 0 || !Array.isArray(json.data)) {
    throw new Error("Invalid API response");
  }
  return json.data;
}

function buildTable(strategies) {
  // Sort by total return descending
  const sorted = [...strategies].sort(
    (a, b) => (b.totalReturn5Y || 0) - (a.totalReturn5Y || 0)
  );

  const header = `| Strategy | Market | Factor | Total Return | Max Drawdown | Sharpe | Frequency |`;
  const separator = `|----------|--------|--------|-------------|-------------|--------|-----------|`;

  const rows = sorted.map((s) => {
    const market = MARKET_MAP[s.market] || s.market || "—";
    const factor = FACTOR_MAP[s.productId] || "—";
    const ret = s.totalReturn5Y != null ? `+${s.totalReturn5Y.toFixed(1)}%` : "—";
    const dd = s.maxDrawdown != null ? `-${s.maxDrawdown.toFixed(1)}%` : "—";
    const sharpe = s.sharpeRatio || "—";
    const freq = (s.frequency || "—").charAt(0).toUpperCase() + (s.frequency || "—").slice(1);
    return `| ${s.name} | ${market} | ${factor} | ${ret} | ${dd} | ${sharpe} | ${freq} |`;
  });

  const today = new Date().toISOString().split("T")[0];
  const footer = `\n> **Last updated: ${today}** · Auto-updated weekly via GitHub Actions · [Verify in git history](../../commits/main/README.md)`;

  return [header, separator, ...rows].join("\n") + footer;
}

async function main() {
  console.log("Fetching strategy data from QuantToGo API...");
  const strategies = await fetchStrategies();
  console.log(`Got ${strategies.length} strategies.`);

  const table = buildTable(strategies);

  console.log("Reading README.md...");
  let readme = fs.readFileSync(README_PATH, "utf-8");

  const startMarker = "<!-- PERFORMANCE_TABLE_START -->";
  const endMarker = "<!-- PERFORMANCE_TABLE_END -->";

  const startIdx = readme.indexOf(startMarker);
  const endIdx = readme.indexOf(endMarker);

  if (startIdx === -1 || endIdx === -1) {
    console.error("ERROR: Could not find performance table markers in README.md");
    process.exit(1);
  }

  const before = readme.slice(0, startIdx + startMarker.length);
  const after = readme.slice(endIdx);

  readme = before + "\n" + table + "\n" + after;

  fs.writeFileSync(README_PATH, readme, "utf-8");
  console.log("README.md updated successfully.");
  console.log("\nPerformance table:");
  console.log(table);
}

main().catch((err) => {
  console.error("Failed:", err.message);
  process.exit(1);
});
