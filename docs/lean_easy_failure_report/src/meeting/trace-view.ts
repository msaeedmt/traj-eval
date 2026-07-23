import {
  type CompilerCheck,
  type DashboardEvent,
  type DashboardTrial,
  type GraphEdge,
  type GraphNode,
  type ViewId,
  compactText,
  escapeAttribute,
  escapeHtml,
  evidenceLabelsForEvent,
  exactJsonLine,
  formatTimestamp,
  prettyJson,
  rawRecordForEvent,
  routeHref,
  statusTone,
} from "./model";

const ROLE_ORDER = ["system", "planner", "reasoner", "engineer", "executor", "critic"];

function eventLabel(event: DashboardEvent): string {
  return event.text || event.phase || `${event.role} ${event.kind}`;
}

function eventHref(trial: DashboardTrial, event: DashboardEvent, view: ViewId): string {
  return routeHref(trial.trialId, event.seq, view);
}

function renderEvidenceLabels(trial: DashboardTrial, event: DashboardEvent): string {
  const labels = evidenceLabelsForEvent(trial, event.seq);
  if (labels.length === 0) {
    return "";
  }
  return `
    <div class="event-evidence" aria-label="Classification evidence">
      ${labels
        .map((label) => `<span class="evidence-label">Evidence: ${escapeHtml(label)}</span>`)
        .join("")}
    </div>
  `;
}

function renderEventDetail(trial: DashboardTrial, event: DashboardEvent | undefined): string {
  if (!event) {
    return `<section class="event-inspector empty-state"><p>No event is available for this trace.</p></section>`;
  }
  const raw = rawRecordForEvent(trial, event);
  const parents = event.causedBy ?? [];
  const toolPayload = [...(event.toolCalls ?? []), ...(event.toolResponses ?? [])];
  return `
    <article class="event-inspector" data-selected-event-detail="${escapeAttribute(event.seq)}">
      <header class="event-inspector-head">
        <div>
          <p class="kicker">Selected event</p>
          <h3>#${escapeHtml(event.seq)} | ${escapeHtml(event.role)} | ${escapeHtml(event.kind)}</h3>
        </div>
        <span class="event-time">${escapeHtml(formatTimestamp(event.timestamp))}</span>
      </header>
      ${renderEvidenceLabels(trial, event)}
      <p class="event-copy">${escapeHtml(eventLabel(event) || "No text was recorded for this event.")}</p>
      <dl class="fact-row">
        <div><dt>Event ID</dt><dd><code>${escapeHtml(event.eventId)}</code></dd></div>
        <div><dt>Caused by</dt><dd>${parents.length ? parents.map((id) => `<code>${escapeHtml(id)}</code>`).join(" ") : "root event"}</dd></div>
        ${event.phase ? `<div><dt>Phase</dt><dd>${escapeHtml(event.phase)}</dd></div>` : ""}
        ${raw ? `<div><dt>Raw line</dt><dd>${escapeHtml(raw.lineNumber)}</dd></div>` : ""}
      </dl>
      ${
        toolPayload.length
          ? `<details class="payload-disclosure"><summary>Tool payload (${toolPayload.length})</summary><pre><code>${escapeHtml(prettyJson(toolPayload))}</code></pre></details>`
          : ""
      }
      ${
        raw
          ? `<details class="payload-disclosure"><summary>Exact sanitized event record</summary><pre><code>${escapeHtml(prettyJson(raw.value))}</code></pre></details>`
          : ""
      }
    </article>
  `;
}

function isDecisiveEvent(
  trial: DashboardTrial,
  event: DashboardEvent,
  selected: DashboardEvent | undefined,
): boolean {
  if (selected?.eventId === event.eventId) {
    return true;
  }
  const check = checkAtSeq(trial, event.seq);
  const compilerResultRecorded = check?.compiled != null;
  if (compilerResultRecorded && check.compiled === false) {
    return true;
  }
  const exactAcceptanceSeqs = trial.checks
    .filter((candidate) => {
      const statementMatch = candidate.statementMatch?.toLowerCase().replaceAll("-", "_") ?? "";
      return (
        candidate.compiled === true &&
        candidate.sorryFree !== false &&
        (candidate.matched === true || statementMatch.includes("exact"))
      );
    })
    .map((candidate) => candidate.resultSeq ?? candidate.callSeq);
  const terminalExactAcceptance = exactAcceptanceSeqs.length
    ? Math.max(...exactAcceptanceSeqs)
    : null;
  if (terminalExactAcceptance === event.seq) {
    return true;
  }
  if (event.role.toLowerCase() === "critic") {
    return true;
  }
  const decisiveEvidence = evidenceLabelsForEvent(trial, event.seq).some((label) =>
    /primary.*failure|recovered.*failure|failure mode|recovery|terminal.*accept/i.test(label),
  );
  if (decisiveEvidence) {
    return true;
  }
  const text = `${event.kind} ${event.phase ?? ""} ${event.text ?? ""}`.toLowerCase();
  return /\b(accepted|rejected|blocked|recovery|recovered|revision|revised|repair)\b/.test(text);
}

function renderEventDisclosureBody(trial: DashboardTrial, event: DashboardEvent): string {
  const raw = rawRecordForEvent(trial, event);
  const parents = event.causedBy ?? [];
  const check = checkAtSeq(trial, event.seq);
  const toolPayload = [...(event.toolCalls ?? []), ...(event.toolResponses ?? [])];
  return `
    <div class="event-disclosure-body">
      ${renderEvidenceLabels(trial, event)}
      <p class="event-full-copy">${escapeHtml(eventLabel(event) || "No text was recorded for this event.")}</p>
      <dl class="event-disclosure-facts">
        <div><dt>Parents</dt><dd>${parents.length ? parents.map((parent) => `<code>${escapeHtml(parent)}</code>`).join(" ") : "root event"}</dd></div>
        ${event.phase ? `<div><dt>Phase</dt><dd>${escapeHtml(event.phase)}</dd></div>` : ""}
        ${raw ? `<div><dt>Raw line</dt><dd>${escapeHtml(raw.lineNumber)}</dd></div>` : ""}
      </dl>
      ${check?.code ? `<section class="inline-code-block"><h4>Lean candidate</h4><pre><code>${escapeHtml(check.code)}</code></pre></section>` : ""}
      ${toolPayload.length ? `<section class="inline-payload"><h4>Tool payload</h4><pre><code>${escapeHtml(prettyJson(toolPayload))}</code></pre></section>` : ""}
      ${raw ? `<section class="inline-payload"><h4>Exact sanitized event record</h4><pre><code>${escapeHtml(prettyJson(raw.value))}</code></pre></section>` : ""}
      <a class="open-event-link" href="${escapeAttribute(eventHref(trial, event, "trace"))}" data-event-select="${escapeAttribute(event.seq)}">Open selected event</a>
    </div>
  `;
}

export function renderTraceTimeline(
  trial: DashboardTrial,
  selected: DashboardEvent | undefined,
): string {
  const events = [...trial.events].sort((a, b) => a.seq - b.seq);
  return `
    <div class="trace-workbench" data-view-panel="trace">
      <section class="event-timeline" aria-labelledby="timeline-heading">
        <div class="panel-heading">
          <div>
            <p class="kicker">Full recorded order</p>
            <h3 id="timeline-heading">Trace events</h3>
          </div>
          <span>${escapeHtml(events.length)} events</span>
        </div>
        <ol class="event-list">
          ${events
            .map((event) => {
              const active = selected?.eventId === event.eventId;
              const evidence = evidenceLabelsForEvent(trial, event.seq);
              const open = isDecisiveEvent(trial, event, selected);
              return `
                <li class="event-list-item${active ? " is-selected" : ""}">
                  <details class="event-disclosure role-${escapeAttribute(event.role)}" data-event-disclosure data-event-decisive="${open ? "true" : "false"}" data-event-seq="${escapeAttribute(event.seq)}" ${open ? "open" : ""}>
                    <summary class="event-row role-${escapeAttribute(event.role)}${active ? " is-selected" : ""}" aria-current="${active ? "true" : "false"}">
                      <span class="event-seq">#${escapeHtml(event.seq)}</span>
                      <span class="event-row-body">
                        <span class="event-row-meta"><strong>${escapeHtml(event.role)}</strong> ${escapeHtml(event.kind)}${event.phase ? ` | ${escapeHtml(event.phase)}` : ""}</span>
                        <span class="event-row-copy">${escapeHtml(compactText(eventLabel(event), 150) || "No text recorded")}</span>
                      </span>
                      ${evidence.length ? `<span class="evidence-dot" aria-label="Classification evidence"></span>` : ""}
                    </summary>
                    ${renderEventDisclosureBody(trial, event)}
                  </details>
                </li>
              `;
            })
            .join("")}
        </ol>
      </section>
      ${renderEventDetail(trial, selected)}
    </div>
  `;
}

function graphData(trial: DashboardTrial): { nodes: GraphNode[]; edges: GraphEdge[] } {
  if (trial.graph?.nodes?.length) {
    return {
      nodes: [...trial.graph.nodes].sort((a, b) => a.seq - b.seq),
      edges: trial.graph.edges ?? [],
    };
  }
  return {
    nodes: trial.events.map((event) => ({
      id: event.eventId,
      eventId: event.eventId,
      seq: event.seq,
      role: event.role,
      kind: event.kind,
      label: eventLabel(event),
    })),
    edges: trial.events.flatMap((event) =>
      event.causedBy.map((source) => ({ source, target: event.eventId })),
    ),
  };
}

function checkAtSeq(trial: DashboardTrial, seq: number): CompilerCheck | undefined {
  return trial.checks.find((check) => check.resultSeq === seq || check.callSeq === seq);
}

function nodeTone(trial: DashboardTrial, node: GraphNode): string {
  const check = checkAtSeq(trial, node.seq);
  if (check?.compiled === false) {
    return "fail";
  }
  if (check?.compiled === true) {
    return "pass";
  }
  if (evidenceLabelsForEvent(trial, node.seq).length > 0) {
    return "evidence";
  }
  return "neutral";
}

export function renderRoleGraph(
  trial: DashboardTrial,
  selected: DashboardEvent | undefined,
): string {
  const graph = graphData(trial);
  if (!graph.nodes.length) {
    return `<section class="empty-state" data-view-panel="graph"><p>No role graph was recorded.</p></section>`;
  }
  const presentRoles = new Set(graph.nodes.map((node) => node.role));
  const roles = [
    ...ROLE_ORDER.filter((role) => presentRoles.has(role)),
    ...[...presentRoles].filter((role) => !ROLE_ORDER.includes(role)).sort(),
  ];
  const laneGap = 74;
  const top = 54;
  const left = 112;
  const step = Math.max(48, Math.min(72, 920 / Math.max(1, graph.nodes.length - 1)));
  const width = Math.max(820, left + graph.nodes.length * step + 80);
  const height = Math.max(260, top + roles.length * laneGap + 38);
  const roleIndex = new Map(roles.map((role, index) => [role, index]));
  const positions = new Map<string, { x: number; y: number }>();
  graph.nodes.forEach((node, index) => {
    positions.set(node.id, {
      x: left + index * step,
      y: top + (roleIndex.get(node.role) ?? roles.length) * laneGap,
    });
    positions.set(node.eventId, {
      x: left + index * step,
      y: top + (roleIndex.get(node.role) ?? roles.length) * laneGap,
    });
  });
  const edges = graph.edges
    .map((edge) => {
      const source = positions.get(edge.source);
      const target = positions.get(edge.target);
      if (!source || !target) {
        return "";
      }
      return `<line class="role-edge" x1="${source.x}" y1="${source.y}" x2="${target.x}" y2="${target.y}" marker-end="url(#role-arrow)" />`;
    })
    .join("");
  const lanes = roles
    .map((role, index) => {
      const y = top + index * laneGap;
      return `
        <g class="role-lane">
          <text x="10" y="${y + 5}">${escapeHtml(role)}</text>
          <line x1="100" y1="${y}" x2="${width - 30}" y2="${y}" />
        </g>
      `;
    })
    .join("");
  const nodes = graph.nodes
    .map((node) => {
      const pos = positions.get(node.id);
      if (!pos) {
        return "";
      }
      const active = selected?.seq === node.seq;
      const label = `Event ${node.seq}, ${node.role}, ${node.kind}. ${compactText(node.label, 100)}`;
      return `
        <a
          href="${escapeAttribute(routeHref(trial.trialId, node.seq, "graph"))}"
          class="role-node tone-${nodeTone(trial, node)}${active ? " is-selected" : ""}"
          data-event-select="${escapeAttribute(node.seq)}"
          aria-label="${escapeAttribute(label)}"
        >
          <circle cx="${pos.x}" cy="${pos.y}" r="${active ? 17 : 14}"></circle>
          <text x="${pos.x}" y="${pos.y + 4}" text-anchor="middle">${escapeHtml(node.seq)}</text>
          <title>${escapeHtml(label)}</title>
        </a>
      `;
    })
    .join("");

  return `
    <div class="graph-workbench" data-view-panel="graph">
      <section class="graph-panel" aria-labelledby="role-graph-heading">
        <div class="panel-heading">
          <div>
            <p class="kicker">Edges mean caused_by</p>
            <h3 id="role-graph-heading">Role graph</h3>
          </div>
          <span>${escapeHtml(graph.nodes.length)} nodes | ${escapeHtml(graph.edges.length)} edges</span>
        </div>
        <div class="svg-scroller">
          <svg
            class="role-graph"
            viewBox="0 0 ${width} ${height}"
            width="${width}"
            height="${height}"
            role="img"
            aria-labelledby="role-graph-title role-graph-description"
          >
            <title id="role-graph-title">Agent-role event graph for ${escapeHtml(trial.trialId)}</title>
            <desc id="role-graph-description">Events are ordered from left to right on agent-role lanes. Lines preserve recorded caused-by relationships.</desc>
            <defs>
              <marker id="role-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M 0 0 L 8 4 L 0 8 z"></path>
              </marker>
            </defs>
            ${lanes}
            <g>${edges}</g>
            <g>${nodes}</g>
          </svg>
        </div>
        <p class="graph-legend"><span class="legend-mark tone-fail"></span> failed compiler result <span class="legend-mark tone-pass"></span> successful compiler result <span class="legend-mark tone-evidence"></span> classification evidence</p>
      </section>
      ${renderEventDetail(trial, selected)}
    </div>
  `;
}

function checkResultLabel(check: CompilerCheck): string {
  if (check.compiled === false) {
    return "failed";
  }
  if (check.compiled === true && check.sorryFree === false) {
    return "compiled with sorry";
  }
  if (check.compiled === true) {
    return "compiled";
  }
  return check.verificationStatus || "unknown";
}

function renderCheckDetail(check: CompilerCheck | undefined): string {
  if (!check) {
    return `<section class="check-detail empty-state"><p>Select a compiler check to inspect its exact code and diagnostic.</p></section>`;
  }
  return `
    <article class="check-detail" data-selected-check="${escapeAttribute(check.callId || check.callSeq)}">
      <header class="event-inspector-head">
        <div>
          <p class="kicker">Selected compiler evidence</p>
          <h3>Call #${escapeHtml(check.callSeq)}${check.resultSeq != null ? ` -> result #${escapeHtml(check.resultSeq)}` : ""}</h3>
        </div>
        <span class="status-pill tone-${statusTone(checkResultLabel(check))}">${escapeHtml(checkResultLabel(check))}</span>
      </header>
      <dl class="fact-row">
        <div><dt>Purpose</dt><dd>${escapeHtml(check.purpose || "not recorded")}</dd></div>
        <div><dt>Subgoal</dt><dd>${escapeHtml(check.subgoalId || "not scoped")}</dd></div>
        <div><dt>Statement match</dt><dd>${escapeHtml(check.statementMatch || "unknown")}</dd></div>
        <div><dt>Candidate kind</dt><dd>${escapeHtml(check.candidateKind || "unknown")}</dd></div>
        <div><dt>Sorry-free</dt><dd>${check.sorryFree == null ? "unknown" : escapeHtml(check.sorryFree)}</dd></div>
        <div><dt>Matched call/result</dt><dd>${check.matched == null ? "unknown" : escapeHtml(check.matched)}</dd></div>
      </dl>
      ${check.diagnostic ? `<section class="diagnostic-block"><h4>Diagnostic</h4><pre><code>${escapeHtml(check.diagnostic)}</code></pre></section>` : ""}
      ${check.code ? `<section class="code-block"><h4>Lean candidate</h4><pre><code>${escapeHtml(check.code)}</code></pre></section>` : ""}
      ${check.evidenceHash ? `<p class="hash-line"><span>Evidence hash</span><code>${escapeHtml(check.evidenceHash)}</code></p>` : ""}
    </article>
  `;
}

export function renderChecksView(
  trial: DashboardTrial,
  selected: DashboardEvent | undefined,
): string {
  const checks = [...trial.checks].sort((a, b) => a.callSeq - b.callSeq);
  const selectedCheck = checks.find(
    (check) => selected && (check.callSeq === selected.seq || check.resultSeq === selected.seq),
  ) ?? checks.at(-1);
  return `
    <div class="checks-workbench" data-view-panel="checks">
      <section class="checks-list" aria-labelledby="checks-heading">
        <div class="panel-heading">
          <div>
            <p class="kicker">Compiler and verifier calls</p>
            <h3 id="checks-heading">Checks</h3>
          </div>
          <span>${escapeHtml(checks.length)} calls</span>
        </div>
        <div class="check-rows">
          ${
            checks.length
              ? checks
                  .map((check) => {
                    const seq = check.resultSeq ?? check.callSeq;
                    const active = selectedCheck === check;
                    const result = checkResultLabel(check);
                    return `
                      <a
                        class="check-row${active ? " is-selected" : ""}"
                        href="${escapeAttribute(routeHref(trial.trialId, seq, "checks"))}"
                        data-event-select="${escapeAttribute(seq)}"
                        aria-current="${active ? "true" : "false"}"
                      >
                        <span class="check-sequence">#${escapeHtml(check.callSeq)}${check.resultSeq != null ? `->#${escapeHtml(check.resultSeq)}` : ""}</span>
                        <span class="check-main">
                          <strong>${escapeHtml(check.tool || "check")}</strong>
                          <span>${escapeHtml(check.purpose || check.candidateKind || "candidate")}${check.subgoalId ? ` | ${escapeHtml(check.subgoalId)}` : ""}</span>
                        </span>
                        <span class="status-pill tone-${statusTone(result)}">${escapeHtml(result)}</span>
                      </a>
                    `;
                  })
                  .join("")
              : `<p class="empty-list">No compiler checks were recorded in this trace.</p>`
          }
        </div>
      </section>
      ${renderCheckDetail(selectedCheck)}
    </div>
  `;
}

export function renderJsonlView(
  trial: DashboardTrial,
  selected: DashboardEvent | undefined,
): string {
  const selectedIndex = selected?.rawRecordIndex ?? -1;
  const eventByRawIndex = new Map(
    trial.events.map((event) => [event.rawRecordIndex, event] as const),
  );
  return `
    <section class="jsonl-panel" data-view-panel="jsonl" aria-labelledby="jsonl-heading">
      <div class="panel-heading">
        <div>
          <p class="kicker">Source-faithful sanitized records</p>
          <h3 id="jsonl-heading">Exact JSONL</h3>
        </div>
        <span>${escapeHtml(trial.rawRecords.length)} lines</span>
      </div>
      <p class="panel-note">One parsed source record per line. Only private absolute paths and temporary Lean filenames are normalized by the build pipeline.</p>
      <ol class="json-lines">
        ${trial.rawRecords
          .map((record, index) => {
            const event = eventByRawIndex.get(index);
            const selectedLine = index === selectedIndex;
            const content = `<span class="json-line-number">${escapeHtml(record.lineNumber)}</span><code>${escapeHtml(exactJsonLine(record))}</code>`;
            return `
              <li class="json-line${selectedLine ? " is-selected" : ""}" data-raw-record-index="${index}">
                ${
                  event
                    ? `<a href="${escapeAttribute(eventHref(trial, event, "jsonl"))}" data-event-select="${escapeAttribute(event.seq)}" aria-current="${selectedLine ? "true" : "false"}">${content}</a>`
                    : `<div>${content}</div>`
                }
              </li>
            `;
          })
          .join("")}
      </ol>
    </section>
  `;
}

export function renderTraceView(
  view: Exclude<ViewId, "subgoals">,
  trial: DashboardTrial,
  selected: DashboardEvent | undefined,
): string {
  if (view === "graph") {
    return renderRoleGraph(trial, selected);
  }
  if (view === "checks") {
    return renderChecksView(trial, selected);
  }
  if (view === "jsonl") {
    return renderJsonlView(trial, selected);
  }
  return renderTraceTimeline(trial, selected);
}
