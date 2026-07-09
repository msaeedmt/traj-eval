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
};

type ToolCall = {
  seq: number;
  compiled: boolean | null;
  sorry_free: boolean | null;
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
  submitted_code: string | null;
  last_verified_code: string | null;
  submitted_eq_last_verified: boolean | null;
  declared_success: boolean;
  n_tool_calls: number;
  n_failed_compiles: number;
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
  headline: string;
  status: string;
  reasoner: string;
  engineer: string;
  critic: string;
  global: string;
  artifact: string;
  takeaway: string;
  evidence_seqs: Record<string, number[]>;
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
};

const CSV_VISIBLE_FIELDS = [
  "trial_id",
  "task_id",
  "validator_outcome",
  "reasoner_strategy_label",
  "engineer_failure_label",
  "critic_label",
  "global_graph_pattern",
  "first_failure_stage",
  "n_tool_calls",
  "n_failed_compiles",
];

function escapeHtml(value: unknown): string {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function cls(value: string): string {
  return value.replaceAll("_", "-").replaceAll("/", "-");
}

function option(value: string, label: string, selected: string): string {
  return `<option value="${escapeHtml(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
}

function filteredRows(): CsvRow[] {
  const query = state.search.trim().toLowerCase();
  const numericFields = new Set([
    "trial_number",
    "n_tool_calls",
    "n_failed_compiles",
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

function renderHeader(summary: ReportSummary): string {
  return `
    <header class="report-header">
      <div class="header-inner">
        <div class="header-copy">
          <p class="eyebrow">Proposal + MD grounded report</p>
          <h1>Lean Easy Failure Analysis</h1>
          <p class="header-subtitle">
            CSV-first analysis over existing Lean JSONL traces. The report follows
            README/NLP Lab objectives O1/O2/O3 and the local MD guides.
          </p>
        </div>
        <div class="header-panel">
          <div class="panel-title">Grounding</div>
          <div class="source-chip">Proposal: O1 localization</div>
          <div class="source-chip">Proposal: O2 taxonomy</div>
          <div class="source-chip muted">Proposal: O3 not claimed</div>
          <div class="source-chip">MD: LEAN_FAILURE_ANALYSIS_GUIDE.md</div>
          <div class="source-chip">MD: REPO_LAYOUT_RULES.md</div>
        </div>
      </div>
      <div class="stats-grid">
        ${renderStat("Trials", summary.trials, "CSV rows")}
        ${renderStat("Tasks", summary.tasks, "10 easy tasks expected")}
        ${renderStat("Trace verified", summary.traceVerified, "in-loop check_lean evidence")}
        ${renderStat("Silent failure", summary.silentFailure, "critic may approve but validator rejects")}
        ${renderStat("Unknown", summary.validationUnknown, "kernel fields are none")}
        ${renderStat("Critic false accept", summary.criticFalseAccept, "approval without validated proof")}
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
          <text x="8" y="${y + 4}">${escapeHtml(role)}</text>
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
      const label = `${node.seq} ${node.role} ${node.type}`;
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
      <svg class="trace-graph" viewBox="0 0 ${width} ${height}" role="img" aria-label="Causal trace graph">
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
        <div><dt>Role</dt><dd>${escapeHtml(node.role)}</dd></div>
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
  return `
    <section class="diagnosis-panel">
      <div class="diagnosis-head">
        <div>
          <p class="eyebrow dark">Deterministic trace diagnosis</p>
          <h3>${escapeHtml(d.headline)}</h3>
        </div>
        <span class="outcome-badge">${escapeHtml(d.status)}</span>
      </div>
      <div class="diagnosis-grid">
        <article><h4>Math question</h4><p>${escapeHtml(trace.informal)}</p></article>
        <article><h4>Human strategy</h4><p>${escapeHtml(row?.naive_human_strategy ?? "")}</p></article>
        <article><h4>Domain LLM strategy</h4><p>${escapeHtml(row?.domain_specific_LLM_strategy ?? "")}</p></article>
        <article><h4>Reasoner</h4><p>${escapeHtml(d.reasoner)}</p></article>
        <article><h4>Engineer</h4><p>${escapeHtml(d.engineer)}</p></article>
        <article><h4>Critic</h4><p>${escapeHtml(d.critic)}</p></article>
        <article><h4>Global</h4><p>${escapeHtml(d.global)}</p></article>
        <article><h4>Final artifact</h4><p>${escapeHtml(d.artifact)}</p></article>
      </div>
      <p class="diagnosis-takeaway">${escapeHtml(d.takeaway)}</p>
    </section>
  `;
}

function renderLeanReader(): string {
  const trace = selectedTrace();
  if (!trace) {
    return "";
  }
  const row = traceOutcome(trace);
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
          </summary>
          ${codeBlock(call.code)}
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
            <strong>${escapeHtml(step.role)}</strong>
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
          <h2>Causal Graph, Diagnosis, And Proof Evidence</h2>
        </div>
        <p class="section-note">
          Reads all 100 raw JSONL-derived traces. The graph is exported from build_graph.
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
            <div><dt>Nodes</dt><dd>${escapeHtml(trace.graph.nodes.length)}</dd></div>
            <div><dt>Edges</dt><dd>${escapeHtml(trace.graph.edges.length)}</dd></div>
            <div><dt>Tool calls</dt><dd>${escapeHtml(trace.n_tool_calls)}</dd></div>
            <div><dt>Failed compiles</dt><dd>${escapeHtml(trace.n_failed_compiles)}</dd></div>
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
            <div><dt>Declared success</dt><dd>${verdictPill(trace.declared_success)}</dd></div>
            <div><dt>Submitted equals last verified</dt><dd>${verdictPill(trace.submitted_eq_last_verified)}</dd></div>
          </dl>
          <h4>Formal Statement</h4>
          ${codeBlock(trace.formal_statement)}
          <h4>Submitted Code</h4>
          ${codeBlock(trace.submitted_code)}
          <h4>Last Verified Code</h4>
          ${codeBlock(trace.last_verified_code)}
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
    option("", "All engineer labels", state.engineer),
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
          Engineer
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

function renderProposalMapping(): string {
  return `
    <section class="section">
      <div class="section-head">
        <div>
          <p class="eyebrow dark">Proposal alignment</p>
          <h2>Research Question Mapping</h2>
        </div>
        <p class="section-note">
          Main conclusion: Lean kernel checking makes hidden trajectory failures visible.
        </p>
      </div>
      <div class="mapping-grid">
        <article class="mapping-card">
          <h3>O1 localization</h3>
          <p>Supported partially by trace graph construction, role attribution, and first_failure_stage.</p>
        </article>
        <article class="mapping-card">
          <h3>O2 taxonomy</h3>
          <p>Supported by deterministic labels over reasoner, engineer, critic, and global behavior.</p>
        </article>
        <article class="mapping-card warning">
          <h3>O3 early prediction</h3>
          <p>Not claimed in this slice. The data has 10 repeated trials per easy task, but no stress or difficulty progression.</p>
        </article>
      </div>
    </section>
  `;
}

function renderTaskTable(): string {
  const rows = taskSummaries(state.rows);
  const body = rows
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.taskId)}</td>
          <td>${escapeHtml(row.trials)}</td>
          <td>${escapeHtml(row.solved)}</td>
          <td>${escapeHtml(row.traceVerified)}</td>
          <td>${escapeHtml(row.silentFailure)}</td>
          <td>${escapeHtml(row.validationUnknown)}</td>
          <td>${escapeHtml(row.unsolved)}</td>
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
        <p class="section-note">Aggregated directly from the CSV rows.</p>
      </div>
      <div class="table-wrap compact">
        <table class="data-table">
          <thead>
            <tr>
              <th>task_id</th>
              <th>trials</th>
              <th>solved</th>
              <th>trace_verified</th>
              <th>silent_failure</th>
              <th>validation_unknown</th>
              <th>unsolved</th>
              <th>dominant_engineer_label</th>
              <th>dominant_global_pattern</th>
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
          <p class="eyebrow dark">MD taxonomy</p>
          <h2>Role-Level Failure Analysis</h2>
        </div>
        <p class="section-note">
          Labels follow docs/LEAN_FAILURE_ANALYSIS_GUIDE.md; no LLM post-hoc judgment is used.
        </p>
      </div>
      <div class="count-grid">
        ${renderCountBlock("Reasoner strategy", "reasoner_strategy_label")}
        ${renderCountBlock("Engineer failure", "engineer_failure_label")}
        ${renderCountBlock("Critic behavior", "critic_label")}
        ${renderCountBlock("Global graph pattern", "global_graph_pattern")}
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
        <div><dt>Dominant engineer label</dt><dd>${escapeHtml(topLabel(rows, "engineer_failure_label"))}</dd></div>
        <div><dt>Dominant global pattern</dt><dd>${escapeHtml(topLabel(rows, "global_graph_pattern"))}</dd></div>
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

function renderReproducibility(): string {
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
        <p><span>Raw traces</span> data/batch/*.jsonl</p>
        <p><span>Canonical CSV</span> data/analysis/lean_easy_failure_patterns.csv</p>
        <p><span>Report CSV copy</span> docs/lean_easy_failure_report/public/data/lean_easy_failure_patterns.csv</p>
        <p><span>Trace JSON copy</span> docs/lean_easy_failure_report/public/data/lean_easy_failure_traces.json</p>
        <p><span>Generate</span> python scripts/analyze_lean_easy_failures.py --input-dir data/batch --dataset-root dataset/Lean</p>
        <p><span>Build report</span> cd docs/lean_easy_failure_report && npm.cmd run build</p>
      </div>
    </section>
  `;
}

function render(): void {
  if (!app) {
    return;
  }
  const summary = summarize(state.rows);
  const rows = filteredRows();
  app.innerHTML = `
    ${renderHeader(summary)}
    <main>
      <div class="source-strip">
        <span>Data: 100 JSONL traces -> CSV rows</span>
        <span>Proposal: O1/O2 supported, O3 not claimed</span>
        <span>MD: failure guide + repo layout rules</span>
      </div>
      ${renderLeanReader()}
      ${renderCsvExplorer(rows)}
      ${renderProposalMapping()}
      ${renderTaskTable()}
      ${renderTaxonomy()}
      ${renderCaseStudies()}
      ${renderReproducibility()}
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
    const text = embeddedCsv?.textContent ?? await fetchCsv();
    const traceText = embeddedTraces?.textContent ?? await fetchTraces();
    state.rows = parseCsv(text);
    state.traces = JSON.parse(traceText) as TraceDoc[];
    state.fields = Object.keys(state.rows[0] ?? {});
    const csvIds = new Set(state.rows.map((row) => row.trial_id));
    const traceIds = new Set(state.traces.map((trace) => trace.trial_id));
    if (csvIds.size !== traceIds.size || [...csvIds].some((id) => !traceIds.has(id))) {
      throw new Error(
        `CSV/trace mismatch: ${csvIds.size} CSV rows vs ${traceIds.size} trace documents`,
      );
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

void boot();
