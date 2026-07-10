import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { assertManifestMatches, loadAndValidateSnapshot } from "./report-data.mjs";

const root = resolve(import.meta.dirname, "..");
const repoRoot = resolve(root, "..", "..");
const dist = resolve(root, "dist");
const outFile = resolve(root, "lean_easy_failure_report_standalone.html");
const snapshot = loadAndValidateSnapshot({ reportRoot: root, repoRoot });
assertManifestMatches(root, snapshot.manifest);

const html = readFileSync(resolve(dist, "index.html"), "utf8");
const cssMatch = html.match(/<link rel="stylesheet" crossorigin href="([^"]+)">/);
const jsMatch = html.match(/<script type="module" crossorigin src="([^"]+)"><\/script>/);

if (!cssMatch || !jsMatch) {
  throw new Error("Could not find Vite CSS/JS assets in dist/index.html");
}

const css = readFileSync(resolve(dist, cssMatch[1].replace(/^\//, "")), "utf8");
const js = readFileSync(resolve(dist, jsMatch[1].replace(/^\//, "")), "utf8");
const csv = snapshot.csvText;
const traces = snapshot.tracesText;
const manifest = JSON.stringify(snapshot.manifest, null, 2);

const escapedCsv = csv.replaceAll("</script", "<\\/script");
const escapedTraces = traces.replaceAll("</script", "<\\/script");
const escapedManifest = manifest.replaceAll("</script", "<\\/script");

const standalone = html
  // Callback replacements keep dollar-sign sequences in proof text literal.
  // String-form replacement can interpret them as substitution tokens and
  // splice the surrounding HTML into the embedded JSON.
  .replace(cssMatch[0], () => `<style>\n${css}\n</style>`)
  .replace(
    jsMatch[0],
    () =>
      `<script type="text/plain" id="embedded-csv">${escapedCsv}</script>\n<script type="application/json" id="embedded-traces">${escapedTraces}</script>\n<script type="application/json" id="embedded-snapshot">${escapedManifest}</script>\n<script type="module">\n${js}\n</script>`,
  );

const embeddedMatch = standalone.match(
  /<script type="application\/json" id="embedded-traces">([\s\S]*?)<\/script>/,
);
if (!embeddedMatch) {
  throw new Error("Standalone output is missing embedded trace JSON");
}
const embedded = JSON.parse(embeddedMatch[1]);
if (!Array.isArray(embedded) || embedded.length !== snapshot.manifest.trial_count) {
  throw new Error(
    `Standalone trace count mismatch: expected ${snapshot.manifest.trial_count}, found ${embedded.length}`,
  );
}

writeFileSync(outFile, standalone, "utf8");
console.log(
  `wrote ${outFile} with ${snapshot.manifest.trial_count} traces (snapshot ${snapshot.manifest.snapshot_sha256})`,
);
