import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { assertManifestMatches, loadAndValidateSnapshot } from "./report-data.mjs";

const root = resolve(import.meta.dirname, "..");
const repoRoot = resolve(root, "..", "..");
const outFile = resolve(root, "lean_easy_failure_report_mobile.md");

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

function topMultiLabel(rows, field) {
  const counts = new Map();
  for (const row of rows) {
    const labels = String(row[field] ?? "")
      .split(/[;|]/)
      .map((value) => value.trim())
      .filter(Boolean);
    for (const label of labels) {
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
  }
  return Array.from(counts.entries()).sort(
    (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
  )[0]?.[0] ?? "none";
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
    "| Task | Trials | Outcome breakdown | Outcome total | Provisional incident signal |",
    "|---|---:|---|---:|---|",
  ];
  for (const taskId of uniqueValues(rows, "task_id")) {
    const taskRows = rows.filter((row) => row.task_id === taskId);
    const outcomes = countBy(taskRows, "validator_outcome");
    const outcomeText = Array.from(outcomes.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([label, count]) => `${label}=${count}`)
      .join("; ");
    const outcomeTotal = Array.from(outcomes.values()).reduce((sum, count) => sum + count, 0);
    lines.push(
      [
        taskId,
        taskRows.length,
        outcomeText,
        `${outcomeTotal} / ${taskRows.length}`,
        topMultiLabel(taskRows, "error_labels") === "none"
          ? topLabel(taskRows, "engineer_failure_label")
          : topMultiLabel(taskRows, "error_labels"),
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
    `- Most frequent reviewed error label: ${topMultiLabel(taskRows, "error_labels")}`,
    `- Most frequent observed symptom: ${topMultiLabel(taskRows, "symptom_codes")}`,
    `- Review confidence: ${topLabel(taskRows, "review_confidence")}`,
    "",
  ].join("\n");
}

function trialAppendix(rows) {
  const lines = [
    "| Trial | Outcome | Verification | Workflow | Critical failure | Recovered | Confidence | Error labels |",
    "|---|---|---|---|---|---:|---|---|",
  ];
  for (const row of rows) {
    lines.push(
      [
        row.trial_id,
        row.validator_outcome,
        row.verification_level || row.kernel_status,
        row.workflow_outcome,
        [row.critical_failure_seq, row.critical_failure_label, row.critical_failure_role]
          .filter(Boolean)
          .join(" / "),
        row.recovered_failure_count,
        row.review_confidence,
        compact(row.error_labels || row.engineer_failure_label, 120),
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

function listValue(value) {
  if (Array.isArray(value)) {
    return value;
  }
  if (value == null || value === "" || value === "none") {
    return [];
  }
  return String(value).split("|").filter(Boolean);
}

function trajectoryAppendix(traces) {
  return traces
    .map((trace) => {
      const verification = trace.diagnosis?.verification ?? {};
      const candidate = trace.diagnosis?.candidate ?? {};
      const workflow = trace.diagnosis?.workflow ?? {};
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
          const summary = compact(step.text, 180);
          return `- #${step.seq} ${marker}: ${summary || "[empty message]"}`;
        })
        .join("\n");
      return [
        `### ${trace.trial_id}`,
        "",
        `- Task: ${trace.task_id}`,
        `- Submission accepted: ${trace.submission_accepted ?? candidate.workflow_approved ?? workflow.declared_success ?? trace.declared_success ?? "unknown"}`,
        `- Validation status: ${trace.validation_status ?? verification.validation_status ?? "not recorded"}`,
        `- Selected candidate kind: ${trace.submitted_kind ?? candidate.candidate_kind ?? candidate.kind ?? "not recorded"}`,
        `- Submission source: ${trace.submission_source ?? candidate.submission_source ?? "not recorded"}`,
        `- Prohibited placeholders: ${listValue(trace.prohibited_placeholders ?? verification.prohibited_placeholders).join(", ") || "none recorded"}`,
        `- Submitted equals last verified: ${trace.submitted_eq_last_verified ?? "unknown"}`,
        `- Failed compiles: ${trace.n_failed_compiles}`,
        `- Opaque infrastructure-unknown checks: ${trace.n_infrastructure_unknown_checks ?? "not recorded"}`,
        "",
        "Formal statement:",
        "",
        fencedLean(trace.formal_statement),
        "",
        "Submitted code:",
        "",
        fencedLean(trace.submitted_code),
        "",
        "Selected candidate code:",
        "",
        fencedLean(trace.accepted_candidate_code ?? trace.last_verified_code),
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

const snapshot = loadAndValidateSnapshot({ reportRoot: root, repoRoot });
assertManifestMatches(root, snapshot.manifest);
const rows = snapshot.rows;
const traces = snapshot.traces;
const kernelCounts = snapshot.manifest.kernel.counts;
const confidenceCounts = snapshot.manifest.confidence.counts;
const confidenceText = Object.keys(confidenceCounts).length
  ? Object.entries(confidenceCounts).map(([key, value]) => `${key}=${value}`).join(", ")
  : "not recorded in this snapshot";
const kernelEvidenceCount = Object.entries(kernelCounts)
  .filter(([key]) => {
    const normalized = key.toLowerCase();
    return !["none", "not_recorded", "unknown", "off", "disabled", "pending", "not_run", "not_evaluated", "unavailable"]
      .some((missing) => normalized === missing || normalized.startsWith(`${missing}:`));
  })
  .reduce((sum, [, value]) => sum + value, 0);
const anchorStatus = snapshot.manifest.anchor_labeled_event_count > 0
  ? `${snapshot.manifest.anchor_labeled_event_count} labelled anchors are present; detector validation remains separate.`
  : "No raw event carries a labelled anchor, so first-anchor localisation is not validated.";
const kernelStatus = kernelEvidenceCount > 0
  ? `${kernelEvidenceCount} trials carry a completed kernel result.`
  : "No trial carries a completed offline-kernel result.";

const markdown = [
  "# Lean Easy Failure Analysis",
  "",
  "Mobile evidence export generated from one validated CSV/trace/raw-JSONL snapshot.",
  "",
  `> **Evidence status:** trajectory observations are available. ${anchorStatus} ${kernelStatus} Outcome counts and earlier incidents are shown separately. Detector precision/recall/F1 has not been measured.`,
  "",
  "## Evidence Ledger",
  "",
  `- Trials: ${rows.length}`,
  `- Tasks: ${uniqueValues(rows, "task_id").length}`,
  `- Raw events: ${snapshot.manifest.event_count}`,
  `- Labelled anchors: ${snapshot.manifest.anchor_labeled_event_count} / ${snapshot.manifest.event_count}`,
  `- Offline-kernel field: ${snapshot.manifest.kernel.field ?? "not recorded"}`,
  `- Offline-kernel values: ${Object.entries(kernelCounts).map(([key, value]) => `${key}=${value}`).join(", ") || "not recorded"}`,
  `- Kernel environment: ${Object.entries(snapshot.manifest.kernel_environment.counts).map(([key, value]) => `${key}=${value}`).join(", ") || "not recorded"}`,
  `- Review confidence: ${confidenceText}`,
  `- Timeline topology: connected linear=${snapshot.manifest.topology.connectedLinear}, disconnected=${snapshot.manifest.topology.disconnected}, branching=${snapshot.manifest.topology.branching}`,
  `- Snapshot SHA-256: \`${snapshot.manifest.snapshot_sha256}\``,
  `- Analyzer snapshot SHA-256: \`${snapshot.manifest.analysis_snapshot_sha256 ?? "not recorded"}\``,
  "- Warehouse evidence used: no matched Lean control; STARGAZER history is excluded from these counts and no architecture comparison is claimed.",
  "",
  "## Proposal Alignment",
  "",
  `- O1 localisation infrastructure: event order and role attribution are inspectable. ${anchorStatus}`,
  "- O2 taxonomy: current labels are **exploratory detector outputs**, not validated diagnoses. Precision/recall/F1 and independent gold labels are absent.",
  "- O3 comparison/early prediction: **not evaluated** for this single model, architecture, grounding setting, and stress level.",
  "- Timeline edges preserve recorded ordering/dependency links; this mostly linear topology is not evidence of a causal mechanism.",
  "",
  "## Final Outcomes",
  "",
  "Final outcomes describe the terminal evidence state. They do not erase recovered incidents, and an earlier incident does not make a successful terminal outcome a failure.",
  "",
  countLine(rows, "validator_outcome"),
  "",
  "## Per-Task Pattern Table",
  "",
  taskTable(rows),
  "",
  "## Exploratory Incident Signals",
  "",
  "These legacy role/global labels are provisional observations. They may describe recovered events and must not be read as final trial outcomes or independently confirmed causes.",
  "",
  "### Engineer incident labels",
  "",
  countLine(rows, "engineer_failure_label"),
  "",
  "### Critic detector labels",
  "",
  countLine(rows, "critic_label"),
  "",
  "### Global trace-pattern labels",
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
  "- Raw traces: `data/batch/version_1_trial_traces/*.jsonl`",
  "- Canonical CSV: `data/analysis/lean_easy_failure_patterns.csv`",
  "- HTML export: `docs/lean_easy_failure_report/lean_easy_failure_report_standalone.html`",
  "- Markdown export: `docs/lean_easy_failure_report/lean_easy_failure_report_mobile.md`",
  `- Validated snapshot: \`${snapshot.manifest.snapshot_sha256}\``,
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
console.log(
  `wrote ${outFile} with ${snapshot.manifest.trial_count} traces (snapshot ${snapshot.manifest.snapshot_sha256})`,
);
