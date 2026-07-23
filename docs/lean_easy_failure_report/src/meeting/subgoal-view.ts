import {
  type DashboardEvent,
  type DashboardTrial,
  type SubgoalExtension,
  type SubgoalFrame,
  type SubgoalNode,
  type SubgoalTransition,
  compactText,
  escapeAttribute,
  escapeHtml,
  hasSubgoalCapability,
  routeHref,
  statusTone,
} from "./model";

function extensionFor(trial: DashboardTrial): SubgoalExtension | undefined {
  return hasSubgoalCapability(trial) ? trial.extensions?.subgoals ?? undefined : undefined;
}

function frameAt(extension: SubgoalExtension, seq: number): SubgoalFrame | undefined {
  return [...extension.frames]
    .filter((frame) => frame.seq <= seq)
    .sort((a, b) => b.seq - a.seq || b.version - a.version)[0];
}

function finalNodes(extension: SubgoalExtension): SubgoalNode[] {
  const latestFrame = [...extension.frames].sort(
    (a, b) => b.seq - a.seq || b.version - a.version,
  )[0];
  return latestFrame?.nodes?.length ? latestFrame.nodes : extension.nodes;
}

function nodeDepth(
  node: SubgoalNode,
  byId: Map<string, SubgoalNode>,
  cache: Map<string, number>,
  visiting: Set<string>,
): number {
  const known = cache.get(node.id);
  if (known != null) {
    return known;
  }
  if (visiting.has(node.id)) {
    return 0;
  }
  visiting.add(node.id);
  const dependencies = node.dependsOn
    .map((id) => byId.get(id))
    .filter((candidate): candidate is SubgoalNode => Boolean(candidate));
  const depth = dependencies.length
    ? 1 + Math.max(...dependencies.map((dependency) => nodeDepth(dependency, byId, cache, visiting)))
    : 0;
  visiting.delete(node.id);
  cache.set(node.id, depth);
  return depth;
}

function transitionForNode(
  extension: SubgoalExtension,
  nodeId: string,
  selectedSeq: number,
): SubgoalTransition | undefined {
  const transitions = extension.transitions
    .filter((transition) => transition.subgoalId === nodeId)
    .sort((a, b) => a.seq - b.seq);
  return (
    [...transitions].reverse().find((transition) => transition.seq <= selectedSeq) ??
    transitions[0]
  );
}

function renderSubgoalDag(
  trial: DashboardTrial,
  extension: SubgoalExtension,
  nodes: SubgoalNode[],
  selectedSeq: number,
  selectedSubgoal: string,
): string {
  if (!nodes.length) {
    return `<section class="empty-state"><p>No subgoal nodes existed at this event.</p></section>`;
  }
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const depthCache = new Map<string, number>();
  const grouped = new Map<number, SubgoalNode[]>();
  for (const node of nodes) {
    const depth = nodeDepth(node, byId, depthCache, new Set());
    const group = grouped.get(depth) ?? [];
    group.push(node);
    grouped.set(depth, group);
  }
  for (const group of grouped.values()) {
    group.sort((a, b) => a.id.localeCompare(b.id));
  }
  const nodeWidth = 174;
  const nodeHeight = 72;
  const columnGap = 76;
  const rowGap = 30;
  const left = 42;
  const top = 42;
  const maxDepth = Math.max(...grouped.keys());
  const maxRows = Math.max(...[...grouped.values()].map((group) => group.length));
  const width = Math.max(700, left * 2 + (maxDepth + 1) * nodeWidth + maxDepth * columnGap);
  const height = Math.max(230, top * 2 + maxRows * nodeHeight + (maxRows - 1) * rowGap);
  const positions = new Map<string, { x: number; y: number }>();
  for (const [depth, group] of grouped.entries()) {
    const columnHeight = group.length * nodeHeight + Math.max(0, group.length - 1) * rowGap;
    const columnTop = Math.max(top, (height - columnHeight) / 2);
    group.forEach((node, index) => {
      positions.set(node.id, {
        x: left + depth * (nodeWidth + columnGap),
        y: columnTop + index * (nodeHeight + rowGap),
      });
    });
  }
  const edges = nodes
    .flatMap((node) =>
      node.dependsOn.map((dependency) => {
        const source = positions.get(dependency);
        const target = positions.get(node.id);
        if (!source || !target) {
          return "";
        }
        const x1 = source.x + nodeWidth;
        const y1 = source.y + nodeHeight / 2;
        const x2 = target.x;
        const y2 = target.y + nodeHeight / 2;
        const bend = Math.max(22, (x2 - x1) / 2);
        return `<path class="subgoal-edge" d="M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}" marker-end="url(#subgoal-arrow)" />`;
      }),
    )
    .join("");
  const marks = nodes
    .map((node) => {
      const pos = positions.get(node.id);
      if (!pos) {
        return "";
      }
      const transition = transitionForNode(extension, node.id, selectedSeq);
      const eventSeq = transition?.seq ?? selectedSeq;
      const active = node.id === selectedSubgoal;
      const label = `${node.id}, ${node.status}, ${node.attempts} attempts. ${node.objective}`;
      return `
        <a
          class="subgoal-node status-${escapeAttribute(node.status)}${active ? " is-selected" : ""}"
          href="${escapeAttribute(routeHref(trial.trialId, eventSeq, "subgoals"))}"
          data-subgoal-select="${escapeAttribute(node.id)}"
          data-event-select="${escapeAttribute(eventSeq)}"
          aria-label="${escapeAttribute(label)}"
        >
          <rect x="${pos.x}" y="${pos.y}" width="${nodeWidth}" height="${nodeHeight}" rx="8"></rect>
          <text x="${pos.x + 14}" y="${pos.y + 23}">${escapeHtml(node.id)}</text>
          <text class="subgoal-status-text" x="${pos.x + 14}" y="${pos.y + 44}">${escapeHtml(node.status)}</text>
          <text class="subgoal-attempt-text" x="${pos.x + 14}" y="${pos.y + 61}">${escapeHtml(node.attempts)} attempt${node.attempts === 1 ? "" : "s"}</text>
          <title>${escapeHtml(label)}</title>
        </a>
      `;
    })
    .join("");

  return `
    <div class="svg-scroller subgoal-scroller">
      <svg
        class="subgoal-graph"
        viewBox="0 0 ${width} ${height}"
        width="${width}"
        height="${height}"
        role="img"
        aria-labelledby="subgoal-graph-title subgoal-graph-description"
      >
        <title id="subgoal-graph-title">Subgoal dependency graph at event ${escapeHtml(selectedSeq)}</title>
        <desc id="subgoal-graph-description">Arrows mean depends-on. Each node shows its ledger status and attempt count at the selected event.</desc>
        <defs>
          <marker id="subgoal-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 8 4 L 0 8 z"></path>
          </marker>
        </defs>
        <g>${edges}</g>
        <g>${marks}</g>
      </svg>
    </div>
  `;
}

function renderProgress(
  extension: SubgoalExtension,
  frame: SubgoalFrame | undefined,
): string {
  const nodes = frame?.nodes ?? [];
  const final = finalNodes(extension);
  const defined = Math.max(nodes.length, final.length);
  const accepted = nodes.filter((node) => node.status === "accepted").length;
  const attempted = nodes.filter((node) => node.attempts > 0).length;
  const active = nodes.filter((node) => node.status === "active").length;
  const blocked = nodes.filter((node) => node.status === "blocked").length;
  const candidate = nodes.filter((node) => node.status === "candidate").length;
  return `
    <section class="subgoal-progress" aria-labelledby="subgoal-progress-heading">
      <div class="panel-heading compact">
        <div>
          <p class="kicker">Controller state at the selected event</p>
          <h3 id="subgoal-progress-heading">Subgoal progress</h3>
        </div>
        <span>ledger state, not percent proved</span>
      </div>
      <div class="progress-metrics">
        <div><span>Ledger accepted</span><strong>${accepted}/${defined || 0}</strong></div>
        <div><span>Attempted</span><strong>${attempted}/${defined || 0}</strong></div>
        <div><span>Active / candidate</span><strong>${active} / ${candidate}</strong></div>
        <div><span>Blocked</span><strong>${blocked}</strong></div>
        <div><span>Forced recoveries</span><strong>${frame?.forcedRecoveries ?? 0}</strong></div>
        <div><span>Strategy revisions</span><strong>${frame?.strategyRevisions ?? 0}</strong></div>
      </div>
      <div class="ledger-bar" role="img" aria-label="${accepted} of ${defined} subgoal nodes ledger accepted">
        <span style="width: ${defined ? Math.max(0, Math.min(100, (accepted / defined) * 100)) : 0}%"></span>
      </div>
    </section>
  `;
}

function renderNodeDetail(
  node: SubgoalNode | undefined,
  extension: SubgoalExtension,
  trial: DashboardTrial,
  selectedSeq: number,
): string {
  if (!node) {
    return `<section class="empty-state"><p>Select a subgoal to inspect its objective and history.</p></section>`;
  }
  const transitions = extension.transitions
    .filter((transition) => transition.subgoalId === node.id)
    .sort((a, b) => a.seq - b.seq);
  return `
    <article class="subgoal-detail" data-selected-subgoal-detail="${escapeAttribute(node.id)}">
      <header class="event-inspector-head">
        <div>
          <p class="kicker">Selected subgoal</p>
          <h3>${escapeHtml(node.id)}</h3>
        </div>
        <span class="status-pill tone-${statusTone(node.status)}">${escapeHtml(node.status)}</span>
      </header>
      <p class="subgoal-objective">${escapeHtml(node.objective)}</p>
      <dl class="fact-row">
        <div><dt>Depends on</dt><dd>${node.dependsOn.length ? node.dependsOn.map((id) => `<code>${escapeHtml(id)}</code>`).join(" ") : "root node"}</dd></div>
        <div><dt>Total attempts</dt><dd>${escapeHtml(node.attempts)}</dd></div>
        <div><dt>Consecutive failures</dt><dd>${escapeHtml(node.consecutiveFailures)}</dd></div>
        ${node.candidateHash ? `<div><dt>Candidate hash</dt><dd><code>${escapeHtml(node.candidateHash)}</code></dd></div>` : ""}
        ${node.acceptedHash ? `<div><dt>Accepted hash</dt><dd><code>${escapeHtml(node.acceptedHash)}</code></dd></div>` : ""}
      </dl>
      ${node.feedback ? `<section class="feedback-block"><h4>Critic feedback</h4><p>${escapeHtml(node.feedback)}</p></section>` : ""}
      ${
        node.failures.length
          ? `<section class="failure-notes"><h4>Recorded failures</h4><ol>${node.failures.map((failure) => `<li>${escapeHtml(failure)}</li>`).join("")}</ol></section>`
          : ""
      }
      <section class="transition-history">
        <h4>Status history</h4>
        ${
          transitions.length
            ? `<ol>${transitions
                .map((transition) => {
                  const active = transition.seq === selectedSeq;
                  const status = [transition.fromStatus, transition.toStatus].filter(Boolean).join(" -> ") || transition.kind;
                  return `
                    <li>
                      <a
                        class="transition-row${active ? " is-selected" : ""}"
                        href="${escapeAttribute(routeHref(trial.trialId, transition.seq, "subgoals"))}"
                        data-event-select="${escapeAttribute(transition.seq)}"
                        aria-current="${active ? "true" : "false"}"
                      >
                        <span>#${escapeHtml(transition.seq)}</span>
                        <strong>${escapeHtml(transition.kind)}</strong>
                        <span>${escapeHtml(status)}</span>
                        ${transition.detail ? `<small>${escapeHtml(compactText(transition.detail, 120))}</small>` : ""}
                      </a>
                    </li>
                  `;
                })
                .join("")}</ol>`
            : `<p>No lifecycle transition was reconstructed for this node.</p>`
        }
      </section>
    </article>
  `;
}

export function renderSubgoalView(
  trial: DashboardTrial,
  selectedEvent: DashboardEvent | undefined,
  selectedSubgoal: string,
): string {
  const extension = extensionFor(trial);
  if (!extension) {
    return `<section class="empty-state" data-view-panel="subgoals"><p>This trace does not expose the subgoal capability.</p></section>`;
  }
  const selectedSeq = selectedEvent?.seq ?? trial.events.at(-1)?.seq ?? 0;
  const frame = frameAt(extension, selectedSeq);
  const nodes = frame?.nodes ?? [];
  const selectedNode =
    nodes.find((node) => node.id === selectedSubgoal) ??
    nodes.find((node) => node.id === frame?.activeSubgoal) ??
    nodes[0];
  const replay = extension.replayValidation;
  return `
    <div class="subgoal-workbench" data-view-panel="subgoals" data-replay-status="${escapeAttribute(replay.status)}">
      ${renderProgress(extension, frame)}
      <section class="subgoal-map" aria-labelledby="subgoal-map-heading">
        <div class="panel-heading">
          <div>
            <p class="kicker">Arrows mean depends_on</p>
            <h3 id="subgoal-map-heading">Subgoal DAG</h3>
          </div>
          <span>${frame ? `frame v${escapeHtml(frame.version)} at #${escapeHtml(frame.seq)}` : `no ledger frame by #${escapeHtml(selectedSeq)}`}</span>
        </div>
        ${renderSubgoalDag(trial, extension, nodes, selectedSeq, selectedNode?.id ?? "")}
        <div class="replay-line">
          <span class="status-pill tone-${statusTone(replay.status)}">Replay ${escapeHtml(replay.status)}</span>
          ${
            replay.status === "gap"
              ? `<span>Expected version ${escapeHtml(replay.expectedVersion ?? "?")}; observed ${escapeHtml(replay.observedVersion ?? "?")}. No missing state is interpolated.</span>`
              : `<span>Terminal replay validation: ${escapeHtml(replay.status)}.</span>`
          }
        </div>
      </section>
      ${renderNodeDetail(selectedNode, extension, trial, selectedSeq)}
    </div>
  `;
}
