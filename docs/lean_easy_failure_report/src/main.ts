import "./styles.css";
import {
  CsvRow,
  ReportSummary,
  countBy,
  parseCsv,
  summarize,
  taskSummaries,
  topLabel,
  uniqueValues,
} from "./report";

const DATA_URL = "data/lean_easy_failure_patterns.csv";
const TRACE_URL = "data/lean_easy_failure_traces.json";
const SNAPSHOT_URL = "data/report_snapshot.json";
const app = document.querySelector<HTMLDivElement>("#app");

type TraceStep = {
  event_id: string;
  seq: number;
  role: string;
  type: string;
  caused_by: string[];
  tool?: string;
  decision?: string;
  handoff_target?: string;
  text: string;
  lean_code?: string;
  anchor?: unknown;
  incident_labels?: string[];
  recovered?: boolean | null;
};

type ToolCall = {
  seq: number;
  result_seq?: number | null;
  role?: string;
  compiled: boolean | null;
  sorry_free: boolean | null;
  candidate_kind?: string | null;
  statement_match?: string | null;
  diagnostic?: string | null;
  code: string | null;
};

type TraceDoc = {
  task_id: string;
  trial_id: string;
  trial_number: number;
  source: string;
  difficulty: string;
  informal: string;
  formal_statement: string;
  submitted_code?: string | null;
  accepted_candidate_code?: string | null;
  last_verified_code?: string | null;
  submitted_kind?: string | null;
  last_verified_kind?: string | null;
  submission_source?: string | null;
  submission_accepted?: boolean | null;
  validation_status?: string | null;
  validation_error?: string | null;
  prohibited_placeholders?: string[];
  submitted_eq_last_verified?: boolean | null;
  declared_success?: boolean;
  n_tool_calls: number;
  n_failed_compiles: number;
  n_infrastructure_unknown_checks?: number;
  tool_calls: ToolCall[];
  graph: TraceGraph;
  diagnosis: Diagnosis;
  timeline: TraceStep[];
};

type TraceGraph = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

type GraphNode = {
  id: string;
  seq: number;
  role: string;
  type: string;
  tool?: string;
  decision?: string;
  handoff_target?: string;
  status: string;
  label: string;
};

type GraphEdge = {
  source: string;
  target: string;
};

type Diagnosis = {
  headline?: string;
  status?: string;
  reasoner?: string;
  engineer?: string;
  critic?: string;
  global?: string;
  artifact?: string;
  takeaway?: string;
  evidence_seqs?: Record<string, number[]>;
  verification?: Record<string, unknown>;
  candidate?: Record<string, unknown> | string | null;
  workflow?: Record<string, unknown> | string | null;
  symptom_codes?: string[];
  causal_labels?: string[];
  incidents?: Array<Record<string, unknown>>;
  critical_failure?: Record<string, unknown> | string | null;
  recovered_failure_seqs?: number[];
  downstream_effects?: string[];
  assessments?: Record<string, unknown>;
  task_diagnosis?: Record<string, unknown> | string | null;
  review_status?: string;
  review_confidence?: string;
};

type SnapshotDoc = {
  schema_version: string;
  trial_count: number;
  task_count: number;
  per_task_counts: Record<string, number>;
  event_count: number;
  anchor_labeled_event_count: number;
  anchor_coverage: number;
  topology: {
    connectedLinear: number;
    disconnected: number;
    branching: number;
  };
  confidence: { field: string | null; counts: Record<string, number> };
  review_status: { field: string | null; counts: Record<string, number> };
  kernel: { field: string | null; counts: Record<string, number> };
  kernel_environment: { field: string | null; counts: Record<string, number> };
  csv_sha256: string;
  traces_sha256: string;
  raw_sha256: string;
  analysis_snapshot_sha256: string | null;
  trial_ids_sha256: string;
  snapshot_sha256: string;
};

type State = {
  rows: CsvRow[];
  traces: TraceDoc[];
  fields: string[];
  search: string;
  task: string;
  outcome: string;
  engineer: string;
  sortField: string;
  sortDir: "asc" | "desc";
  page: number;
  pageSize: number;
  selectedTrial: string;
  selectedNodeId: string;
  snapshot: SnapshotDoc | null;
};

const state: State = {
  rows: [],
  traces: [],
  fields: [],
  search: "",
  task: "",
  outcome: "",
  engineer: "",
  sortField: "task_id",
  sortDir: "asc",
  page: 1,
  pageSize: 20,
  selectedTrial: "",
  selectedNodeId: "",
  snapshot: null,
};

const CSV_VISIBLE_FIELDS = [
  "trial_id",
  "task_id",
  "validator_outcome",
  "verification_level",
  "kernel_status",
  "validation_status",
  "candidate_kind",
  "statement_match",
  "submission_accepted",
  "workflow_outcome",
  "symptom_codes",
  "error_labels",
  "critical_failure_label",
  "recovered_failure_count",
  "review_confidence",
  "review_status",
  "reasoner_strategy_label",
  "engineer_failure_label",
  "critic_label",
  "global_graph_pattern",
  "first_failure_stage",
  "n_tool_calls",
  "n_failed_compiles",
  "n_infrastructure_unknown_checks",
];

function escapeHtml(value: unknown): string {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function displayRole(role: string): string {
  if (role.toLowerCase() === "executor") {
    return "tool runtime (legacy executor label)";
  }
  if (role.toLowerCase() === "planner") {
    return "planner (legacy)";
  }
  return role;
}

function cls(value: string): string {
  return value.replaceAll("_", "-").replaceAll("/", "-");
}

function option(value: string, label: string, selected: string): string {
  return `<option value="${escapeHtml(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
}

function fieldValue(row: CsvRow | undefined, ...fields: string[]): string {
  for (const field of fields) {
    const value = row?.[field];
    if (value) {
      return value;
    }
  }
  return "not recorded";
}

function displayValue(value: unknown): string {
  if (value == null || value === "") {
    return "not recorded";
  }
  if (Array.isArray(value)) {
    return value.length ? value.map(displayValue).join(", ") : "none observed";
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    return entries.length
      ? entries.map(([key, item]) => `${key}=${displayValue(item)}`).join("; ")
      : "not recorded";
  }
  return String(value);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value != null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function countSummary(counts: Record<string, number>): string {
  const entries = Object.entries(counts);
  if (!entries.length) {
    return "not recorded";
  }
  return entries
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([label, count]) => `${label}=${count}`)
    .join(", ");
}

function filteredRows(): CsvRow[] {
  const query = state.search.trim().toLowerCase();
  const numericFields = new Set([
    "trial_number",
    "n_tool_calls",
    "n_failed_compiles",
    "n_infrastructure_unknown_checks",
  ]);
  const rows = state.rows
    .filter((row) => {
      if (state.task && row.task_id !== state.task) {
        return false;
      }
      if (state.outcome && row.validator_outcome !== state.outcome) {
        return false;
      }
      if (state.engineer && row.engineer_failure_label !== state.engineer) {
        return false;
      }
      if (!query) {
        return true;
      }
      return state.fields.some((field) => (row[field] || "").toLowerCase().includes(query));
    })
    .sort((a, b) => {
      const av = a[state.sortField] || "";
      const bv = b[state.sortField] || "";
      const result = numericFields.has(state.sortField)
        ? Number(av || 0) - Number(bv || 0)
        : av.localeCompare(bv);
      return state.sortDir === "asc" ? result : -result;
    });
  return rows;
}

function renderStat(label: string, value: string | number, note: string): string {
  return `
    <div class="stat">
      <div class="stat-label">${escapeHtml(label)}</div>
      <div class="stat-value">${escapeHtml(value)}</div>
      <div class="stat-note">${escapeHtml(note)}</div>
    </div>
  `;
}

function renderHeader(summary: ReportSummary, snapshot: SnapshotDoc): string {
  return `
    <header class="report-header">
      <div class="header-inner">
        <div class="header-copy">
          <p class="eyebrow">Evidence-first trajectory audit</p>
          <h1>Lean Easy Failure Analysis</h1>
          <p class="header-subtitle">
            One synchronized snapshot of 100 Lean trajectories. Final outcomes,
            recovered incidents, verification evidence, and exploratory diagnoses
            are kept separate so trace activity is not mistaken for kernel truth.
          </p>
        </div>
        <div class="header-panel">
          <div class="panel-title">Claim gate</div>
          <div class="source-chip muted">O1: timeline available; anchor localisation unvalidated</div>
          <div class="source-chip muted">O2: taxonomy exploratory; detector P/R/F1 unmeasured</div>
          <div class="source-chip muted">O3: not evaluated in this single configuration</div>
          <div class="source-chip">Snapshot: ${escapeHtml(snapshot.snapshot_sha256.slice(0, 16))}…</div>
        </div>
      </div>
      <div class="stats-grid">
        ${renderStat("Trials", summary.trials, "ID-matched raw/CSV/JSON")}
        ${renderStat("Tasks", summary.tasks, "10 trials each, build-enforced")}
        ${renderStat("Silent failures", summary.silentFailure, "workflow accepted; strict validator rejected")}
        ${renderStat("Kernel accepted", summary.kernelAccepted, "independent offline validation")}
        ${renderStat("Kernel unknown", summary.kernelUnknown, "validation not completed")}
        ${renderStat("Labelled anchors", snapshot.anchor_labeled_event_count, `of ${snapshot.event_count} raw events`)}
      </div>
    </header>
  `;
}

function selectedTrace(): TraceDoc | undefined {
  if (!state.selectedTrial) {
    return state.traces.find((trace) => !state.task || trace.task_id === state.task) ?? state.traces[0];
  }
  return state.traces.find((trace) => trace.trial_id === state.selectedTrial) ?? state.traces[0];
}

function selectedNode(trace: TraceDoc): GraphNode | undefined {
  if (state.selectedNodeId) {
    const explicit = trace.graph.nodes.find((node) => node.id === state.selectedNodeId);
    if (explicit) {
      return explicit;
    }
  }
  return (
    trace.graph.nodes.find((node) => node.status === "fail") ??
    trace.graph.nodes.find((node) => node.role === "engineer") ??
    trace.graph.nodes[0]
  );
}

function selectedStep(trace: TraceDoc, node: GraphNode | undefined): TraceStep | undefined {
  if (!node) {
    return undefined;
  }
  return trace.timeline.find((step) => step.event_id === node.id);
}

function traceOutcome(trace: TraceDoc): CsvRow | undefined {
  return state.rows.find((row) => row.trial_id === trace.trial_id);
}

function codeBlock(code: string | null | undefined): string {
  if (!code) {
    return `<div class="empty-code">No Lean code captured for this slot.</div>`;
  }
  return `<pre class="lean-code"><code>${escapeHtml(code)}</code></pre>`;
}

function verdictPill(value: boolean | null | undefined): string {
  if (value === true) {
    return `<span class="pill pass">true</span>`;
  }
  if (value === false) {
    return `<span class="pill fail">false</span>`;
  }
  return `<span class="pill unknown">unknown</span>`;
}

function statementMatchPill(value: unknown): string {
  const status = displayValue(value);
  const normalized = status.toLowerCase();
  const tone = normalized === "exact"
    ? "pass"
    : ["changed", "not_target"].includes(normalized)
      ? "fail"
      : "unknown";
  return `<span class="pill ${tone}">${escapeHtml(status)}</span>`;
}

function renderTraceGraph(trace: TraceDoc): string {
  const roleLanes = ["system", "reasoner", "engineer", "executor", "critic", "planner"];
  const laneFor = (role: string) => {
    const found = roleLanes.indexOf(role);
    return found >= 0 ? found : roleLanes.length;
  };
  const width = Math.max(980, trace.graph.nodes.length * 46 + 120);
  const height = 420;
  const laneHeight = 56;
  const top = 44;
  const left = 58;
  const positions = new Map<string, { x: number; y: number }>();
  trace.graph.nodes.forEach((node, index) => {
    positions.set(node.id, {
      x: left + index * 46,
      y: top + laneFor(node.role) * laneHeight,
    });
  });
  const edges = trace.graph.edges
    .map((edge) => {
      const source = positions.get(edge.source);
      const target = positions.get(edge.target);
      if (!source || !target) {
        return "";
      }
      return `<line class="graph-edge" x1="${source.x}" y1="${source.y}" x2="${target.x}" y2="${target.y}" />`;
    })
    .join("");
  const lanes = roleLanes
    .map((role, index) => {
      const y = top + index * laneHeight;
      return `
        <g class="graph-lane">
          <text x="8" y="${y + 4}">${escapeHtml(displayRole(role))}</text>
          <line x1="54" y1="${y}" x2="${width - 32}" y2="${y}" />
        </g>
      `;
    })
    .join("");
  const current = selectedNode(trace);
  const nodes = trace.graph.nodes
    .map((node) => {
      const pos = positions.get(node.id);
      if (!pos) {
        return "";
      }
      const active = current?.id === node.id ? " active" : "";
      const label = `${node.seq} ${displayRole(node.role)} ${node.type}`;
      return `
        <g class="graph-node ${cls(node.role)} ${cls(node.status)}${active}" data-node-id="${escapeHtml(node.id)}" tabindex="0" role="button" aria-label="${escapeHtml(label)}">
          <circle cx="${pos.x}" cy="${pos.y}" r="13"></circle>
          <text x="${pos.x}" y="${pos.y + 4}" text-anchor="middle">${escapeHtml(node.seq)}</text>
          <title>${escapeHtml(label)}</title>
        </g>
      `;
    })
    .join("");

  return `
    <div class="graph-scroll">
      <svg class="trace-graph" viewBox="0 0 ${width} ${height}" role="img" aria-label="Role-lane event timeline">
        <defs>
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M 0 0 L 8 4 L 0 8 z"></path>
          </marker>
        </defs>
        ${lanes}
        <g>${edges}</g>
        <g>${nodes}</g>
      </svg>
    </div>
  `;
}

function renderNodeDetail(trace: TraceDoc): string {
  const node = selectedNode(trace);
  const step = selectedStep(trace, node);
  if (!node || !step) {
    return `<article class="node-detail"><h3>No node selected</h3></article>`;
  }
  return `
    <article class="node-detail">
      <div class="proof-head">
        <h3>Event #${escapeHtml(node.seq)}</h3>
        <span class="outcome-badge">${escapeHtml(node.status)}</span>
      </div>
      <dl class="node-fields">
        <div><dt>Role</dt><dd>${escapeHtml(displayRole(node.role))}</dd></div>
        <div><dt>Type</dt><dd>${escapeHtml(node.type)}</dd></div>
        <div><dt>Tool</dt><dd>${escapeHtml(node.tool ?? "none")}</dd></div>
        <div><dt>Decision</dt><dd>${escapeHtml(node.decision ?? "none")}</dd></div>
        <div><dt>Handoff</dt><dd>${escapeHtml(node.handoff_target ?? "none")}</dd></div>
        <div><dt>Parents</dt><dd>${escapeHtml(step.caused_by.length)}</dd></div>
      </dl>
      ${step.lean_code ? codeBlock(step.lean_code) : `<p class="event-text">${escapeHtml(step.text || "No text captured.")}</p>`}
    </article>
  `;
}

function renderDiagnosis(trace: TraceDoc, row: CsvRow | undefined): string {
  const d = trace.diagnosis;
  const assessments = d.assessments ?? {};
  const verification = d.verification ?? {};
  return `
    <section class="diagnosis-panel">
      <div class="diagnosis-head">
        <div>
          <p class="eyebrow dark">Exploratory trace diagnosis</p>
          <h3>${escapeHtml(d.headline ?? "Trajectory evidence summary")}</h3>
        </div>
        <span class="outcome-badge">${escapeHtml(d.status ?? row?.validator_outcome ?? "unknown")}</span>
      </div>
      <div class="diagnosis-grid">
        <article><h4>Math question</h4><p>${escapeHtml(trace.informal)}</p></article>
        <article><h4>Human strategy</h4><p>${escapeHtml(row?.naive_human_strategy ?? "")}</p></article>
        <article><h4>Domain LLM strategy</h4><p>${escapeHtml(row?.domain_specific_LLM_strategy ?? "")}</p></article>
        <article><h4>Reasoner assessment</h4><p>${escapeHtml(displayValue(assessments.reasoner ?? d.reasoner))}</p></article>
        <article><h4>Engineer assessment</h4><p>${escapeHtml(displayValue(assessments.engineer ?? d.engineer))}</p></article>
        <article><h4>Critic assessment</h4><p>${escapeHtml(displayValue(assessments.critic ?? d.critic))}</p></article>
        <article><h4>Verification</h4><p>${escapeHtml(displayValue(Object.keys(verification).length ? verification : d.artifact))}</p></article>
        <article><h4>Observed symptoms</h4><p>${escapeHtml(displayValue(d.symptom_codes ?? row?.symptom_codes))}</p></article>
        <article><h4>Causal labels</h4><p>${escapeHtml(displayValue(d.causal_labels ?? row?.error_labels))}</p></article>
        <article><h4>Critical unrecovered event</h4><p>${escapeHtml(displayValue(d.critical_failure ?? fieldValue(row, "critical_failure_label", "critical_failure_seq")))}</p></article>
        <article><h4>Recovered incidents</h4><p>${escapeHtml(displayValue(d.recovered_failure_seqs ?? fieldValue(row, "recovered_failure_count")))}</p></article>
        <article><h4>Downstream effects</h4><p>${escapeHtml(displayValue(d.downstream_effects))}</p></article>
        <article><h4>Review confidence</h4><p>${escapeHtml(d.review_confidence ?? fieldValue(row, "review_confidence"))}</p></article>
        <article><h4>Review status</h4><p>${escapeHtml(d.review_status ?? fieldValue(row, "review_status"))}</p></article>
      </div>
      <p class="diagnosis-takeaway">Legacy role/global labels can describe recovered incidents. Treat the terminal outcome and independent verification fields as separate evidence; causal attribution remains provisional until reviewed evidence and confidence are recorded.</p>
    </section>
  `;
}

function renderLeanReader(): string {
  const trace = selectedTrace();
  if (!trace) {
    return "";
  }
  const row = traceOutcome(trace);
  const verification = asRecord(trace.diagnosis.verification);
  const candidate = asRecord(trace.diagnosis.candidate);
  const workflow = asRecord(trace.diagnosis.workflow);
  const taskOptions = uniqueValues(state.rows, "task_id")
    .map((taskId) => option(taskId, taskId, state.task || trace.task_id))
    .join("");
  const trialOptions = state.traces
    .filter((item) => !state.task || item.task_id === state.task)
    .map((item) => option(item.trial_id, item.trial_id, trace.trial_id))
    .join("");
  const toolRows = trace.tool_calls
    .map(
      (call, index) => `
        <details class="tool-card" ${index === trace.tool_calls.length - 1 ? "open" : ""}>
          <summary>
            <span>check_lean seq ${escapeHtml(call.seq)}</span>
            ${verdictPill(call.compiled)}
            <span class="muted-inline">sorry_free</span>
            ${verdictPill(call.sorry_free)}
            ${call.candidate_kind ? `<span class="tool-name">${escapeHtml(call.candidate_kind)}</span>` : ""}
            <span class="muted-inline">statement_match</span>
            ${statementMatchPill(call.statement_match)}
          </summary>
          ${codeBlock(call.code)}
          ${call.diagnostic ? `<p class="tool-diagnostic">${escapeHtml(call.diagnostic)}</p>` : ""}
        </details>
      `,
    )
    .join("");
  const timeline = trace.timeline
    .map(
      (step) => `
        <details class="timeline-step ${cls(step.role)}" ${state.selectedNodeId === step.event_id ? "open" : ""}>
          <summary>
            <span class="seq">#${escapeHtml(step.seq)}</span>
            <strong>${escapeHtml(displayRole(step.role))}</strong>
            <span>${escapeHtml(step.type)}</span>
            ${step.tool ? `<span class="tool-name">${escapeHtml(step.tool)}</span>` : ""}
            ${step.decision ? `<span class="decision">${escapeHtml(step.decision)}</span>` : ""}
            ${step.handoff_target ? `<span class="handoff">to ${escapeHtml(step.handoff_target)}</span>` : ""}
          </summary>
          ${step.lean_code ? codeBlock(step.lean_code) : `<p>${escapeHtml(step.text)}</p>`}
        </details>
      `,
    )
    .join("");

  return `
    <section class="section lean-reader" id="lean-reader">
      <div class="section-head">
        <div>
          <p class="eyebrow dark">Trace-first JSON reader</p>
          <h2>Event Timeline, Diagnosis, And Proof Evidence</h2>
        </div>
        <p class="section-note">
          Nodes follow recorded event order and role lanes. Edges preserve logged
          predecessor/dependency links; this mostly linear topology is not proof of causality.
        </p>
      </div>
      <div class="trace-shell">
        <aside class="trace-sidebar">
          <label>
            Task
            <select id="reader-task">${taskOptions}</select>
          </label>
          <label>
            Trial
            <select id="reader-trial">${trialOptions}</select>
          </label>
          <dl class="trace-facts">
            <div><dt>Trial</dt><dd>${escapeHtml(trace.trial_id)}</dd></div>
            <div><dt>Outcome</dt><dd>${escapeHtml(row?.validator_outcome ?? "unknown")}</dd></div>
            <div><dt>Verification level</dt><dd>${escapeHtml(fieldValue(row, "verification_level"))}</dd></div>
            <div><dt>Kernel environment</dt><dd>${escapeHtml(fieldValue(row, "kernel_status"))}</dd></div>
            <div><dt>Validation status</dt><dd>${escapeHtml(fieldValue(row, "validation_status"))}</dd></div>
            <div><dt>Proof compiles</dt><dd>${escapeHtml(fieldValue(row, "final_proof_compiles"))}</dd></div>
            <div><dt>Critical event</dt><dd>${escapeHtml(fieldValue(row, "critical_failure_seq", "critical_failure_label"))}</dd></div>
            <div><dt>Recovered incidents</dt><dd>${escapeHtml(fieldValue(row, "recovered_failure_count"))}</dd></div>
            <div><dt>Confidence</dt><dd>${escapeHtml(fieldValue(row, "review_confidence"))}</dd></div>
            <div><dt>Nodes</dt><dd>${escapeHtml(trace.graph.nodes.length)}</dd></div>
            <div><dt>Edges</dt><dd>${escapeHtml(trace.graph.edges.length)}</dd></div>
            <div><dt>Tool calls</dt><dd>${escapeHtml(trace.n_tool_calls)}</dd></div>
            <div><dt>Failed compiles</dt><dd>${escapeHtml(trace.n_failed_compiles)}</dd></div>
            <div><dt>Opaque check results</dt><dd>${escapeHtml(trace.n_infrastructure_unknown_checks ?? fieldValue(row, "n_infrastructure_unknown_checks"))}</dd></div>
          </dl>
        </aside>
        <div class="graph-panel">
          ${renderTraceGraph(trace)}
        </div>
        ${renderNodeDetail(trace)}
      </div>
      ${renderDiagnosis(trace, row)}
      <div class="reader-layout lower-reader">
        <article class="proof-panel">
          <h3>Proof Artifacts</h3>
          <dl class="evidence-grid">
            <div><dt>Submission accepted</dt><dd>${verdictPill(trace.submission_accepted ?? candidate.workflow_approved as boolean | null | undefined ?? workflow.declared_success as boolean | null | undefined ?? trace.declared_success)}</dd></div>
            <div><dt>Validation status</dt><dd>${escapeHtml(displayValue(trace.validation_status ?? verification.validation_status))}</dd></div>
            <div><dt>Selected candidate kind</dt><dd>${escapeHtml(displayValue(trace.submitted_kind ?? candidate.candidate_kind ?? candidate.kind))}</dd></div>
            <div><dt>Submission source</dt><dd>${escapeHtml(displayValue(trace.submission_source ?? candidate.submission_source))}</dd></div>
            <div><dt>Statement match</dt><dd>${statementMatchPill(candidate.statement_match)}</dd></div>
            <div><dt>Prohibited placeholders</dt><dd>${escapeHtml(displayValue(trace.prohibited_placeholders ?? verification.prohibited_placeholders))}</dd></div>
            <div><dt>Submitted equals last verified</dt><dd>${verdictPill(trace.submitted_eq_last_verified)}</dd></div>
          </dl>
          ${trace.validation_error ?? verification.validation_error ? `<p class="validation-error"><strong>Validation diagnostic:</strong> ${escapeHtml(displayValue(trace.validation_error ?? verification.validation_error))}</p>` : ""}
          <h4>Formal Statement</h4>
          ${codeBlock(trace.formal_statement)}
          <h4>Workflow-submitted Code</h4>
          ${codeBlock(trace.submitted_code)}
          <h4>Selected Candidate Code</h4>
          ${codeBlock(trace.accepted_candidate_code ?? trace.last_verified_code)}
        </article>
        <article class="proof-panel">
          <h3>check_lean Calls</h3>
          <div class="tool-list">${toolRows || `<p>No check_lean calls captured.</p>`}</div>
        </article>
      </div>
      <div class="timeline-list compact-timeline">
        <h3>Raw Timeline</h3>
        ${timeline}
      </div>
    </section>
  `;
}

function renderCsvExplorer(rows: CsvRow[]): string {
  const pageCount = Math.max(1, Math.ceil(rows.length / state.pageSize));
  if (state.page > pageCount) {
    state.page = pageCount;
  }
  const start = (state.page - 1) * state.pageSize;
  const pageRows = rows.slice(start, start + state.pageSize);
  const taskOptions = [
    option("", "All tasks", state.task),
    ...uniqueValues(state.rows, "task_id").map((value) => option(value, value, state.task)),
  ].join("");
  const outcomeOptions = [
    option("", "All outcomes", state.outcome),
    ...uniqueValues(state.rows, "validator_outcome").map((value) => option(value, value, state.outcome)),
  ].join("");
  const engineerOptions = [
    option("", "All engineer signals", state.engineer),
    ...uniqueValues(state.rows, "engineer_failure_label").map((value) =>
      option(value, value, state.engineer),
    ),
  ].join("");

  const visibleFields = CSV_VISIBLE_FIELDS.filter((field) => state.fields.includes(field));
  const headers = visibleFields
    .map((field) => {
      const active = state.sortField === field;
      const marker = active ? (state.sortDir === "asc" ? " up" : " down") : "";
      return `
        <th>
          <button class="sort-button${active ? " active" : ""}" data-sort="${escapeHtml(field)}">
            ${escapeHtml(field)}${escapeHtml(marker)}
          </button>
        </th>
      `;
    })
    .join("");
  const body = pageRows
    .map(
      (row) => `
        <tr>
          <td><button class="open-trace-button" data-open-trace="${escapeHtml(row.trial_id)}">Open</button></td>
          ${visibleFields
            .map((field) => `<td class="${field === "presentation_takeaway" ? "wide-cell" : ""}">${escapeHtml(row[field] || "")}</td>`)
            .join("")}
        </tr>
      `,
    )
    .join("");

  return `
    <section class="section csv-first" id="complete-csv">
      <div class="section-head">
        <div>
          <p class="eyebrow dark">Canonical artifact</p>
          <h2>Complete CSV Explorer</h2>
        </div>
        <p class="section-note">
          Source: data/analysis/lean_easy_failure_patterns.csv copied into public/data for this report.
        </p>
      </div>
      <div class="controls">
        <label>
          Search
          <input id="search" type="search" value="${escapeHtml(state.search)}" placeholder="task, label, strategy, takeaway" />
        </label>
        <label>
          Task
          <select id="task-filter">${taskOptions}</select>
        </label>
        <label>
          Outcome
          <select id="outcome-filter">${outcomeOptions}</select>
        </label>
        <label>
          Engineer signal
          <select id="engineer-filter">${engineerOptions}</select>
        </label>
      </div>
      <div class="table-meta">
        Showing ${escapeHtml(start + 1)}-${escapeHtml(Math.min(start + state.pageSize, rows.length))}
        of ${escapeHtml(rows.length)} filtered rows.
      </div>
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>trace</th>${headers}</tr></thead>
          <tbody>${body || `<tr><td colspan="${visibleFields.length + 1}">No rows match the filters.</td></tr>`}</tbody>
        </table>
      </div>
      <div class="pager">
        <button data-page="prev" ${state.page <= 1 ? "disabled" : ""}>Previous</button>
        <span>Page ${escapeHtml(state.page)} / ${escapeHtml(pageCount)}</span>
        <button data-page="next" ${state.page >= pageCount ? "disabled" : ""}>Next</button>
      </div>
    </section>
  `;
}

function renderProposalMapping(snapshot: SnapshotDoc): string {
  return `
    <section class="section">
      <div class="section-head">
        <div>
          <p class="eyebrow dark">Evidence and claim ledger</p>
          <h2>What This Snapshot Can Support</h2>
        </div>
        <p class="section-note">
          Status is based on evidence present in this export, not on intended pipeline capability.
        </p>
      </div>
      <div class="mapping-grid">
        <article class="mapping-card warning">
          <h3>O1 localisation · not validated</h3>
          <p>${escapeHtml(snapshot.event_count)} events and role/order timelines are available, but only ${escapeHtml(snapshot.anchor_labeled_event_count)} events carry anchors. The heuristic first_failure_stage is not a validated first-anchor localisation.</p>
        </article>
        <article class="mapping-card warning">
          <h3>O2 taxonomy · exploratory</h3>
          <p>Detector outputs are inspectable, but independent gold labels and precision/recall/F1 are absent. Labels are signals to review, not confirmed diagnoses.</p>
        </article>
        <article class="mapping-card warning">
          <h3>O3 comparison · not evaluated</h3>
          <p>The slice contains one model, architecture, grounding setting, and stress level. It cannot support early-warning or configuration-superiority claims.</p>
        </article>
      </div>
      <div class="evidence-ledger">
        <div><span>Snapshot</span><strong>${escapeHtml(snapshot.snapshot_sha256)}</strong></div>
        <div><span>Analyzer snapshot</span><strong>${escapeHtml(snapshot.analysis_snapshot_sha256 ?? "not recorded")}</strong></div>
        <div><span>Anchor coverage</span><strong>${escapeHtml(snapshot.anchor_labeled_event_count)} / ${escapeHtml(snapshot.event_count)}</strong></div>
        <div><span>Kernel field</span><strong>${escapeHtml(snapshot.kernel.field ?? "not recorded")}: ${escapeHtml(countSummary(snapshot.kernel.counts))}</strong></div>
        <div><span>Kernel environment</span><strong>${escapeHtml(countSummary(snapshot.kernel_environment.counts))}</strong></div>
        <div><span>Review confidence</span><strong>${escapeHtml(countSummary(snapshot.confidence.counts))}</strong></div>
        <div><span>Timeline topology</span><strong>${escapeHtml(snapshot.topology.connectedLinear)} connected linear; ${escapeHtml(snapshot.topology.disconnected)} disconnected; ${escapeHtml(snapshot.topology.branching)} branching</strong></div>
        <div><span>Warehouse evidence used</span><strong>No matched Lean control. STARGAZER history is excluded from these counts; no architecture comparison is claimed.</strong></div>
      </div>
    </section>
  `;
}

function renderTaskTable(): string {
  const rows = taskSummaries(state.rows);
  const outcomeFields = uniqueValues(state.rows, "validator_outcome");
  const body = rows
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.taskId)}</td>
          <td>${escapeHtml(row.trials)}</td>
          ${outcomeFields.map((field) => `<td>${escapeHtml(row.outcomes[field] ?? 0)}</td>`).join("")}
          <td><span class="total-check ${row.outcomeTotal === row.trials ? "pass" : "fail"}">${escapeHtml(row.outcomeTotal)} / ${escapeHtml(row.trials)}</span></td>
          <td>${escapeHtml(row.dominantEngineerLabel)}</td>
          <td>${escapeHtml(row.dominantGlobalPattern)}</td>
        </tr>
      `,
    )
    .join("");
  return `
    <section class="section">
      <div class="section-head">
        <div>
          <p class="eyebrow dark">Per-task pattern table</p>
          <h2>10 Easy Tasks</h2>
        </div>
        <p class="section-note">Every outcome column is terminal and mutually exclusive. The total check must equal 10 for every task.</p>
      </div>
      <div class="table-wrap compact">
        <table class="data-table">
          <thead>
            <tr>
              <th>task_id</th>
              <th>trials</th>
              ${outcomeFields.map((field) => `<th>${escapeHtml(field)}</th>`).join("")}
              <th>outcome total</th>
              <th>provisional engineer signal</th>
              <th>provisional trace pattern</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </section>
  `;
}

function renderCountBlock(title: string, field: string): string {
  const entries = Array.from(countBy(state.rows, field).entries()).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...entries.map(([, value]) => value), 1);
  return `
    <article class="count-block">
      <h3>${escapeHtml(title)}</h3>
      <div class="bar-list">
        ${entries
          .map(
            ([label, value]) => `
              <div class="bar-row">
                <span>${escapeHtml(label)}</span>
                <strong>${escapeHtml(value)}</strong>
                <i style="--bar:${(value / max) * 100}%"></i>
              </div>
            `,
          )
          .join("")}
      </div>
    </article>
  `;
}

function renderTaxonomy(): string {
  return `
    <section class="section">
      <div class="section-head">
        <div>
          <p class="eyebrow dark">Outcome versus incident signals</p>
          <h2>Terminal State And Exploratory Labels</h2>
        </div>
        <p class="section-note">
          Final outcomes describe where a run ended. Legacy role/global labels may describe
          recovered incidents and are provisional until evidence review and detector validation.
        </p>
      </div>
      <div class="count-grid">
        ${renderCountBlock("Final validation outcome", "validator_outcome")}
        ${renderCountBlock("Reasoner signal", "reasoner_strategy_label")}
        ${renderCountBlock("Engineer incident signal", "engineer_failure_label")}
        ${renderCountBlock("Critic detector signal", "critic_label")}
        ${renderCountBlock("Global trace-pattern signal", "global_graph_pattern")}
      </div>
    </section>
  `;
}

function renderCase(taskId: string): string {
  const rows = state.rows.filter((row) => row.task_id === taskId);
  if (!rows.length) {
    return "";
  }
  const sample = rows[0];
  return `
    <article class="case-card">
      <h3>${escapeHtml(taskId)}</h3>
      <p>${escapeHtml(sample.math_question)}</p>
      <dl>
        <div><dt>Human strategy</dt><dd>${escapeHtml(sample.naive_human_strategy)}</dd></div>
        <div><dt>Domain LLM strategy</dt><dd>${escapeHtml(sample.domain_specific_LLM_strategy)}</dd></div>
        <div><dt>Provisional engineer signal</dt><dd>${escapeHtml(topLabel(rows, "engineer_failure_label"))}</dd></div>
        <div><dt>Provisional trace-pattern signal</dt><dd>${escapeHtml(topLabel(rows, "global_graph_pattern"))}</dd></div>
      </dl>
    </article>
  `;
}

function renderCaseStudies(): string {
  return `
    <section class="section">
      <div class="section-head">
        <div>
          <p class="eyebrow dark">Case studies</p>
          <h2>FATEM111, FATEM115, LeanCat001/002</h2>
        </div>
        <p class="section-note">These cases keep the math question, strategy, and observed agent path together.</p>
      </div>
      <div class="case-grid">
        ${["easy_fatem_111", "easy_fatem_115", "easy_leancat_001", "easy_leancat_002"]
          .map(renderCase)
          .join("")}
      </div>
    </section>
  `;
}

function renderReproducibility(snapshot: SnapshotDoc): string {
  return `
    <section class="section repro-section">
      <div class="section-head">
        <div>
          <p class="eyebrow dark">Reproducibility</p>
          <h2>Paths And Commands</h2>
        </div>
        <p class="section-note">Layout follows docs/REPO_LAYOUT_RULES.md.</p>
      </div>
      <div class="terminal-panel">
        <p><span>Raw traces</span> data/batch/version_1_trial_traces/*.jsonl</p>
        <p><span>Canonical CSV</span> data/analysis/lean_easy_failure_patterns.csv</p>
        <p><span>Report CSV copy</span> docs/lean_easy_failure_report/public/data/lean_easy_failure_patterns.csv</p>
        <p><span>Trace JSON copy</span> docs/lean_easy_failure_report/public/data/lean_easy_failure_traces.json</p>
        <p><span>Snapshot manifest</span> docs/lean_easy_failure_report/public/data/report_snapshot.json</p>
        <p><span>Snapshot SHA-256</span> ${escapeHtml(snapshot.snapshot_sha256)}</p>
        <p><span>Generate</span> python scripts/analyze_lean_easy_failures.py --input-dir data/batch/version_1_trial_traces --dataset-root dataset/Lean</p>
        <p><span>Build both exports</span> cd docs/lean_easy_failure_report && npm.cmd run build:mobile</p>
      </div>
    </section>
  `;
}

function render(): void {
  if (!app || !state.snapshot) {
    return;
  }
  const summary = summarize(state.rows);
  const rows = filteredRows();
  app.innerHTML = `
    ${renderHeader(summary, state.snapshot)}
    <main>
      <div class="source-strip">
        <span>Data: 100 raw JSONL = 100 CSV = 100 trace documents</span>
        <span>O1/O2: exploratory evidence, validation pending</span>
        <span>Outcome ≠ incident ≠ inferred cause</span>
      </div>
      ${renderLeanReader()}
      ${renderCsvExplorer(rows)}
      ${renderProposalMapping(state.snapshot)}
      ${renderTaskTable()}
      ${renderTaxonomy()}
      ${renderCaseStudies()}
      ${renderReproducibility(state.snapshot)}
    </main>
  `;
  bindEvents();
}

function bindEvents(): void {
  document.querySelector<HTMLInputElement>("#search")?.addEventListener("input", (event) => {
    state.search = (event.target as HTMLInputElement).value;
    state.page = 1;
    render();
  });
  document.querySelector<HTMLSelectElement>("#task-filter")?.addEventListener("change", (event) => {
    state.task = (event.target as HTMLSelectElement).value;
    state.selectedTrial = "";
    state.selectedNodeId = "";
    state.page = 1;
    render();
  });
  document.querySelector<HTMLSelectElement>("#reader-task")?.addEventListener("change", (event) => {
    state.task = (event.target as HTMLSelectElement).value;
    state.selectedTrial = "";
    state.selectedNodeId = "";
    state.page = 1;
    render();
  });
  document.querySelector<HTMLSelectElement>("#reader-trial")?.addEventListener("change", (event) => {
    state.selectedTrial = (event.target as HTMLSelectElement).value;
    state.selectedNodeId = "";
    render();
  });
  document.querySelector<HTMLSelectElement>("#outcome-filter")?.addEventListener("change", (event) => {
    state.outcome = (event.target as HTMLSelectElement).value;
    state.page = 1;
    render();
  });
  document.querySelector<HTMLSelectElement>("#engineer-filter")?.addEventListener("change", (event) => {
    state.engineer = (event.target as HTMLSelectElement).value;
    state.page = 1;
    render();
  });
  document.querySelectorAll<HTMLButtonElement>("[data-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      const field = button.dataset.sort || "task_id";
      if (state.sortField === field) {
        state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
      } else {
        state.sortField = field;
        state.sortDir = "asc";
      }
      render();
    });
  });
  document.querySelectorAll<HTMLButtonElement>("[data-page]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.page === "prev") {
        state.page = Math.max(1, state.page - 1);
      }
      if (button.dataset.page === "next") {
        state.page += 1;
      }
      render();
    });
  });
  document.querySelectorAll<SVGGElement>("[data-node-id]").forEach((node) => {
    node.addEventListener("click", () => {
      state.selectedNodeId = node.dataset.nodeId || "";
      render();
    });
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        state.selectedNodeId = node.dataset.nodeId || "";
        render();
      }
    });
  });
  document.querySelectorAll<HTMLButtonElement>("[data-open-trace]").forEach((button) => {
    button.addEventListener("click", () => {
      const trialId = button.dataset.openTrace || "";
      const trace = state.traces.find((item) => item.trial_id === trialId);
      state.selectedTrial = trialId;
      state.task = trace?.task_id ?? state.task;
      state.selectedNodeId = "";
      render();
      document.querySelector("#lean-reader")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

async function boot(): Promise<void> {
  if (!app) {
    return;
  }
  app.innerHTML = `<div class="loading">Loading CSV report data...</div>`;
  try {
    const embeddedCsv = document.querySelector<HTMLScriptElement>("#embedded-csv");
    const embeddedTraces = document.querySelector<HTMLScriptElement>("#embedded-traces");
    const embeddedSnapshot = document.querySelector<HTMLScriptElement>("#embedded-snapshot");
    const text = embeddedCsv?.textContent ?? await fetchCsv();
    const traceText = embeddedTraces?.textContent ?? await fetchTraces();
    const snapshotText = embeddedSnapshot?.textContent ?? await fetchSnapshot();
    state.rows = parseCsv(text);
    state.traces = JSON.parse(traceText) as TraceDoc[];
    state.snapshot = JSON.parse(snapshotText) as SnapshotDoc;
    state.fields = Object.keys(state.rows[0] ?? {});
    const csvIds = new Set(state.rows.map((row) => row.trial_id));
    const traceIds = new Set(state.traces.map((trace) => trace.trial_id));
    if (csvIds.size !== traceIds.size || [...csvIds].some((id) => !traceIds.has(id))) {
      throw new Error(
        `CSV/trace mismatch: ${csvIds.size} CSV rows vs ${traceIds.size} trace documents`,
      );
    }
    if (
      state.rows.length !== 100 ||
      state.traces.length !== 100 ||
      state.snapshot.trial_count !== 100 ||
      state.snapshot.task_count !== 10
    ) {
      throw new Error(
        `Expected one 100-trial / 10-task snapshot; found CSV=${state.rows.length}, traces=${state.traces.length}, manifest=${state.snapshot.trial_count}/${state.snapshot.task_count}`,
      );
    }
    for (const [taskId, count] of Object.entries(state.snapshot.per_task_counts)) {
      if (count !== 10) {
        throw new Error(`Task ${taskId} has ${count} trials; expected 10`);
      }
    }
    render();
  } catch (error) {
    app.innerHTML = `
      <div class="error-panel">
        <h1>Report data missing</h1>
        <p>${escapeHtml(error instanceof Error ? error.message : String(error))}</p>
        <code>python scripts/analyze_lean_easy_failures.py</code>
      </div>
    `;
  }
}

async function fetchCsv(): Promise<string> {
  const response = await fetch(DATA_URL);
  if (!response.ok) {
    throw new Error(`Failed to load ${DATA_URL}: ${response.status}`);
  }
  return response.text();
}

async function fetchTraces(): Promise<string> {
  const response = await fetch(TRACE_URL);
  if (!response.ok) {
    throw new Error(`Failed to load ${TRACE_URL}: ${response.status}`);
  }
  return response.text();
}

async function fetchSnapshot(): Promise<string> {
  const response = await fetch(SNAPSHOT_URL);
  if (!response.ok) {
    throw new Error(`Failed to load ${SNAPSHOT_URL}: ${response.status}`);
  }
  return response.text();
}

void boot();
