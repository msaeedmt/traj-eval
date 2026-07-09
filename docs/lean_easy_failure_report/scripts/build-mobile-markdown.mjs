import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const csvPath = resolve(root, "public", "data", "lean_easy_failure_patterns.csv");
const tracePath = resolve(root, "public", "data", "lean_easy_failure_traces.json");
const outFile = resolve(root, "lean_easy_failure_report_mobile.md");

function parseCsv(text) {
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
      continue;
    }
    if (char === '"') {
      inQuotes = !inQuotes;
      continue;
    }
    if (char === "," && !inQuotes) {
      row.push(cell);
      cell = "";
      continue;
    }
    if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && next === "\n") {
        i += 1;
      }
      row.push(cell);
      if (row.some((value) => value.length > 0)) {
        table.push(row);
      }
      row = [];
      cell = "";
      continue;
    }
    cell += char;
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
  return records.map((record) => {
    const item = {};
    headers.forEach((header, index) => {
      item[header] = record[index] ?? "";
    });
    return item;
  });
}

function countBy(rows, field) {
  const counts = new Map();
  rows.forEach((row) => {
    const key = row[field] || "none";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  });
  return counts;
}

function uniqueValues(rows, field) {
  return Array.from(new Set(rows.map((row) => row[field]).filter(Boolean))).sort();
}

function topLabel(rows, field) {
  const entries = Array.from(countBy(rows, field).entries()).sort((a, b) => {
    if (b[1] !== a[1]) {
      return b[1] - a[1];
    }
    return a[0].localeCompare(b[0]);
  });
  return entries[0]?.[0] ?? "none";
}

function escapeMd(value) {
  return String(value ?? "")
    .replaceAll("|", "\\|")
    .replaceAll("\r", " ")
    .replaceAll("\n", " ")
    .trim();
}

function compact(value, limit = 150) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, limit - 3).trim()}...`;
}

function countLine(rows, field) {
  return Array.from(countBy(rows, field).entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([key, value]) => `- ${key}: ${value}`)
    .join("\n");
}

function taskTable(rows) {
  const lines = [
    "| Task | Trials | Solved | Silent failure | Unknown | Unsolved | Dominant engineer label | Dominant global pattern |",
    "|---|---:|---:|---:|---:|---:|---|---|",
  ];
  for (const taskId of uniqueValues(rows, "task_id")) {
    const taskRows = rows.filter((row) => row.task_id === taskId);
    const outcomes = countBy(taskRows, "validator_outcome");
    lines.push(
      [
        taskId,
        taskRows.length,
        outcomes.get("solved") ?? 0,
        outcomes.get("silent_failure") ?? 0,
        outcomes.get("validation_unknown") ?? 0,
        outcomes.get("unsolved") ?? 0,
        topLabel(taskRows, "engineer_failure_label"),
        topLabel(taskRows, "global_graph_pattern"),
      ]
        .map(escapeMd)
        .join(" | ")
        .replace(/^/, "| ")
        .replace(/$/, " |"),
    );
  }
  return lines.join("\n");
}

function caseStudy(rows, taskId) {
  const taskRows = rows.filter((row) => row.task_id === taskId);
  const first = taskRows[0];
  if (!first) {
    return "";
  }
  return [
    `### ${taskId}`,
    "",
    `- Math question: ${compact(first.math_question, 280)}`,
    `- Naive human strategy: ${first.naive_human_strategy}`,
    `- Domain-specific LLM strategy: ${first.domain_specific_LLM_strategy}`,
    `- Dominant engineer label: ${topLabel(taskRows, "engineer_failure_label")}`,
    `- Dominant critic label: ${topLabel(taskRows, "critic_label")}`,
    `- Dominant global pattern: ${topLabel(taskRows, "global_graph_pattern")}`,
    "",
  ].join("\n");
}

function trialAppendix(rows) {
  const lines = [
    "| Trial | Outcome | First failure | Reasoner | Engineer | Critic | Tools | Failed compiles | Takeaway |",
    "|---|---|---|---|---|---|---:|---:|---|",
  ];
  for (const row of rows) {
    lines.push(
      [
        row.trial_id,
        row.validator_outcome,
        row.first_failure_stage,
        row.reasoner_strategy_label,
        row.engineer_failure_label,
        row.critic_label,
        row.n_tool_calls,
        row.n_failed_compiles,
        compact(row.presentation_takeaway, 120),
      ]
        .map(escapeMd)
        .join(" | ")
        .replace(/^/, "| ")
        .replace(/$/, " |"),
    );
  }
  return lines.join("\n");
}

function fencedLean(code) {
  if (!code) {
    return "_No Lean code captured._";
  }
  return ["```lean", code.trim(), "```"].join("\n");
}

function trajectoryAppendix(traces) {
  return traces
    .map((trace) => {
      const toolCalls = trace.tool_calls
        .map(
          (call) =>
            `- seq ${call.seq}: compiled=${call.compiled ?? "unknown"}, sorry_free=${call.sorry_free ?? "unknown"}`,
        )
        .join("\n");
      const timeline = trace.timeline
        .map((step) => {
          const marker = [step.role, step.type, step.tool, step.decision, step.handoff_target ? `to ${step.handoff_target}` : ""]
            .filter(Boolean)
            .join(" / ");
          return `- #${step.seq} ${marker}: ${compact(step.text, 180)}`;
        })
        .join("\n");
      return [
        `### ${trace.trial_id}`,
        "",
        `- Task: ${trace.task_id}`,
        `- Declared success: ${trace.declared_success}`,
        `- Submitted equals last verified: ${trace.submitted_eq_last_verified ?? "unknown"}`,
        `- Failed compiles: ${trace.n_failed_compiles}`,
        "",
        "Formal statement:",
        "",
        fencedLean(trace.formal_statement),
        "",
        "Submitted code:",
        "",
        fencedLean(trace.submitted_code),
        "",
        "Last verified code:",
        "",
        fencedLean(trace.last_verified_code),
        "",
        "check_lean calls:",
        "",
        toolCalls || "_No check_lean calls captured._",
        "",
        "Compact role timeline:",
        "",
        timeline,
        "",
      ].join("\n");
    })
    .join("\n");
}

const rows = parseCsv(readFileSync(csvPath, "utf8"));
const traces = JSON.parse(readFileSync(tracePath, "utf8"));
const outcomes = countBy(rows, "validator_outcome");
const critics = countBy(rows, "critic_label");

const markdown = [
  "# Lean Easy Failure Analysis",
  "",
  "Mobile Markdown export generated from `data/analysis/lean_easy_failure_patterns.csv`.",
  "",
  "## Summary",
  "",
  `- Trials: ${rows.length}`,
  `- Tasks: ${uniqueValues(rows, "task_id").length}`,
  `- Solved: ${outcomes.get("solved") ?? 0}`,
  `- Trace verified: ${outcomes.get("trace_verified") ?? 0}`,
  `- Silent failure: ${outcomes.get("silent_failure") ?? 0}`,
  `- Validation unknown: ${outcomes.get("validation_unknown") ?? 0}`,
  `- Unsolved: ${outcomes.get("unsolved") ?? 0}`,
  `- Critic false accept: ${critics.get("critic_false_accept") ?? 0}`,
  "",
  "## Proposal Alignment",
  "",
  "- O1 localization: partially supported by trace graph construction, role attribution, and first failure stage.",
  "- O2 taxonomy: supported by deterministic labels over reasoner, engineer, critic, and global behavior.",
  "- O3 early prediction: not claimed for this 100-trace slice.",
  "",
  "## Per-Task Pattern Table",
  "",
  taskTable(rows),
  "",
  "## Validator Outcomes",
  "",
  countLine(rows, "validator_outcome"),
  "",
  "## Role-Level Labels",
  "",
  "### Engineer failure labels",
  "",
  countLine(rows, "engineer_failure_label"),
  "",
  "### Critic labels",
  "",
  countLine(rows, "critic_label"),
  "",
  "### Global graph patterns",
  "",
  countLine(rows, "global_graph_pattern"),
  "",
  "## Case Studies",
  "",
  ["easy_fatem_111", "easy_fatem_115", "easy_leancat_001", "easy_leancat_002"]
    .map((taskId) => caseStudy(rows, taskId))
    .join("\n"),
  "## Reproducibility",
  "",
  "- Raw traces: `data/batch/*.jsonl`",
  "- Canonical CSV: `data/analysis/lean_easy_failure_patterns.csv`",
  "- HTML export: `docs/lean_easy_failure_report/lean_easy_failure_report_standalone.html`",
  "- Markdown export: `docs/lean_easy_failure_report/lean_easy_failure_report_mobile.md`",
  "- Generate both mobile exports: `npm.cmd run build:mobile` from `docs/lean_easy_failure_report`",
  "",
  "## Compact Trial Appendix",
  "",
  trialAppendix(rows),
  "",
  "## Lean Trajectory Appendix",
  "",
  trajectoryAppendix(traces),
  "",
].join("\n");

writeFileSync(outFile, markdown, "utf8");
console.log(`wrote ${outFile}`);
