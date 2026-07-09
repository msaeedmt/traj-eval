import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const dist = resolve(root, "dist");
const publicData = resolve(root, "public", "data", "lean_easy_failure_patterns.csv");
const publicTraces = resolve(root, "public", "data", "lean_easy_failure_traces.json");
const outFile = resolve(root, "lean_easy_failure_report_standalone.html");

const html = readFileSync(resolve(dist, "index.html"), "utf8");
const cssMatch = html.match(/<link rel="stylesheet" crossorigin href="([^"]+)">/);
const jsMatch = html.match(/<script type="module" crossorigin src="([^"]+)"><\/script>/);

if (!cssMatch || !jsMatch) {
  throw new Error("Could not find Vite CSS/JS assets in dist/index.html");
}

const css = readFileSync(resolve(dist, cssMatch[1].replace(/^\//, "")), "utf8");
const js = readFileSync(resolve(dist, jsMatch[1].replace(/^\//, "")), "utf8");
const csv = readFileSync(publicData, "utf8");
const traces = readFileSync(publicTraces, "utf8");

const escapedCsv = csv.replaceAll("</script", "<\\/script");
const escapedTraces = traces.replaceAll("</script", "<\\/script");

const standalone = html
  .replace(cssMatch[0], `<style>\n${css}\n</style>`)
  .replace(
    jsMatch[0],
    `<script type="text/plain" id="embedded-csv">${escapedCsv}</script>\n<script type="application/json" id="embedded-traces">${escapedTraces}</script>\n<script type="module">\n${js}\n</script>`,
  );

writeFileSync(outFile, standalone, "utf8");
console.log(`wrote ${outFile}`);
