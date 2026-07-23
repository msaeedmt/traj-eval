import "./styles.css";
import { renderDashboard, renderDashboardError } from "./dashboard-view";
import {
  type DashboardBundle,
  type DashboardState,
  type DashboardTrial,
  type ViewId,
  availableViews,
  defaultEvent,
  findEvent,
  findTrial,
  hasSubgoalCapability,
  navigationSections,
  normalizeView,
  parseDashboardBundle,
  parseRoute,
  routeHref,
  selectedEvent,
} from "./model";

const app = document.querySelector<HTMLDivElement>("#meeting-app");
const embedded = document.querySelector<HTMLScriptElement>("#meeting-data");

let bundle: DashboardBundle;
let state: DashboardState;
let searchQuery = "";
let routeNotice = "";

function firstTrial(source: DashboardBundle): DashboardTrial | undefined {
  const indexed = new Map(source.trials.map((trial) => [trial.trialId, trial]));
  const firstDeclared = [...source.views]
    .sort((a, b) => a.order - b.order)
    .flatMap((view) => view.trialIds)
    .map((trialId) => indexed.get(trialId))
    .find((trial): trial is DashboardTrial => Boolean(trial));
  if (firstDeclared) {
    return firstDeclared;
  }
  return navigationSections(source)
    .flatMap((section) => section.groups)
    .flatMap((group) => group.trials)[0] ?? source.trials[0];
}

function subgoalIdsAt(trial: DashboardTrial, eventSeq: number): string[] {
  if (!hasSubgoalCapability(trial)) {
    return [];
  }
  const extension = trial.extensions?.subgoals;
  if (!extension) {
    return [];
  }
  const frame = [...extension.frames]
    .filter((candidate) => candidate.seq <= eventSeq)
    .sort((a, b) => b.seq - a.seq || b.version - a.version)[0];
  return (frame?.nodes ?? extension.nodes).map((node) => node.id);
}

function normalizeState(
  source: DashboardBundle,
  requested: Partial<DashboardState>,
  previous?: DashboardState,
): { trial: DashboardTrial; state: DashboardState } {
  const trial = findTrial(source, requested.trialId ?? "") ?? firstTrial(source);
  if (!trial) {
    throw new Error("The dashboard bundle contains no full traces.");
  }
  const event = selectedEvent(trial, requested.eventRef ?? "") ?? defaultEvent(trial);
  if (!event) {
    throw new Error(`Trace ${trial.trialId} contains no events.`);
  }
  const view = normalizeView(trial, String(requested.view ?? "trace"));
  const requestedSubgoal = requested.selectedSubgoal ?? previous?.selectedSubgoal ?? "";
  const subgoalIds = subgoalIdsAt(trial, event.seq);
  const selectedSubgoal = subgoalIds.includes(requestedSubgoal)
    ? requestedSubgoal
    : subgoalIds[0] ?? "";
  return {
    trial,
    state: {
      trialId: trial.trialId,
      eventRef: String(event.seq),
      view,
      drawerOpen: requested.drawerOpen ?? previous?.drawerOpen ?? false,
      selectedSubgoal,
      matrixBehavior: requested.matrixBehavior ?? previous?.matrixBehavior ?? "",
      matrixProgress: requested.matrixProgress ?? previous?.matrixProgress ?? "",
    },
  };
}

function invalidRouteNotice(
  source: DashboardBundle,
  requested: Partial<DashboardState>,
  hash: string,
): string {
  if (!hash || hash === "#") {
    return "";
  }
  const requestedTrialId = requested.trialId ?? "";
  const trial = findTrial(source, requestedTrialId);
  if (requestedTrialId && !trial) {
    return `Trace ${requestedTrialId} is not in this validated bundle. The first available trace is shown.`;
  }
  const resolvedTrial = trial ?? firstTrial(source);
  if (!resolvedTrial) {
    return "";
  }
  if (requested.eventRef && !findEvent(resolvedTrial, requested.eventRef)) {
    return `Event ${requested.eventRef} is not present in ${resolvedTrial.trialId}. A recorded evidence event is shown instead.`;
  }
  if (
    requested.view &&
    !availableViews(resolvedTrial).includes((requested.view === "json" ? "jsonl" : requested.view) as ViewId)
  ) {
    return `View ${requested.view} is unavailable for this trace. The trace timeline is shown instead.`;
  }
  return "";
}

function currentHref(nextState = state): string {
  return routeHref(nextState.trialId, nextState.eventRef, nextState.view);
}

function exposeSmokeMarkers(trial: DashboardTrial): void {
  if (!app) {
    return;
  }
  app.dataset.dashboardReady = "true";
  app.dataset.selectedTrial = trial.trialId;
  app.dataset.selectedEvent = state.eventRef;
  app.dataset.selectedView = state.view;
  app.dataset.selectedSubgoal = state.selectedSubgoal;
  app.setAttribute("aria-busy", "false");
  document.documentElement.dataset.dashboardReady = "true";
  document.documentElement.dataset.selectedTrial = trial.trialId;
}

function syncDrawerAccessibility(): void {
  const pane = document.querySelector<HTMLElement>("#trace-browser");
  if (!pane) {
    return;
  }
  const isMobile = window.matchMedia("(max-width: 820px)").matches;
  pane.inert = isMobile && !state.drawerOpen;
  pane.setAttribute("aria-hidden", isMobile && !state.drawerOpen ? "true" : "false");
}

function applyNavigationFilters(): void {
  if (!app) {
    return;
  }
  const query = searchQuery.trim().toLocaleLowerCase();
  const items = [...app.querySelectorAll<HTMLElement>("[data-search-item]")];
  let visible = 0;
  for (const item of items) {
    const matchesSearch = !query || (item.dataset.searchText ?? "").includes(query);
    const matchesMatrix = item.dataset.matrixMatch !== "false";
    item.hidden = !(matchesSearch && matchesMatrix);
    if (!item.hidden) {
      visible += 1;
    }
  }
  const groups = [...app.querySelectorAll<HTMLDetailsElement>("[data-search-group]")];
  for (const group of groups) {
    const hasVisible = [...group.querySelectorAll<HTMLElement>("[data-search-item]")].some(
      (item) => !item.hidden,
    );
    group.hidden = !hasVisible;
    if (query && hasVisible) {
      group.open = true;
    }
  }
  const sections = [...app.querySelectorAll<HTMLDetailsElement>("[data-search-section]")];
  for (const section of sections) {
    const hasVisible = [...section.querySelectorAll<HTMLElement>("[data-search-item]")].some(
      (item) => !item.hidden,
    );
    section.hidden = !hasVisible;
    if (query && hasVisible) {
      section.open = true;
    }
  }
  const input = app.querySelector<HTMLInputElement>("[data-trial-search]");
  if (input && input.value !== searchQuery) {
    input.value = searchQuery;
  }
  const status = app.querySelector<HTMLElement>("[data-search-status]");
  if (status) {
    status.textContent = query ? `${visible} matching entries` : `${visible} indexed entries`;
  }
  const empty = app.querySelector<HTMLElement>("[data-search-empty]");
  if (empty) {
    empty.hidden = visible > 0;
  }
}

function render(requested: Partial<DashboardState> = state): void {
  if (!app) {
    return;
  }
  const normalized = normalizeState(bundle, requested, state);
  state = normalized.state;
  app.innerHTML = renderDashboard(bundle, normalized.trial, state, routeNotice);
  exposeSmokeMarkers(normalized.trial);
  syncDrawerAccessibility();
  applyNavigationFilters();
}

function replaceRouteIfNeeded(): void {
  if (window.location.hash !== currentHref()) {
    window.history.replaceState(null, "", currentHref());
  }
}

function selectAdjacentEvent(direction: -1 | 1): void {
  const trial = findTrial(bundle, state.trialId);
  if (!trial) {
    return;
  }
  const events = [...trial.events].sort((a, b) => a.seq - b.seq);
  const current = selectedEvent(trial, state.eventRef);
  const index = Math.max(0, events.findIndex((event) => event.eventId === current?.eventId));
  const nextIndex = Math.max(0, Math.min(events.length - 1, index + direction));
  const next = events[nextIndex];
  if (next && next.eventId !== current?.eventId) {
    window.location.hash = routeHref(trial.trialId, next.seq, state.view);
  }
}

function openDrawer(): void {
  render({ ...state, drawerOpen: true });
  requestAnimationFrame(() => {
    document.querySelector<HTMLButtonElement>("[data-drawer-close]")?.focus();
  });
}

function closeDrawer(restoreFocus = false): void {
  if (!state.drawerOpen) {
    return;
  }
  render({ ...state, drawerOpen: false });
  if (restoreFocus) {
    requestAnimationFrame(() => {
      document.querySelector<HTMLButtonElement>("[data-drawer-open]")?.focus();
    });
  }
}

function fallbackCopy(value: string): boolean {
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.append(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  return copied;
}

async function copyReference(button: HTMLButtonElement): Promise<void> {
  const value = button.dataset.copyReference ?? "";
  if (!value) {
    return;
  }
  let copied = false;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      copied = true;
    }
  } catch {
    copied = false;
  }
  if (!copied) {
    copied = fallbackCopy(value);
  }
  const original = button.dataset.copyLabel || button.textContent || "Copy trace reference";
  button.dataset.copyLabel = original;
  button.textContent = copied ? "Copied trace reference" : "Copy unavailable";
  window.setTimeout(() => {
    button.textContent = original;
  }, 1600);
}

function bindInteractions(): void {
  if (!app) {
    return;
  }
  app.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) {
      return;
    }
    const target = event.target;
    if (target.closest("[data-drawer-open]")) {
      event.preventDefault();
      openDrawer();
      return;
    }
    const dismiss = target.closest("[data-dismiss-route-notice]");
    if (dismiss) {
      event.preventDefault();
      routeNotice = "";
      render(state);
      return;
    }
    const copy = target.closest<HTMLButtonElement>("[data-copy-reference]");
    if (copy) {
      event.preventDefault();
      void copyReference(copy);
      return;
    }
    const clearMatrix = target.closest("[data-clear-matrix-filter]");
    if (clearMatrix) {
      event.preventDefault();
      render({ ...state, matrixBehavior: "", matrixProgress: "" });
      return;
    }
    const matrixCell = target.closest<HTMLElement>("[data-matrix-behavior][data-matrix-progress]");
    if (matrixCell) {
      state.matrixBehavior = matrixCell.dataset.matrixBehavior ?? "";
      state.matrixProgress = matrixCell.dataset.matrixProgress ?? "";
      if ((matrixCell as HTMLAnchorElement).hash === window.location.hash) {
        render(state);
      }
    }
    if (target.closest("[data-drawer-close]")) {
      event.preventDefault();
      closeDrawer(true);
      return;
    }
    const subgoal = target.closest<HTMLElement>("[data-subgoal-select]");
    if (subgoal?.dataset.subgoalSelect) {
      state.selectedSubgoal = subgoal.dataset.subgoalSelect;
      if ((subgoal as HTMLAnchorElement).hash === window.location.hash) {
        render(state);
      }
    }
    const trialLink = target.closest<HTMLElement>("[data-trial-select]");
    if (trialLink && state.drawerOpen) {
      state.drawerOpen = false;
    }
  });

  app.addEventListener("input", (event) => {
    if (!(event.target instanceof HTMLInputElement) || !event.target.matches("[data-trial-search]")) {
      return;
    }
    searchQuery = event.target.value;
    applyNavigationFilters();
  });

  document.addEventListener("keydown", (event) => {
    const target = event.target as HTMLElement;
    if (event.key === "Escape" && state.drawerOpen) {
      event.preventDefault();
      closeDrawer(true);
      return;
    }
    const trialLink = target.closest<HTMLElement>("[data-trial-select]");
    if (trialLink && ["ArrowUp", "ArrowDown"].includes(event.key)) {
      const links = [...document.querySelectorAll<HTMLElement>("[data-trial-select]")].filter(
        (item) => !item.hidden && item.getClientRects().length > 0,
      );
      const index = Math.max(0, links.indexOf(trialLink));
      const direction = event.key === "ArrowDown" ? 1 : -1;
      const next = links[(index + direction + links.length) % links.length];
      if (next) {
        event.preventDefault();
        next.focus();
      }
      return;
    }
    const tab = target.closest<HTMLAnchorElement>("[role='tab']");
    if (tab && ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      const tabs = [...document.querySelectorAll<HTMLAnchorElement>("[role='tab']")];
      const index = Math.max(0, tabs.indexOf(tab));
      let nextIndex = index;
      if (event.key === "ArrowLeft") {
        nextIndex = (index - 1 + tabs.length) % tabs.length;
      } else if (event.key === "ArrowRight") {
        nextIndex = (index + 1) % tabs.length;
      } else if (event.key === "Home") {
        nextIndex = 0;
      } else if (event.key === "End") {
        nextIndex = tabs.length - 1;
      }
      const next = tabs[nextIndex];
      if (next) {
        event.preventDefault();
        next.focus();
        window.location.hash = next.hash;
      }
      return;
    }
    if (
      !event.ctrlKey &&
      !event.metaKey &&
      !event.altKey &&
      !target.closest("input, textarea, select")
    ) {
      if (event.key === "[") {
        event.preventDefault();
        selectAdjacentEvent(-1);
      } else if (event.key === "]") {
        event.preventDefault();
        selectAdjacentEvent(1);
      }
    }
  });

  window.addEventListener("hashchange", () => {
    const route = parseRoute(window.location.hash);
    routeNotice = invalidRouteNotice(bundle, route, window.location.hash);
    render({ ...state, ...route, drawerOpen: false });
    replaceRouteIfNeeded();
    const selected = document.querySelector<HTMLElement>("[data-selected-event-detail]");
    if (selected && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      selected.scrollIntoView({ block: "nearest" });
    }
  });

  window.addEventListener("resize", syncDrawerAccessibility);
}

function fail(error: unknown): void {
  if (!app) {
    return;
  }
  const message = error instanceof Error ? error.message : String(error);
  app.innerHTML = renderDashboardError(message);
  app.dataset.dashboardReady = "error";
  app.setAttribute("aria-busy", "false");
  document.documentElement.dataset.dashboardReady = "error";
}

function boot(): void {
  if (!app || !embedded) {
    return;
  }
  try {
    bundle = parseDashboardBundle(embedded.textContent ?? "");
    const route = parseRoute(window.location.hash);
    routeNotice = invalidRouteNotice(bundle, route, window.location.hash);
    const normalized = normalizeState(bundle, { ...route, drawerOpen: false });
    state = normalized.state;
    bindInteractions();
    render(state);
    replaceRouteIfNeeded();
    window.dispatchEvent(new CustomEvent("meeting-dashboard-ready", {
      detail: {
        trialId: state.trialId,
        event: state.eventRef,
        view: state.view,
      },
    }));
  } catch (error) {
    fail(error);
  }
}

void boot();
