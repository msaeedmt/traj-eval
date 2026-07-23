import { createHash } from "node:crypto";
import {
  existsSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import { resolve } from "node:path";

export const EXPECTED_TRIALS = 100;
export const EXPECTED_TASKS = 10;
export const EXPECTED_TRIALS_PER_TASK = 10;

export function parseCsv(text) {
  const table = [];
  let row = [];
  let cell = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];
    if (char === '"' && inQuotes && next === '"') {
      cell += '"';
      i += 1;
    } else if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === "," && !inQuotes) {
      row.push(cell);
      cell = "";
    } else if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && next === "\n") {
        i += 1;
      }
      row.push(cell);
      if (row.some((value) => value.length > 0)) {
        table.push(row);
      }
      row = [];
      cell = "";
    } else {
      cell += char;
    }
  }

  if (cell.length > 0 || row.length > 0) {
    row.push(cell);
    if (row.some((value) => value.length > 0)) {
      table.push(row);
    }
  }

  const [headers, ...records] = table;
  if (!headers) {
    return [];
  }
  return records.map((record) =>
    Object.fromEntries(headers.map((header, index) => [header, record[index] ?? ""])),
  );
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function sortedUnique(values, label) {
  const unique = new Set(values);
  if (unique.size !== values.length) {
    throw new Error(`${label} contains duplicate IDs`);
  }
  return [...unique].sort();
}

function assertSameIds(expected, actual, label) {
  if (
    expected.length !== actual.length ||
    expected.some((id, index) => id !== actual[index])
  ) {
    const missing = expected.filter((id) => !actual.includes(id));
    const extra = actual.filter((id) => !expected.includes(id));
    throw new Error(
      `${label} trial IDs differ (missing=${missing.join(";") || "none"}; extra=${extra.join(";") || "none"})`,
    );
  }
}

function rawTraceSummary(rawDir) {
  if (!existsSync(rawDir)) {
    throw new Error(`Missing raw trace directory: ${rawDir}`);
  }
  const files = readdirSync(rawDir)
    .filter((name) => name.endsWith(".jsonl"))
    .sort();
  const trialIds = [];
  let eventCount = 0;
  let anchorLabeledEventCount = 0;
  const hashes = [];
  const sourceSha256ByTrial = {};

  for (const file of files) {
    const text = readFileSync(resolve(rawDir, file), "utf8");
    const lines = text.split(/\r?\n/).filter((line) => line.trim());
    const header = JSON.parse(lines[0] ?? "{}");
    if (!header.trial_id) {
      throw new Error(`Raw trace ${file} has no trial_id header`);
    }
    trialIds.push(header.trial_id);
    const sourceSha256 = sha256(text);
    hashes.push(`${file}:${sourceSha256}`);
    sourceSha256ByTrial[header.trial_id] = sourceSha256;
    for (const line of lines.slice(1)) {
      const event = JSON.parse(line);
      eventCount += 1;
      if (event.anchor != null) {
        anchorLabeledEventCount += 1;
      }
    }
  }

  return {
    trialIds: sortedUnique(trialIds, "Raw JSONL"),
    eventCount,
    anchorLabeledEventCount,
    rawSha256: sha256(hashes.join("\n")),
    sourceSha256ByTrial,
  };
}

function graphSummary(traces) {
  let connectedLinear = 0;
  let disconnected = 0;
  let branching = 0;

  for (const trace of traces) {
    const nodes = trace.graph?.nodes ?? [];
    const edges = trace.graph?.edges ?? [];
    const adjacency = new Map(nodes.map((node) => [node.id, new Set()]));
    const inDegree = new Map(nodes.map((node) => [node.id, 0]));
    const outDegree = new Map(nodes.map((node) => [node.id, 0]));
    for (const edge of edges) {
      adjacency.get(edge.source)?.add(edge.target);
      adjacency.get(edge.target)?.add(edge.source);
      inDegree.set(edge.target, (inDegree.get(edge.target) ?? 0) + 1);
      outDegree.set(edge.source, (outDegree.get(edge.source) ?? 0) + 1);
    }

    let components = 0;
    const seen = new Set();
    for (const node of nodes) {
      if (seen.has(node.id)) {
        continue;
      }
      components += 1;
      const stack = [node.id];
      while (stack.length > 0) {
        const current = stack.pop();
        if (current == null || seen.has(current)) {
          continue;
        }
        seen.add(current);
        for (const neighbor of adjacency.get(current) ?? []) {
          stack.push(neighbor);
        }
      }
    }

    const hasBranch = nodes.some(
      (node) => (inDegree.get(node.id) ?? 0) > 1 || (outDegree.get(node.id) ?? 0) > 1,
    );
    if (hasBranch) {
      branching += 1;
    } else if (components > 1) {
      disconnected += 1;
    } else {
      connectedLinear += 1;
    }
  }

  return { connectedLinear, disconnected, branching };
}

function countValues(rows, candidates) {
  const field = candidates.find((candidate) => rows.some((row) => row[candidate]));
  if (!field) {
    return { field: null, counts: {} };
  }
  const counts = {};
  for (const row of rows) {
    const value = row[field] || "not_recorded";
    counts[value] = (counts[value] ?? 0) + 1;
  }
  return { field, counts };
}

export function loadAndValidateSnapshot({ reportRoot, repoRoot }) {
  const csvPath = resolve(reportRoot, "public", "data", "lean_easy_failure_patterns.csv");
  const tracesPath = resolve(reportRoot, "public", "data", "lean_easy_failure_traces.json");
  const rawDir = resolve(repoRoot, "data", "batch", "version_1_trial_traces");
  if (!existsSync(csvPath) || !existsSync(tracesPath)) {
    throw new Error("Report CSV or trace JSON is missing; run the analyzer first");
  }

  const csvText = readFileSync(csvPath, "utf8");
  const tracesText = readFileSync(tracesPath, "utf8");
  const rows = parseCsv(csvText);
  const traces = JSON.parse(tracesText);
  if (!Array.isArray(traces)) {
    throw new Error("Trace payload must be a JSON array");
  }
  if (rows.length !== EXPECTED_TRIALS || traces.length !== EXPECTED_TRIALS) {
    throw new Error(
      `Expected ${EXPECTED_TRIALS} CSV rows and traces; found ${rows.length} and ${traces.length}`,
    );
  }

  const csvIds = sortedUnique(rows.map((row) => row.trial_id), "CSV");
  const traceIds = sortedUnique(traces.map((trace) => trace.trial_id), "Trace JSON");
  const raw = rawTraceSummary(rawDir);
  assertSameIds(csvIds, traceIds, "CSV/trace JSON");
  assertSameIds(csvIds, raw.trialIds, "CSV/raw JSONL");

  const rowsWithSourceHashes = rows.filter((row) => row.source_sha256);
  if (rowsWithSourceHashes.length > 0) {
    if (rowsWithSourceHashes.length !== rows.length) {
      throw new Error("source_sha256 must be present on every CSV row or none");
    }
    for (const row of rowsWithSourceHashes) {
      if (row.source_sha256 !== raw.sourceSha256ByTrial[row.trial_id]) {
        throw new Error(`Raw source hash mismatch for ${row.trial_id}`);
      }
    }
  }

  const analysisHashes = [
    ...new Set(rows.map((row) => row.analysis_snapshot_sha256).filter(Boolean)),
  ].sort();
  if (analysisHashes.length > 1) {
    throw new Error("CSV rows reference more than one analysis snapshot");
  }

  const perTaskCounts = {};
  for (const row of rows) {
    perTaskCounts[row.task_id] = (perTaskCounts[row.task_id] ?? 0) + 1;
  }
  const taskIds = Object.keys(perTaskCounts).sort();
  if (taskIds.length !== EXPECTED_TASKS) {
    throw new Error(`Expected ${EXPECTED_TASKS} tasks; found ${taskIds.length}`);
  }
  for (const taskId of taskIds) {
    if (perTaskCounts[taskId] !== EXPECTED_TRIALS_PER_TASK) {
      throw new Error(
        `Expected ${EXPECTED_TRIALS_PER_TASK} trials for ${taskId}; found ${perTaskCounts[taskId]}`,
      );
    }
  }

  for (const trace of traces) {
    const row = rows.find((candidate) => candidate.trial_id === trace.trial_id);
    if (!row || row.task_id !== trace.task_id) {
      throw new Error(`Task mismatch for ${trace.trial_id}`);
    }
  }

  const csvSha256 = sha256(csvText);
  const tracesSha256 = sha256(tracesText);
  const trialIdsSha256 = sha256(csvIds.join("\n"));
  const topology = graphSummary(traces);
  const confidence = countValues(rows, ["review_confidence", "diagnosis_confidence", "confidence"]);
  const reviewStatus = countValues(rows, ["review_status"]);
  const kernel = countValues(rows, ["validation_status", "final_proof_compiles"]);
  const kernelEnvironment = countValues(rows, ["kernel_status"]);
  const snapshotSha256 = sha256(
    [csvSha256, tracesSha256, raw.rawSha256, trialIdsSha256].join(":"),
  );

  return {
    csvText,
    tracesText,
    rows,
    traces,
    manifest: {
      schema_version: "1.0.0",
      trial_count: rows.length,
      task_count: taskIds.length,
      per_task_counts: perTaskCounts,
      event_count: raw.eventCount,
      anchor_labeled_event_count: raw.anchorLabeledEventCount,
      anchor_coverage:
        raw.eventCount > 0 ? raw.anchorLabeledEventCount / raw.eventCount : 0,
      topology,
      confidence,
      review_status: reviewStatus,
      kernel,
      kernel_environment: kernelEnvironment,
      csv_sha256: csvSha256,
      traces_sha256: tracesSha256,
      raw_sha256: raw.rawSha256,
      analysis_snapshot_sha256: analysisHashes[0] ?? null,
      trial_ids_sha256: trialIdsSha256,
      snapshot_sha256: snapshotSha256,
    },
  };
}

export function writeManifest(reportRoot, manifest) {
  const path = resolve(reportRoot, "public", "data", "report_snapshot.json");
  writeFileSync(path, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  return path;
}

export function assertManifestMatches(reportRoot, manifest) {
  const path = resolve(reportRoot, "public", "data", "report_snapshot.json");
  if (!existsSync(path)) {
    throw new Error(`Missing report snapshot manifest: ${path}`);
  }
  const recorded = JSON.parse(readFileSync(path, "utf8"));
  if (recorded.snapshot_sha256 !== manifest.snapshot_sha256) {
    throw new Error(
      `Snapshot changed during export: ${recorded.snapshot_sha256} != ${manifest.snapshot_sha256}`,
    );
  }
}
