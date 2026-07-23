import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { build as viteBuild } from "vite";

import { buildMeetingExperimentBundle } from "./meeting/experiment-data.mjs";
import { renderMeetingMarkdown } from "./meeting/render-markdown.mjs";

const modulePath = fileURLToPath(import.meta.url);
const defaultReportRoot = resolve(import.meta.dirname, "..");
const defaultRepoRoot = resolve(defaultReportRoot, "..", "..");

const OUTPUTS = Object.freeze({
  html: "lean_failure_modes_meeting.html",
  markdown: "lean_failure_modes_meeting.md",
});

function viteOutputItems(result) {
  const outputs = Array.isArray(result) ? result : [result];
  return outputs.flatMap((output) => {
    if (!output || !("output" in output) || !Array.isArray(output.output)) {
      throw new Error("Vite did not return an in-memory Rollup output");
    }
    return output.output;
  });
}

function sourceText(asset) {
  if (typeof asset.source === "string") return asset.source;
  if (asset.source instanceof Uint8Array) {
    return new TextDecoder().decode(asset.source);
  }
  throw new Error(`Unsupported Vite asset source for ${asset.fileName}`);
}

function escapeEmbeddedJson(value) {
  return JSON.stringify(value).replaceAll("</script", "<\\/script");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function assignmentId(trial, field) {
  return trial.classifications?.[field]?.categoryId ?? null;
}

function taxonomy(bundle, axisId) {
  return bundle.taxonomies.find((axis) => axis.axisId === axisId)?.categories ?? [];
}

function renderSemanticFallback(bundle) {
  const easyFailures = bundle.trials.filter((trial) => assignmentId(trial, "failureMode"));
  const medium = bundle.trials.filter((trial) => assignmentId(trial, "failureBehavior"));
  const recoveries = bundle.indexes?.recoverySuccesses ?? [];
  const easyRows = taxonomy(bundle, "easy-failure-mode")
    .map((mode) => {
      const count = easyFailures.filter(
        (trial) => assignmentId(trial, "failureMode") === mode.categoryId,
      ).length;
      return `<tr><th scope="row">${escapeHtml(mode.label)}</th><td>${count}</td></tr>`;
    })
    .join("");
  const stages = taxonomy(bundle, "medium-progress-stage");
  const mediumRows = taxonomy(bundle, "medium-failure-behavior")
    .map((behavior) => {
      const cells = stages
        .map((stage) =>
          medium.filter(
            (trial) =>
              assignmentId(trial, "failureBehavior") === behavior.categoryId &&
              assignmentId(trial, "progressStage") === stage.categoryId,
          ).length,
        )
        .map((count) => `<td>${count}</td>`)
        .join("");
      return `<tr><th scope="row">${escapeHtml(behavior.label)}</th>${cells}</tr>`;
    })
    .join("");

  return `<noscript>
    <main class="noscript-message">
      <h1>Lean failure and recovery traces</h1>
      <p><strong>${bundle.scope.trialCount} complete traces</strong> · ${bundle.scope.eventCount.toLocaleString("en-US")} events · ${bundle.scope.causalEdgeCount.toLocaleString("en-US")} causal edges.</p>
      <p>Interactive trace, graph, checks, JSONL, and subgoal synchronization needs JavaScript. This source-backed summary remains available for printing and no-script readers.</p>
      <h2>Easy failure modes</h2>
      <table><thead><tr><th>Reviewed mode</th><th>Trials</th></tr></thead><tbody>${easyRows}</tbody></table>
      <h2>Recovery after compiler failure</h2>
      <p>${recoveries.length} kernel-confirmed exact-target runs contain a failed compiler result before terminal acceptance.</p>
      <p>${recoveries.map((entry) => `<code>${escapeHtml(entry.trialId)}</code>`).join(" · ")}</p>
      <h2>Medium behavior × controller progress</h2>
      <p>Ledger acceptance is workflow state, not proof completion.</p>
      <div class="table-scroll"><table><thead><tr><th>Observed behavior</th>${stages.map((stage) => `<th>${escapeHtml(stage.label.match(/P[0-5]/)?.[0] ?? stage.label)}</th>`).join("")}</tr></thead><tbody>${mediumRows}</tbody></table></div>
      <p>See <code>lean_failure_modes_meeting.md</code> for the complete static report.</p>
    </main>
  </noscript>`;
}

function inlineViteOutput(items, bundle) {
  const htmlAsset = items.find(
    (item) => item.type === "asset" && item.fileName.endsWith(".html"),
  );
  const entryChunks = items.filter(
    (item) => item.type === "chunk" && item.isEntry,
  );
  const cssAssets = items.filter(
    (item) => item.type === "asset" && item.fileName.endsWith(".css"),
  );

  if (!htmlAsset || entryChunks.length !== 1) {
    throw new Error(
      `Expected one meeting HTML asset and one entry chunk; found ${htmlAsset ? 1 : 0} HTML and ${entryChunks.length} entries`,
    );
  }

  const css = cssAssets.map(sourceText).join("\n");
  if (/<\/style/i.test(css)) {
    throw new Error("Compiled CSS contains a closing style tag and cannot be safely inlined");
  }

  let html = sourceText(htmlAsset);
  html = html.replace(
    /^[ \t]*<link\b[^>]*\brel=["']stylesheet["'][^>]*>[ \t]*\r?\n/gim,
    "",
  );
  html = html.replace(
    /^[ \t]*<script\b[^>]*\btype=["']module["'][^>]*\bsrc=["'][^"']+["'][^>]*><\/script>[ \t]*\r?\n/gim,
    "",
  );

  const dataTag = `<script id="meeting-data" type="application/json">${escapeEmbeddedJson(bundle)}</script>`;
  if (/<script\b[^>]*\bid=["']meeting-data["'][^>]*>[\s\S]*?<\/script>/i.test(html)) {
    html = html.replace(
      /<script\b[^>]*\bid=["']meeting-data["'][^>]*>[\s\S]*?<\/script>/i,
      () => dataTag,
    );
  } else {
    html = html.replace("</body>", `${dataTag}\n</body>`);
  }

  if (/<noscript\b[^>]*>[\s\S]*?<\/noscript>/i.test(html)) {
    html = html.replace(/<noscript\b[^>]*>[\s\S]*?<\/noscript>/i, () =>
      renderSemanticFallback(bundle),
    );
  }

  if (css) {
    html = html.replace("</head>", `<style data-meeting-inline>\n${css}\n</style>\n</head>`);
  }

  const javascript = entryChunks[0].code.replaceAll("</script", "<\\/script");
  html = html.replace(
    "</body>",
    `<script type="module" data-meeting-inline>\n${javascript}\n</script>\n</body>`,
  );

  return `${html.trim()}\n`;
}

function assertPortableHtml(html) {
  const activeExternalAsset = /<(?:script|img|iframe)\b[^>]*\bsrc=["'](?:https?:)?\/\//i;
  const externalStylesheet = /<link\b[^>]*\bhref=["'](?:https?:)?\/\//i;
  const externalCss = /(?:@import\s+|url\(\s*["']?)(?:https?:)?\/\//i;
  const privateAbsolutePath = /(?:\b[A-Za-z]:[\\/]|file:\/\/\/|\\\\wsl\.localhost\\)/i;
  const temporaryLeanPath = /(?:\.traj_eval_tmp|\bcheck_[0-9a-f]{8,}\.lean\b|<lean-temp>\.lean)/i;

  if (activeExternalAsset.test(html) || externalStylesheet.test(html) || externalCss.test(html)) {
    throw new Error("Meeting HTML contains an external asset or network request");
  }
  if (privateAbsolutePath.test(html)) {
    throw new Error("Meeting HTML contains a private absolute path");
  }
  if (temporaryLeanPath.test(html)) {
    throw new Error("Meeting HTML contains a raw temporary Lean filename");
  }
  if (!html.includes('id="meeting-data"') || !html.includes("<noscript")) {
    throw new Error("Meeting HTML is missing embedded data or its semantic no-script fallback");
  }
}

export function extractEmbeddedBundle(html) {
  const match = html.match(
    /<script\b[^>]*\bid=["']meeting-data["'][^>]*>([\s\S]*?)<\/script>/i,
  );
  if (!match) throw new Error("Meeting HTML does not contain #meeting-data");
  return JSON.parse(match[1]);
}

export async function createMeetingArtifacts({
  reportRoot = defaultReportRoot,
  repoRoot = defaultRepoRoot,
} = {}) {
  const bundle = await buildMeetingExperimentBundle({ reportRoot, repoRoot });
  const result = await viteBuild({
    root: reportRoot,
    configFile: false,
    base: "./",
    logLevel: "silent",
    appType: "mpa",
    build: {
      write: false,
      emptyOutDir: false,
      cssCodeSplit: false,
      minify: true,
      sourcemap: false,
      rollupOptions: {
        input: resolve(reportRoot, "meeting.html"),
      },
    },
  });

  const html = inlineViteOutput(viteOutputItems(result), bundle);
  const markdown = `${renderMeetingMarkdown(bundle).trim()}\n`;
  assertPortableHtml(html);

  const embedded = extractEmbeddedBundle(html);
  if (
    embedded.scope?.trialCount !== bundle.scope?.trialCount ||
    embedded.scope?.eventCount !== bundle.scope?.eventCount ||
    embedded.scope?.causalEdgeCount !== bundle.scope?.causalEdgeCount
  ) {
    throw new Error("Embedded bundle totals differ from the validated source bundle");
  }

  return {
    bundle,
    html,
    markdown,
    summary: {
      traces: bundle.scope.trialCount,
      events: bundle.scope.eventCount,
      causalEdges: bundle.scope.causalEdgeCount,
    },
  };
}

async function readExisting(path) {
  try {
    return await readFile(path, "utf8");
  } catch (error) {
    if (error && error.code === "ENOENT") return null;
    throw error;
  }
}

export async function writeMeetingArtifacts(artifacts, { reportRoot = defaultReportRoot } = {}) {
  await writeFile(resolve(reportRoot, OUTPUTS.html), artifacts.html, "utf8");
  await writeFile(resolve(reportRoot, OUTPUTS.markdown), artifacts.markdown, "utf8");
}

export async function checkMeetingArtifacts(artifacts, { reportRoot = defaultReportRoot } = {}) {
  const expected = [
    [OUTPUTS.html, artifacts.html],
    [OUTPUTS.markdown, artifacts.markdown],
  ];
  const stale = [];
  for (const [name, content] of expected) {
    if ((await readExisting(resolve(reportRoot, name))) !== content) stale.push(name);
  }
  if (stale.length) {
    throw new Error(`Meeting artifacts are stale: ${stale.join(", ")}. Run npm run build:meeting.`);
  }
}

async function main() {
  const checkOnly = process.argv.slice(2).includes("--check");
  const artifacts = await createMeetingArtifacts();
  if (checkOnly) {
    await checkMeetingArtifacts(artifacts);
  } else {
    await writeMeetingArtifacts(artifacts);
  }
  const action = checkOnly ? "verified" : "wrote";
  console.log(
    `${action} ${OUTPUTS.html} and ${OUTPUTS.markdown}: ${artifacts.summary.traces} traces, ${artifacts.summary.events} events, ${artifacts.summary.causalEdges} causal edges`,
  );
}

if (process.argv[1] && resolve(process.argv[1]) === resolve(modulePath)) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  });
}
