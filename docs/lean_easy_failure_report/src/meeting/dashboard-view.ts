import {
  type ClassificationAssignment,
  type DashboardBundle,
  type DashboardEvent,
  type DashboardState,
  type DashboardTrial,
  type NavigationGroup,
  type NavigationSection,
  type SuccessIndexEntry,
  type TaxonomyCategory,
  type ViewId,
  assignmentLabel,
  availableViews,
  escapeAttribute,
  escapeHtml,
  groupForTrial,
  hasSubgoalCapability,
  isOneShotTrial,
  isRecoveryTrial,
  navigationSections,
  normalizeView,
  primaryModeLabel,
  recoveryFailureCount,
  recoveryRegressionNote,
  recoveryStages,
  routeHref,
  sectionForTrial,
  selectedEvent,
  statusTone,
  trialHeadline,
  trialOutcomeLabel,
} from "./model";
import { renderSubgoalView } from "./subgoal-view";
import { renderTraceView } from "./trace-view";

const VIEW_LABELS: Record<ViewId, string> = {
  trace: "Trace",
  graph: "Role graph",
  checks: "Checks",
  jsonl: "Exact JSONL",
  subgoals: "Subgoals",
};

function renderAssignmentBadge(
  assignment: ClassificationAssignment | undefined,
  kind: string,
): string {
  if (!assignment) {
    return "";
  }
  const label = assignmentLabel(assignment);
  if (!label) {
    return "";
  }
  return `<span class="classification-badge kind-${escapeAttribute(kind)}" data-axis-id="${escapeAttribute(assignment.axisId)}" data-category-id="${escapeAttribute(assignment.categoryId)}">${escapeHtml(label)}</span>`;
}

function renderTrialBadges(trial: DashboardTrial): string {
  const c = trial.classifications ?? {};
  if (isRecoveryTrial(trial)) {
    return `
      <div class="classification-row recovery-header-labels" aria-label="Recovery classification">
        <span class="classification-badge kind-success">Recovery success</span>
        <span class="classification-badge kind-context">${escapeHtml(trial.taskId)} | ${escapeHtml(trial.source || "source not recorded")}</span>
        <span class="classification-badge kind-success">Kernel-confirmed exact target</span>
      </div>
    `;
  }
  if (hasSubgoalCapability(trial)) {
    return `
      <div class="classification-row" aria-label="Medium trial classification">
        ${renderAssignmentBadge(c.failureBehavior ?? c.failureMode, "behavior")}
        ${renderAssignmentBadge(c.progressStage, "progress")}
      </div>
    `;
  }
  return `
    <div class="classification-row" aria-label="Trial classifications">
      ${renderAssignmentBadge(c.outcome, "outcome")}
      ${renderAssignmentBadge(c.successPattern, "success")}
      ${renderAssignmentBadge(c.failureMode, "failure")}
      ${renderAssignmentBadge(c.progressStage, "progress")}
      ${renderAssignmentBadge(c.failureBehavior, "behavior")}
      ${(c.auditFlags ?? []).map((flag) => renderAssignmentBadge(flag, "audit")).join("")}
    </div>
  `;
}

function trialSearchText(trial: DashboardTrial): string {
  const formalContext = trial.events
    .slice(0, 4)
    .map((event) => event.text ?? "")
    .join(" ")
    .slice(0, 5000);
  const classifications = Object.values(trial.classifications ?? {})
    .flatMap((value) => (Array.isArray(value) ? value : [value]))
    .map((value) => value?.label ?? value?.categoryId ?? "")
    .join(" ");
  const recovery = isRecoveryTrial(trial)
    ? `${recoveryFailureCount(trial)} failed compiler results terminal acceptance recovery`
    : "";
  return [
    trial.trialId,
    trial.taskId,
    trial.source,
    trial.difficulty,
    trialHeadline(trial),
    classifications,
    recovery,
    JSON.stringify(trial.metadata ?? {}),
    formalContext,
  ]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase();
}

function trialMatchesMatrix(trial: DashboardTrial, state: DashboardState): boolean {
  if (!hasSubgoalCapability(trial)) {
    return !state.matrixBehavior && !state.matrixProgress;
  }
  const behavior = trial.classifications?.failureBehavior?.categoryId ?? "";
  const progress = trial.classifications?.progressStage?.categoryId ?? "";
  return (
    (!state.matrixBehavior || behavior === state.matrixBehavior) &&
    (!state.matrixProgress || progress === state.matrixProgress)
  );
}

function renderTrialLink(
  trial: DashboardTrial,
  selectedTrial: DashboardTrial,
  state: DashboardState,
): string {
  const event = selectedEvent(trial, "");
  const active = trial.trialId === selectedTrial.trialId;
  const progress = assignmentLabel(trial.classifications?.progressStage);
  const result = assignmentLabel(trial.classifications?.successPattern) || trialOutcomeLabel(trial);
  const recovery = isRecoveryTrial(trial);
  const shortId = trial.trialId.match(/_(t\d+)$/)?.[1] ?? trial.trialId;
  const recoveryFailures = recoveryFailureCount(trial);
  return `
    <a
      class="trial-link${active ? " is-selected" : ""}"
      href="${escapeAttribute(routeHref(trial.trialId, event?.seq ?? 0, "trace"))}"
      data-trial-select="${escapeAttribute(trial.trialId)}"
      data-search-item
      data-search-text="${escapeAttribute(trialSearchText(trial))}"
      data-matrix-match="${trialMatchesMatrix(trial, state) ? "true" : "false"}"
      aria-current="${active ? "true" : "false"}"
    >
      <span class="trial-link-id">${escapeHtml(recovery ? shortId : trial.trialId)}</span>
      <span class="trial-link-meta">${
        recovery
          ? `${escapeHtml(recoveryFailures)} failure${recoveryFailures === 1 ? "" : "s"} -> accepted`
          : `${escapeHtml(progress || result)} | ${escapeHtml(trial.events.length)} events`
      }</span>
    </a>
  `;
}

function renderNavigationGroup(
  group: NavigationGroup,
  selectedTrial: DashboardTrial,
  state: DashboardState,
): string {
  const containsSelected = group.trials.some((trial) => trial.trialId === selectedTrial.trialId);
  return `
    <details class="navigation-group" data-search-group ${containsSelected ? "open" : ""}>
      <summary>
        <span>${escapeHtml(group.label)}</span>
        <strong>${escapeHtml(group.trials.length)}</strong>
      </summary>
      ${group.description ? `<p class="group-description">${escapeHtml(group.description)}</p>` : ""}
      <div class="trial-links">
        ${group.trials.map((trial) => renderTrialLink(trial, selectedTrial, state)).join("")}
      </div>
    </details>
  `;
}

function renderNavigationSection(
  section: NavigationSection,
  selectedTrial: DashboardTrial,
  state: DashboardState,
): string {
  const sourceTrials = section.groups.flatMap((group) => group.trials);
  const recoveryTrials = sourceTrials.filter(isRecoveryTrial);
  const recoveryGroups: NavigationGroup[] = recoveryTrials.length
    ? [...recoveryTrials.reduce((tasks, trial) => {
        const trials = tasks.get(trial.taskId) ?? [];
        trials.push(trial);
        tasks.set(trial.taskId, trials);
        return tasks;
      }, new Map<string, DashboardTrial[]>()).entries()]
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([taskId, trials]) => ({
          id: `recovery-task-${taskId}`,
          label: taskId,
          trials: [...trials].sort((left, right) => left.trialId.localeCompare(right.trialId)),
        }))
    : [];
  const remainingGroups = section.groups
    .map((group) => ({
      ...group,
      trials: group.trials.filter(
        (trial) => !isRecoveryTrial(trial) && !isOneShotTrial(trial),
      ),
    }))
    .filter((group) => group.trials.length > 0);
  const groups = recoveryGroups.length ? [...recoveryGroups, ...remainingGroups] : section.groups;
  const count = groups.reduce((total, group) => total + group.trials.length, 0);
  const containsSelected = groups.some((group) =>
    group.trials.some((trial) => trial.trialId === selectedTrial.trialId),
  );
  return `
    <details class="navigation-section" data-search-section data-navigation-section="${escapeAttribute(section.id)}" ${containsSelected ? "open" : ""}>
      <summary>
        <span>${escapeHtml(section.label)}</span>
        <strong>${escapeHtml(count)}</strong>
      </summary>
      <div class="navigation-groups">
        ${groups.map((group) => renderNavigationGroup(group, selectedTrial, state)).join("")}
      </div>
    </details>
  `;
}

function renderOneShotEntry(
  entry: SuccessIndexEntry,
  bundle: DashboardBundle,
  selectedTrial: DashboardTrial,
  state: DashboardState,
): string {
  const fullTrace = bundle.trials.find((trial) => trial.trialId === entry.trialId);
  const active = fullTrace?.trialId === selectedTrial.trialId;
  const body = `
    <span class="index-trial-id">${escapeHtml(entry.trialId)}</span>
    <span class="index-trial-meta">accepted #${escapeHtml(entry.acceptedResultSeq ?? "?")} | ${escapeHtml(entry.eventCount)} events</span>
  `;
  const searchText = [
    entry.trialId,
    entry.taskId,
    entry.source,
    entry.difficulty,
    "one-shot success accepted exact target",
  ]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase();
  const matrixMatch = !state.matrixBehavior && !state.matrixProgress;
  if (!fullTrace) {
    return `<li class="index-trial" data-search-item data-search-text="${escapeAttribute(searchText)}" data-matrix-match="${matrixMatch ? "true" : "false"}" data-index-only-trial="${escapeAttribute(entry.trialId)}">${body}</li>`;
  }
  return `
    <li class="index-trial has-full-trace${active ? " is-selected" : ""}" data-search-item data-search-text="${escapeAttribute(`${searchText} ${trialSearchText(fullTrace)}`)}" data-matrix-match="${matrixMatch ? "true" : "false"}">
      <a
        href="${escapeAttribute(routeHref(fullTrace.trialId, entry.acceptedResultSeq ?? fullTrace.events[0]?.seq ?? 0, "trace"))}"
        data-trial-select="${escapeAttribute(fullTrace.trialId)}"
        aria-current="${active ? "true" : "false"}"
      >${body}<span class="index-open-label">full contrast</span></a>
    </li>
  `;
}

function renderOneShotIndex(
  bundle: DashboardBundle,
  selectedTrial: DashboardTrial,
  state: DashboardState,
): string {
  const entries = bundle.indexes?.oneShotSuccesses ?? [];
  if (!entries.length) {
    return "";
  }
  return `
    <details class="one-shot-index" data-search-section>
      <summary>
        <span>One-shot success index</span>
        <strong>${escapeHtml(entries.length)}</strong>
      </summary>
      <p>Compact cohort index. The labelled reference opens as a full trace.</p>
      <ol>
        ${entries.map((entry) => renderOneShotEntry(entry, bundle, selectedTrial, state)).join("")}
      </ol>
    </details>
  `;
}

function renderNavigation(
  bundle: DashboardBundle,
  sections: NavigationSection[],
  selectedTrial: DashboardTrial,
  state: DashboardState,
): string {
  return `
    <aside class="browser-pane${state.drawerOpen ? " is-open" : ""}" id="trace-browser" aria-label="Trace browser">
      <header class="browser-pane-head">
        <div>
          <p class="kicker">Evidence tree</p>
          <h2>Browse traces</h2>
        </div>
        <button class="drawer-close" type="button" data-drawer-close aria-label="Close trace browser">X</button>
      </header>
      <label class="navigation-search">
        <span>Search trials</span>
        <input type="search" data-trial-search autocomplete="off" placeholder="Trial, task, Lean symbol, recovery..." />
        <small data-search-status>Indexed trial entries</small>
      </label>
      <nav class="trace-navigation" aria-label="Failure, recovery, and progress groups">
        ${sections.map((section) => renderNavigationSection(section, selectedTrial, state)).join("")}
        ${renderOneShotIndex(bundle, selectedTrial, state)}
        <p class="navigation-empty" data-search-empty hidden>No trials match the current search and matrix filter.</p>
      </nav>
    </aside>
  `;
}

function renderRecoveryRail(
  trial: DashboardTrial,
  event: DashboardEvent | undefined,
): string {
  const stages = recoveryStages(trial);
  const regressionNote = recoveryRegressionNote(trial);
  if (!stages.length) {
    return "";
  }
  return `
    <section class="recovery-rail" aria-labelledby="recovery-heading">
      <div class="recovery-rail-head">
        <div>
          <p class="kicker">Failed compiler evidence -> exact-target acceptance</p>
          <h3 id="recovery-heading">Recovery stages</h3>
        </div>
        <span>${escapeHtml(recoveryFailureCount(trial))} failed compiler result${recoveryFailureCount(trial) === 1 ? "" : "s"}</span>
      </div>
      <ol>
        ${stages
          .map((stage, index) => {
            const active = event?.seq === stage.seq;
            return `
              <li class="recovery-stage tone-${stage.tone}${active ? " is-selected" : ""}">
                <a
                  href="${escapeAttribute(routeHref(trial.trialId, stage.seq, "trace"))}"
                  data-event-select="${escapeAttribute(stage.seq)}"
                  aria-current="${active ? "step" : "false"}"
                >
                  <span class="stage-index">${index + 1}</span>
                  <span><strong>${escapeHtml(stage.label)}</strong><small>#${escapeHtml(stage.seq)} | ${escapeHtml(stage.detail)}</small></span>
                </a>
              </li>
            `;
          })
          .join("")}
      </ol>
      ${regressionNote ? `<p class="recovery-regression-note"><strong>Regression note:</strong> ${escapeHtml(regressionNote)}</p>` : ""}
    </section>
  `;
}

function renderViewTabs(
  trial: DashboardTrial,
  event: DashboardEvent | undefined,
  activeView: ViewId,
): string {
  return `
    <nav class="view-tabs" role="tablist" aria-label="Trace views">
      ${availableViews(trial)
        .map((view) => {
          const active = view === activeView;
          return `
            <a
              class="view-tab${active ? " is-selected" : ""}"
              href="${escapeAttribute(routeHref(trial.trialId, event?.seq ?? 0, view))}"
              data-view-select="${escapeAttribute(view)}"
              role="tab"
              aria-selected="${active ? "true" : "false"}"
              aria-controls="active-view-panel"
              tabindex="${active ? "0" : "-1"}"
            >${escapeHtml(VIEW_LABELS[view])}</a>
          `;
        })
        .join("")}
    </nav>
  `;
}

function renderActiveView(
  trial: DashboardTrial,
  event: DashboardEvent | undefined,
  state: DashboardState,
): string {
  if (state.view === "subgoals" && hasSubgoalCapability(trial)) {
    return renderSubgoalView(trial, event, state.selectedSubgoal);
  }
  const view = state.view === "subgoals" ? "trace" : state.view;
  return renderTraceView(view, trial, event);
}

function sourceCount(bundle: DashboardBundle): number {
  return Array.isArray(bundle.provenance?.sourceFiles) ? bundle.provenance?.sourceFiles?.length ?? 0 : 0;
}

function taxonomyCategories(
  bundle: DashboardBundle,
  trials: DashboardTrial[],
  kind: "behavior" | "progress",
): TaxonomyCategory[] {
  const assignment = trials
    .map((trial) =>
      kind === "behavior"
        ? trial.classifications?.failureBehavior
        : trial.classifications?.progressStage,
    )
    .find(Boolean);
  const taxonomy = bundle.taxonomies.find((candidate) => candidate.axisId === assignment?.axisId);
  if (taxonomy?.categories.length) {
    return [...taxonomy.categories].sort(
      (left, right) => left.order - right.order || left.label.localeCompare(right.label),
    );
  }
  const categories = new Map<string, TaxonomyCategory>();
  for (const trial of trials) {
    const value =
      kind === "behavior"
        ? trial.classifications?.failureBehavior
        : trial.classifications?.progressStage;
    if (value && !categories.has(value.categoryId)) {
      categories.set(value.categoryId, {
        categoryId: value.categoryId,
        label: value.label || value.categoryId,
        order: categories.size,
      });
    }
  }
  return [...categories.values()];
}

function renderMediumMatrix(
  bundle: DashboardBundle,
  trial: DashboardTrial,
  state: DashboardState,
): string {
  if (!hasSubgoalCapability(trial)) {
    return "";
  }
  const mediumTrials = bundle.trials.filter(hasSubgoalCapability);
  const behaviors = taxonomyCategories(bundle, mediumTrials, "behavior");
  const progressStages = taxonomyCategories(bundle, mediumTrials, "progress");
  const selectedBehavior = behaviors.find(
    (category) => category.categoryId === state.matrixBehavior,
  );
  const selectedProgress = progressStages.find(
    (category) => category.categoryId === state.matrixProgress,
  );
  const grandTotal = mediumTrials.length;
  return `
    <section class="medium-matrix" aria-labelledby="medium-matrix-heading">
      <div class="medium-matrix-head">
        <div>
          <p class="kicker">Behavior by achieved progress</p>
          <h3 id="medium-matrix-heading">Medium failure matrix</h3>
        </div>
        <div class="matrix-filter-state">
          ${
            selectedBehavior || selectedProgress
              ? `<span>Filter: ${escapeHtml(selectedBehavior?.label ?? "all behaviors")} | ${escapeHtml(selectedProgress?.label ?? "all P stages")}</span>
                 <button type="button" data-clear-matrix-filter>Clear filter</button>`
              : `<span>${escapeHtml(grandTotal)} classified trials</span>`
          }
        </div>
      </div>
      <div class="matrix-scroll" tabindex="0" aria-label="Scrollable medium failure matrix">
        <table>
          <thead>
            <tr>
              <th scope="col">Failure behavior</th>
              ${progressStages.map((category) => `<th scope="col" title="${escapeAttribute(category.description ?? category.label)}">${escapeHtml(category.label)}</th>`).join("")}
              <th scope="col">Total</th>
            </tr>
          </thead>
          <tbody>
            ${behaviors
              .map((behavior) => {
                const rowTrials = mediumTrials.filter(
                  (candidate) =>
                    candidate.classifications?.failureBehavior?.categoryId === behavior.categoryId,
                );
                return `
                  <tr>
                    <th scope="row" title="${escapeAttribute(behavior.description ?? behavior.label)}">${escapeHtml(behavior.label)}</th>
                    ${progressStages
                      .map((progress) => {
                        const matches = rowTrials.filter(
                          (candidate) =>
                            candidate.classifications?.progressStage?.categoryId === progress.categoryId,
                        );
                        const first = matches[0];
                        const firstEvent = first ? selectedEvent(first, "") : undefined;
                        const active =
                          state.matrixBehavior === behavior.categoryId &&
                          state.matrixProgress === progress.categoryId;
                        return `
                          <td class="matrix-cell${active ? " is-selected" : ""}">
                            ${
                              first
                                ? `<a
                                    href="${escapeAttribute(routeHref(first.trialId, firstEvent?.seq ?? 0, normalizeView(first, state.view)))}"
                                    data-trial-select="${escapeAttribute(first.trialId)}"
                                    data-matrix-behavior="${escapeAttribute(behavior.categoryId)}"
                                    data-matrix-progress="${escapeAttribute(progress.categoryId)}"
                                    aria-label="${escapeAttribute(`${matches.length} trials: ${behavior.label}, ${progress.label}`)}"
                                  >${escapeHtml(matches.length)}</a>`
                                : `<span aria-label="No trials">0</span>`
                            }
                          </td>
                        `;
                      })
                      .join("")}
                    <td class="matrix-total">${escapeHtml(rowTrials.length)}</td>
                  </tr>
                `;
              })
              .join("")}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">Total</th>
              ${progressStages
                .map((progress) =>
                  `<td class="matrix-total">${escapeHtml(
                    mediumTrials.filter(
                      (candidate) =>
                        candidate.classifications?.progressStage?.categoryId === progress.categoryId,
                    ).length,
                  )}</td>`,
                )
                .join("")}
              <td class="matrix-grand-total">${escapeHtml(grandTotal)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  `;
}

function sectionTrials(section: NavigationSection | undefined, fallback: DashboardTrial): DashboardTrial[] {
  if (!section) {
    return [fallback];
  }
  const unique = new Map<string, DashboardTrial>();
  for (const trial of section.groups.flatMap((group) => group.trials)) {
    unique.set(trial.trialId, trial);
  }
  return [...unique.values()];
}

function trialLinkFor(target: DashboardTrial, state: DashboardState): string {
  const event = selectedEvent(target, "");
  return routeHref(target.trialId, event?.seq ?? 0, normalizeView(target, state.view));
}

function renderTraceActions(
  bundle: DashboardBundle,
  section: NavigationSection | undefined,
  trial: DashboardTrial,
  state: DashboardState,
): string {
  const sectionPeers = sectionTrials(section, trial);
  const peers = isRecoveryTrial(trial)
    ? sectionPeers.filter(isRecoveryTrial)
    : sectionPeers;
  const index = Math.max(0, peers.findIndex((candidate) => candidate.trialId === trial.trialId));
  const previous = index > 0 ? peers[index - 1] : undefined;
  const next = index < peers.length - 1 ? peers[index + 1] : undefined;
  const contrast = isRecoveryTrial(trial)
    ? bundle.trials.find(isOneShotTrial)
    : isOneShotTrial(trial)
      ? bundle.trials.find(isRecoveryTrial)
      : undefined;
  const reference = `lean_failure_modes_meeting.html${routeHref(trial.trialId, state.eventRef, state.view)}`;
  return `
    <div class="trace-actions" aria-label="Trace navigation and reference">
      <div class="trace-action-links">
        ${
          previous
            ? `<a href="${escapeAttribute(trialLinkFor(previous, state))}" data-trial-select="${escapeAttribute(previous.trialId)}" data-previous-trace>Previous trace</a>`
            : `<span class="disabled-action" data-previous-trace aria-disabled="true">Previous trace</span>`
        }
        ${
          next
            ? `<a href="${escapeAttribute(trialLinkFor(next, state))}" data-trial-select="${escapeAttribute(next.trialId)}" data-next-trace>Next trace</a>`
            : `<span class="disabled-action" data-next-trace aria-disabled="true">Next trace</span>`
        }
        ${
          contrast
            ? `<a class="contrast-link" href="${escapeAttribute(trialLinkFor(contrast, state))}" data-trial-select="${escapeAttribute(contrast.trialId)}">${isRecoveryTrial(trial) ? "One-shot contrast" : "Recovery contrast"}</a>`
            : ""
        }
      </div>
      <div class="copy-reference">
        <code>${escapeHtml(reference)}</code>
        <button type="button" data-copy-reference="${escapeAttribute(reference)}">Copy trace reference</button>
      </div>
    </div>
  `;
}

function renderAuditWarning(trial: DashboardTrial): string {
  const flags = trial.classifications?.auditFlags ?? [];
  if (!hasSubgoalCapability(trial) || flags.length === 0) {
    return "";
  }
  return `
    <aside class="audit-warning" role="note">
      <strong>Audit warning</strong>
      <span>${flags.map((flag) => escapeHtml(assignmentLabel(flag))).join(" | ")}</span>
    </aside>
  `;
}

function renderTrialHeader(
  bundle: DashboardBundle,
  trial: DashboardTrial,
): string {
  if (isRecoveryTrial(trial)) {
    const recoveryCount = bundle.indexes?.recoverySuccesses?.length ?? bundle.trials.filter(isRecoveryTrial).length;
    return `
      <div class="trial-title-row recovery-title-row">
        <div>
          <p class="kicker">${escapeHtml(recoveryCount)} complete traces | <code>${escapeHtml(trial.trialId)}</code></p>
          <h2>Recovery after compiler failure</h2>
        </div>
      </div>
      <p class="trial-summary">At least one failed compiler result precedes terminal kernel-confirmed exact-target acceptance.</p>
      ${renderTrialBadges(trial)}
    `;
  }
  if (hasSubgoalCapability(trial)) {
    const behavior = assignmentLabel(trial.classifications?.failureBehavior) || primaryModeLabel(trial);
    const progress = assignmentLabel(trial.classifications?.progressStage) || "Progress stage not recorded";
    return `
      <div class="trial-title-row medium-title-row">
        <div>
          <p class="kicker">${escapeHtml(trial.taskId)} | ${escapeHtml(trial.difficulty || "medium")} | ${escapeHtml(trial.trialId)}</p>
          <h2>${escapeHtml(behavior)}</h2>
        </div>
        <span class="progress-stage-label">${escapeHtml(progress)}</span>
      </div>
      <p class="trial-summary">${escapeHtml(trialHeadline(trial))}</p>
      ${renderTrialBadges(trial)}
    `;
  }
  return `
    <div class="trial-title-row">
      <div>
        <p class="kicker">${escapeHtml(trial.taskId)} | ${escapeHtml(trial.difficulty || "difficulty not recorded")}</p>
        <h2>${escapeHtml(trial.trialId)}</h2>
      </div>
      <span class="outcome-label tone-${statusTone(trialOutcomeLabel(trial))}">${escapeHtml(trialOutcomeLabel(trial))}</span>
    </div>
    <p class="trial-summary">${escapeHtml(trialHeadline(trial))}</p>
    ${renderTrialBadges(trial)}
  `;
}

function renderTrialWorkspace(
  bundle: DashboardBundle,
  sections: NavigationSection[],
  trial: DashboardTrial,
  state: DashboardState,
): string {
  const event = selectedEvent(trial, state.eventRef);
  const section = sectionForTrial(sections, trial.trialId);
  const group = groupForTrial(sections, trial.trialId);
  return `
    <main
      class="trace-pane"
      id="trace-workspace"
      data-selected-trace="${escapeAttribute(trial.trialId)}"
      data-selected-event-seq="${escapeAttribute(event?.seq ?? "")}"
      data-selected-view-panel="${escapeAttribute(state.view)}"
    >
      <header class="trial-header">
        <div class="trial-breadcrumbs">
          <button class="browse-button" type="button" data-drawer-open aria-controls="trace-browser" aria-expanded="${state.drawerOpen ? "true" : "false"}">Browse traces</button>
          <span>${escapeHtml(section?.label ?? trial.sectionId)}</span>
          <span aria-hidden="true">/</span>
          <span>${escapeHtml(group?.label ?? primaryModeLabel(trial))}</span>
        </div>
        ${renderTrialHeader(bundle, trial)}
        ${renderTraceActions(bundle, section, trial, state)}
      </header>
      ${renderRecoveryRail(trial, event)}
      ${renderMediumMatrix(bundle, trial, state)}
      ${renderAuditWarning(trial)}
      ${renderViewTabs(trial, event, state.view)}
      <section id="active-view-panel" class="active-view" role="tabpanel" aria-label="${escapeAttribute(VIEW_LABELS[state.view])}">
        ${renderActiveView(trial, event, state)}
      </section>
      <footer class="workspace-footer">
        <span>${escapeHtml(sourceCount(bundle))} source files recorded in bundle provenance</span>
        <span>Hash route: <code>trial</code> | <code>event</code> | <code>view</code></span>
      </footer>
    </main>
  `;
}

function renderScope(bundle: DashboardBundle): string {
  const mediumFailures = bundle.trials.filter(hasSubgoalCapability).length;
  const easyFailures = bundle.trials.filter(
    (trial) => !hasSubgoalCapability(trial) && !isRecoveryTrial(trial) && !isOneShotTrial(trial),
  ).length;
  const recoveries =
    bundle.indexes?.recoverySuccesses?.length ??
    bundle.trials.filter((trial) =>
      trial.classifications?.successPattern?.categoryId.toLowerCase().includes("recovery"),
    ).length;
  const oneShotContrasts = bundle.trials.filter(isOneShotTrial).length;
  return [
    `${bundle.trials.length} complete traces`,
    `${easyFailures} easy failures`,
    `${mediumFailures} medium failures`,
    `${recoveries} recoveries`,
    `${oneShotContrasts} one-shot contrast${oneShotContrasts === 1 ? "" : "s"}`,
  ].join(" | ");
}

export function renderDashboard(
  bundle: DashboardBundle,
  trial: DashboardTrial,
  state: DashboardState,
  routeNotice = "",
): string {
  const sections = navigationSections(bundle);
  return `
    <div class="meeting-shell${state.drawerOpen ? " drawer-open" : ""}" data-ui-shell>
      <header class="meeting-header">
        <div>
          <p class="kicker">Teammate meeting | trace-verifiable analysis</p>
          <h1>Lean Agent Failure Modes</h1>
          <p>${escapeHtml(renderScope(bundle))}</p>
        </div>
      </header>
      ${
        routeNotice
          ? `<aside class="route-notice" role="status"><span>${escapeHtml(routeNotice)}</span><button type="button" data-dismiss-route-notice aria-label="Dismiss route notice">Dismiss</button></aside>`
          : ""
      }
      <div class="browser-layout">
        ${renderNavigation(bundle, sections, trial, state)}
        ${renderTrialWorkspace(bundle, sections, trial, state)}
      </div>
      <button class="drawer-backdrop" type="button" data-drawer-close aria-label="Close trace browser"></button>
    </div>
  `;
}

export function renderDashboardError(message: string): string {
  return `
    <main class="fatal-error" role="alert">
      <p class="kicker">Dashboard could not start</p>
      <h1>Trace data is unavailable</h1>
      <p>${escapeHtml(message)}</p>
      <p>Rebuild the meeting report so the validated <code>meeting-data</code> bundle is embedded in this file.</p>
    </main>
  `;
}
