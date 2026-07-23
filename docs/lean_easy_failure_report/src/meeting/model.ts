export type ViewId = "trace" | "graph" | "checks" | "jsonl" | "subgoals";

export type EvidenceRef =
  | number
  | string
  | {
      seq?: number;
      eventSeq?: number;
      eventId?: string;
      event_id?: string;
      detail?: string;
    };

export type ClassificationAssignment = {
  axisId: string;
  categoryId: string;
  label: string;
  method?: string;
  confidence?: string;
  evidenceRefs?: EvidenceRef[];
};

export type TrialClassifications = {
  outcome?: ClassificationAssignment;
  successPattern?: ClassificationAssignment;
  failureMode?: ClassificationAssignment;
  progressStage?: ClassificationAssignment;
  failureBehavior?: ClassificationAssignment;
  auditFlags?: ClassificationAssignment[];
};

export type RawRecord = {
  lineNumber: number;
  kind: "header" | "event";
  value: unknown;
};

export type DashboardEvent = {
  eventId: string;
  seq: number;
  timestamp?: string | null;
  kind: string;
  role: string;
  causedBy: string[];
  rawRecordIndex: number;
  text?: string;
  toolCalls?: unknown[];
  toolResponses?: unknown[];
  phase?: string | null;
};

export type CompilerCheck = {
  callId: string;
  callSeq: number;
  resultSeq?: number | null;
  role?: string | null;
  tool?: string | null;
  purpose?: string | null;
  subgoalId?: string | null;
  compiled?: boolean | null;
  sorryFree?: boolean | null;
  nSorries?: number | null;
  verificationStatus?: string | null;
  candidateKind?: string | null;
  statementMatch?: string | null;
  diagnostic?: string | null;
  code?: string | null;
  evidenceHash?: string | null;
  matched?: boolean | null;
};

export type GraphNode = {
  id: string;
  eventId: string;
  seq: number;
  role: string;
  kind: string;
  label: string;
};

export type GraphEdge = {
  source: string;
  target: string;
};

export type TraceGraph = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type SubgoalNode = {
  id: string;
  objective: string;
  dependsOn: string[];
  status: string;
  attempts: number;
  consecutiveFailures: number;
  candidateHash?: string | null;
  acceptedHash?: string | null;
  failures: string[];
  feedback?: string;
};

export type SubgoalFrame = {
  seq: number;
  eventId?: string | null;
  version: number;
  tool?: string | null;
  activeSubgoal?: string | null;
  planReady: boolean;
  forcedRecoveries: number;
  strategyRevisions: number;
  nodes: SubgoalNode[];
  changes: unknown[];
};

export type SubgoalTransition = {
  seq: number;
  eventId?: string | null;
  subgoalId: string;
  kind: string;
  fromStatus?: string | null;
  toStatus?: string | null;
  detail?: string | null;
};

export type ReplayValidation = {
  status: "matched" | "gap" | "unavailable";
  expectedVersion?: number | null;
  observedVersion?: number | null;
  mismatches?: unknown[];
};

export type SubgoalExtension = {
  nodes: SubgoalNode[];
  frames: SubgoalFrame[];
  transitions: SubgoalTransition[];
  replayValidation: ReplayValidation;
};

export type DashboardTrial = {
  trialId: string;
  experimentId: string;
  taskId: string;
  trialNumber?: number | null;
  source?: string | null;
  difficulty?: string | null;
  sectionId: "failures" | "successes" | string;
  groupId: string;
  metadata?: Record<string, unknown>;
  outcome?: unknown;
  classifications?: TrialClassifications;
  summary?: unknown;
  rawRecords: RawRecord[];
  events: DashboardEvent[];
  checks: CompilerCheck[];
  graph?: TraceGraph | null;
  annotations?: unknown[];
  extensions?: {
    subgoals?: SubgoalExtension | null;
    [key: string]: unknown;
  };
  provenance?: Record<string, unknown>;
};

export type Experiment = {
  id: string;
  label: string;
  description?: string;
  order: number;
  capabilities?: string[];
  trialIds: string[];
  metrics?: Record<string, unknown>;
  sourceRefs?: string[];
};

export type TaxonomyCategory = {
  categoryId: string;
  label: string;
  description?: string;
  order: number;
};

export type Taxonomy = {
  axisId: string;
  label: string;
  description?: string;
  exclusive?: boolean;
  categories: TaxonomyCategory[];
};

export type DashboardView = {
  id: string;
  label: string;
  order: number;
  sectionId: string;
  groupAxisId?: string | null;
  trialIds: string[];
};

export type DashboardSectionDefinition = {
  sectionId: string;
  label: string;
  order: number;
  count: number;
  trialIds: string[];
  groups: Array<{
    groupId: string;
    label: string;
    axisId?: string | null;
    order: number;
    count: number;
    trialIds: string[];
  }>;
};

export type SuccessIndexEntry = {
  trialId: string;
  experimentId: string;
  taskId: string;
  trialNumber?: number | null;
  source?: string | null;
  difficulty?: string | null;
  acceptedResultSeq?: number | null;
  eventCount: number;
  failedResultSeqs?: number[];
};

export type DashboardBundle = {
  schemaVersion: "meeting-dashboard.bundle.v1" | string;
  generatedAt?: null;
  scope?: unknown;
  experiments: Experiment[];
  trials: DashboardTrial[];
  taxonomies: Taxonomy[];
  metricDefinitions?: unknown[];
  views: DashboardView[];
  sections?: DashboardSectionDefinition[];
  indexes?: {
    oneShotSuccesses?: SuccessIndexEntry[];
    recoverySuccesses?: SuccessIndexEntry[];
  };
  provenance?: {
    sourceFiles?: unknown[];
    [key: string]: unknown;
  };
  validation?: Record<string, unknown>;
};

export type DashboardState = {
  trialId: string;
  eventRef: string;
  view: ViewId;
  drawerOpen: boolean;
  selectedSubgoal: string;
  matrixBehavior: string;
  matrixProgress: string;
};

export type NavigationGroup = {
  id: string;
  label: string;
  description?: string;
  trials: DashboardTrial[];
};

export type NavigationSection = {
  id: string;
  label: string;
  order: number;
  groups: NavigationGroup[];
};

export type RecoveryStage = {
  id: string;
  label: string;
  seq: number;
  tone: "failed" | "repair" | "accepted";
  detail: string;
};

const CANONICAL_VIEW_ORDER: ViewId[] = ["trace", "graph", "checks", "subgoals", "jsonl"];

export function parseDashboardBundle(text: string): DashboardBundle {
  const parsed: unknown = JSON.parse(text);
  if (!isRecord(parsed)) {
    throw new Error("The embedded dashboard bundle is not an object.");
  }
  if (parsed.schemaVersion !== "meeting-dashboard.bundle.v1") {
    throw new Error(
      `Unsupported dashboard schema: ${String(parsed.schemaVersion ?? "missing")}`,
    );
  }
  if (!Array.isArray(parsed.trials) || !Array.isArray(parsed.views)) {
    throw new Error("The embedded dashboard bundle has no trial or view index.");
  }
  const bundle = parsed as unknown as DashboardBundle;
  const trialIds = new Set<string>();
  for (const trial of bundle.trials) {
    if (!trial.trialId || trialIds.has(trial.trialId)) {
      throw new Error(`Invalid or duplicate trial ID: ${String(trial.trialId)}`);
    }
    trialIds.add(trial.trialId);
    trial.events = Array.isArray(trial.events) ? trial.events : [];
    trial.checks = Array.isArray(trial.checks) ? trial.checks : [];
    trial.rawRecords = Array.isArray(trial.rawRecords) ? trial.rawRecords : [];
  }
  return bundle;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export const escapeAttribute = escapeHtml;

export function compactText(value: unknown, limit = 150): string {
  const text = displayText(value).replace(/\s+/g, " ").trim();
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, Math.max(0, limit - 3)).trimEnd()}...`;
}

export function displayText(value: unknown): string {
  if (value == null || value === "") {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map(displayText).filter(Boolean).join(" | ");
  }
  if (isRecord(value)) {
    for (const key of ["headline", "label", "title", "description", "text", "summary"]) {
      if (value[key] != null) {
        return displayText(value[key]);
      }
    }
    return JSON.stringify(value);
  }
  return String(value);
}

export function humanize(value: string): string {
  const clean = value.replaceAll(/[-_]+/g, " ").replace(/\s+/g, " ").trim();
  return clean ? clean.charAt(0).toUpperCase() + clean.slice(1) : "Other";
}

export function assignmentLabel(
  assignment: ClassificationAssignment | undefined,
  fallback = "",
): string {
  return assignment?.label || (assignment?.categoryId ? humanize(assignment.categoryId) : fallback);
}

export function classificationAssignments(trial: DashboardTrial): ClassificationAssignment[] {
  const c = trial.classifications ?? {};
  return [
    c.outcome,
    c.successPattern,
    c.failureMode,
    c.progressStage,
    c.failureBehavior,
    ...(c.auditFlags ?? []),
  ].filter((item): item is ClassificationAssignment => Boolean(item));
}

export function evidenceSeqs(assignment: ClassificationAssignment | undefined): number[] {
  if (!assignment?.evidenceRefs) {
    return [];
  }
  const values = assignment.evidenceRefs.flatMap((reference) => {
    if (typeof reference === "number" && Number.isFinite(reference)) {
      return [reference];
    }
    if (typeof reference === "string") {
      const match = reference.match(/(?:seq[:#=\s]*)?(\d+)/i);
      return match ? [Number(match[1])] : [];
    }
    if (isRecord(reference)) {
      const seq = reference.seq ?? reference.eventSeq;
      return typeof seq === "number" && Number.isFinite(seq) ? [seq] : [];
    }
    return [];
  });
  return [...new Set(values)].sort((a, b) => a - b);
}

export function evidenceLabelsForEvent(trial: DashboardTrial, seq: number): string[] {
  const labels = classificationAssignments(trial)
    .filter((assignment) => evidenceSeqs(assignment).includes(seq))
    .map((assignment) => assignmentLabel(assignment))
    .filter(Boolean);

  for (const annotation of trial.annotations ?? []) {
    if (!isRecord(annotation)) {
      continue;
    }
    const refs = Array.isArray(annotation.evidenceRefs)
      ? annotation.evidenceRefs
      : annotation.seq != null
        ? [annotation.seq]
        : [];
    const assignment: ClassificationAssignment = {
      axisId: "annotation",
      categoryId: String(annotation.id ?? annotation.kind ?? "annotation"),
      label: displayText(annotation.label ?? annotation.title ?? annotation.kind ?? "Evidence"),
      evidenceRefs: refs as EvidenceRef[],
    };
    if (evidenceSeqs(assignment).includes(seq)) {
      labels.push(assignment.label);
    }
  }
  return [...new Set(labels)];
}

export function hasSubgoalCapability(trial: DashboardTrial): boolean {
  const extension = trial.extensions?.subgoals;
  return Boolean(
    extension &&
      Array.isArray(extension.nodes) &&
      Array.isArray(extension.frames) &&
      Array.isArray(extension.transitions),
  );
}

export function isRecoveryTrial(trial: DashboardTrial): boolean {
  return trial.classifications?.successPattern?.categoryId.toLowerCase() === "recovery";
}

export function isOneShotTrial(trial: DashboardTrial): boolean {
  const category =
    trial.classifications?.successPattern?.categoryId.toLowerCase().replaceAll("-", "_") ?? "";
  return category.includes("one_shot") || category.includes("oneshot");
}

export function availableViews(trial: DashboardTrial): ViewId[] {
  return CANONICAL_VIEW_ORDER.filter((view) => view !== "subgoals" || hasSubgoalCapability(trial));
}

export function normalizeView(trial: DashboardTrial, value: string): ViewId {
  const requested = value === "json" ? "jsonl" : value;
  const available = availableViews(trial);
  return available.includes(requested as ViewId) ? (requested as ViewId) : "trace";
}

export function findTrial(bundle: DashboardBundle, trialId: string): DashboardTrial | undefined {
  return bundle.trials.find((trial) => trial.trialId === trialId);
}

export function findEvent(
  trial: DashboardTrial,
  reference: string | number,
): DashboardEvent | undefined {
  const normalized = String(reference ?? "").trim();
  if (!normalized) {
    return undefined;
  }
  const seq = Number(normalized.replace(/^#/, ""));
  return trial.events.find(
    (event) => event.eventId === normalized || (Number.isFinite(seq) && event.seq === seq),
  );
}

export function defaultEvent(trial: DashboardTrial): DashboardEvent | undefined {
  const assignments = trial.classifications ?? {};
  const preferred = [
    assignments.failureMode,
    assignments.failureBehavior,
    assignments.successPattern,
    assignments.progressStage,
  ];
  for (const assignment of preferred) {
    const seq = evidenceSeqs(assignment)[0];
    if (seq != null) {
      const event = findEvent(trial, seq);
      if (event) {
        return event;
      }
    }
  }
  const failedCheck = [...trial.checks]
    .filter((check) => check.compiled === false)
    .sort((a, b) => (a.resultSeq ?? a.callSeq) - (b.resultSeq ?? b.callSeq))[0];
  if (failedCheck) {
    return findEvent(trial, failedCheck.resultSeq ?? failedCheck.callSeq);
  }
  return [...trial.events].sort((a, b) => a.seq - b.seq)[0];
}

export function selectedEvent(
  trial: DashboardTrial,
  reference: string | number,
): DashboardEvent | undefined {
  return findEvent(trial, reference) ?? defaultEvent(trial);
}

export function trialHeadline(trial: DashboardTrial): string {
  return (
    displayText(trial.summary) ||
    assignmentLabel(trial.classifications?.failureMode) ||
    assignmentLabel(trial.classifications?.failureBehavior) ||
    assignmentLabel(trial.classifications?.successPattern) ||
    trial.taskId
  );
}

export function trialOutcomeLabel(trial: DashboardTrial): string {
  return (
    assignmentLabel(trial.classifications?.outcome) ||
    displayText(trial.outcome) ||
    humanize(trial.sectionId)
  );
}

export function primaryModeLabel(trial: DashboardTrial): string {
  return (
    assignmentLabel(trial.classifications?.failureMode) ||
    assignmentLabel(trial.classifications?.failureBehavior) ||
    assignmentLabel(trial.classifications?.successPattern) ||
    humanize(trial.groupId)
  );
}

export function routeHref(trialId: string, eventRef: string | number, view: ViewId): string {
  const params = new URLSearchParams();
  params.set("trial", trialId);
  params.set("event", String(eventRef));
  params.set("view", view);
  return `#${params.toString()}`;
}

export function parseRoute(hash: string): Partial<DashboardState> {
  const clean = hash.startsWith("#") ? hash.slice(1) : hash;
  const params = new URLSearchParams(clean);
  return {
    trialId: params.get("trial") ?? "",
    eventRef: params.get("event") ?? "",
    view: (params.get("view") ?? "trace") as ViewId,
  };
}

function taxonomyCategory(
  bundle: DashboardBundle,
  axisId: string | null | undefined,
  categoryId: string,
): TaxonomyCategory | undefined {
  if (!axisId) {
    return undefined;
  }
  return bundle.taxonomies
    .find((taxonomy) => taxonomy.axisId === axisId)
    ?.categories.find((category) => category.categoryId === categoryId);
}

function classificationForCategory(
  trial: DashboardTrial,
  categoryId: string,
): ClassificationAssignment | undefined {
  return classificationAssignments(trial).find(
    (assignment) => assignment.categoryId === categoryId,
  );
}

function declaredSections(bundle: DashboardBundle): NavigationSection[] {
  const indexed = new Map(bundle.trials.map((trial) => [trial.trialId, trial]));
  if (bundle.sections?.length) {
    return [...bundle.sections]
      .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label))
      .map((section) => ({
        id: section.sectionId,
        label: section.label,
        order: section.order,
        groups: [...section.groups]
          .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label))
          .map((group) => ({
            id: group.groupId,
            label: group.label,
            trials: group.trialIds
              .map((trialId) => indexed.get(trialId))
              .filter((trial): trial is DashboardTrial => Boolean(trial))
              .sort((a, b) => a.trialId.localeCompare(b.trialId)),
          }))
          .filter((group) => group.trials.length > 0),
      }))
      .filter((section) => section.groups.length > 0);
  }
  return [...bundle.views]
    .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label))
    .map((view) => {
      const trials = view.trialIds
        .map((trialId) => indexed.get(trialId))
        .filter((trial): trial is DashboardTrial => Boolean(trial));
      const grouped = new Map<string, DashboardTrial[]>();
      for (const trial of trials) {
        const items = grouped.get(trial.groupId) ?? [];
        items.push(trial);
        grouped.set(trial.groupId, items);
      }
      const groups = [...grouped.entries()]
        .map(([groupId, groupTrials]) => {
          const category = taxonomyCategory(bundle, view.groupAxisId, groupId);
          const assignment = classificationForCategory(groupTrials[0], groupId);
          return {
            id: groupId,
            label: category?.label || assignment?.label || humanize(groupId),
            description: category?.description,
            order: category?.order ?? Number.MAX_SAFE_INTEGER,
            trials: [...groupTrials].sort((a, b) => a.trialId.localeCompare(b.trialId)),
          };
        })
        .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label));
      return {
        id: view.id,
        label: view.label,
        order: view.order,
        groups: groups.map(({ id, label, description, trials: groupTrials }) => ({
          id,
          label,
          description,
          trials: groupTrials,
        })),
      };
    })
    .filter((section) => section.groups.some((group) => group.trials.length > 0));
}

function derivedSections(bundle: DashboardBundle): NavigationSection[] {
  const successKind = (trial: DashboardTrial) =>
    trial.classifications?.successPattern?.categoryId.toLowerCase().replaceAll("-", "_") ?? "";
  const buckets: Array<{
    id: string;
    label: string;
    order: number;
    test: (trial: DashboardTrial) => boolean;
  }> = [
    {
      id: "recovery-successes",
      label: "Recovery successes",
      order: 1,
      test: (trial) => successKind(trial).includes("recovery"),
    },
    {
      id: "failure-modes",
      label: "Failure modes",
      order: 2,
      test: (trial) => trial.sectionId === "failures" && !hasSubgoalCapability(trial),
    },
    {
      id: "medium-subgoals",
      label: "Medium subgoal trials",
      order: 3,
      test: (trial) => hasSubgoalCapability(trial),
    },
    {
      id: "one-shot",
      label: "One-shot reference",
      order: 4,
      test: (trial) => successKind(trial).includes("one_shot") || successKind(trial).includes("oneshot"),
    },
  ];
  return buckets
    .map((bucket) => {
      const grouped = new Map<string, DashboardTrial[]>();
      for (const trial of bundle.trials.filter(bucket.test)) {
        const trials = grouped.get(trial.groupId) ?? [];
        trials.push(trial);
        grouped.set(trial.groupId, trials);
      }
      return {
        id: bucket.id,
        label: bucket.label,
        order: bucket.order,
        groups: [...grouped.entries()].map(([id, trials]) => ({
          id,
          label: primaryModeLabel(trials[0]),
          trials: [...trials].sort((a, b) => a.trialId.localeCompare(b.trialId)),
        })),
      };
    })
    .filter((section) => section.groups.length > 0);
}

export function navigationSections(bundle: DashboardBundle): NavigationSection[] {
  const sections = declaredSections(bundle);
  return sections.length > 0 ? sections : derivedSections(bundle);
}

export function sectionForTrial(
  sections: NavigationSection[],
  trialId: string,
): NavigationSection | undefined {
  return sections.find((section) =>
    section.groups.some((group) => group.trials.some((trial) => trial.trialId === trialId)),
  );
}

export function groupForTrial(
  sections: NavigationSection[],
  trialId: string,
): NavigationGroup | undefined {
  return sections
    .flatMap((section) => section.groups)
    .find((group) => group.trials.some((trial) => trial.trialId === trialId));
}

export function recoveryStages(trial: DashboardTrial): RecoveryStage[] {
  if (!isRecoveryTrial(trial)) {
    return [];
  }
  const summary = isRecord(trial.summary) ? trial.summary : {};
  const recovery = isRecord(summary.recovery) ? summary.recovery : {};
  const fallbackFailures = Array.isArray(recovery.failureResultSeqsBeforeAcceptance)
    ? recovery.failureResultSeqsBeforeAcceptance
        .map(finiteNumber)
        .filter((seq): seq is number => seq != null)
        .sort((left, right) => left - right)
    : trial.checks
        .filter((check) => check.compiled === false)
        .map((check) => check.resultSeq ?? check.callSeq)
        .sort((left, right) => left - right);
  const firstFailureSeq = finiteNumber(recovery.firstFailureSeq) ?? fallbackFailures[0] ?? null;
  const lastFailureSeq =
    finiteNumber(recovery.lastFailureSeq) ?? fallbackFailures.at(-1) ?? firstFailureSeq;
  const terminalAcceptanceSeq = finiteNumber(recovery.terminalAcceptanceSeq);
  if (terminalAcceptanceSeq == null) {
    return [];
  }
  const stageDetail = (seq: number, fallback: string) => {
    const check = trial.checks.find((candidate) => candidate.resultSeq === seq);
    const event = findEvent(trial, seq);
    return compactText(check?.diagnostic || event?.text || fallback, 110);
  };
  const stages: RecoveryStage[] = [];
  if (firstFailureSeq != null) {
    stages.push({
      id: `first-failure-${firstFailureSeq}`,
      label: "First failed compiler result",
      seq: firstFailureSeq,
      tone: "failed",
      detail: stageDetail(firstFailureSeq, "The first compiler-rejected candidate."),
    });
  }
  if (lastFailureSeq != null) {
    stages.push({
      id: `last-failure-${lastFailureSeq}`,
      label: "Last failed compiler result",
      seq: lastFailureSeq,
      tone: "failed",
      detail: stageDetail(lastFailureSeq, "The last compiler failure before terminal acceptance."),
    });
  }
  stages.push({
    id: `accepted-${terminalAcceptanceSeq}`,
    label: "Terminal exact-target acceptance",
    seq: terminalAcceptanceSeq,
    tone: "accepted",
    detail: "The later exact-target candidate compiles without prohibited placeholders.",
  });
  return stages.sort((a, b) => a.seq - b.seq || a.label.localeCompare(b.label));
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function recoveryFailureCount(trial: DashboardTrial): number {
  const summary = isRecord(trial.summary) ? trial.summary : {};
  const recovery = isRecord(summary.recovery) ? summary.recovery : {};
  return Array.isArray(recovery.failureResultSeqsBeforeAcceptance)
    ? recovery.failureResultSeqsBeforeAcceptance.length
    : trial.checks.filter((check) => check.compiled === false).length;
}

export function recoveryRegressionNote(trial: DashboardTrial): string {
  const summary = isRecord(trial.summary) ? trial.summary : {};
  const recovery = isRecord(summary.recovery) ? summary.recovery : {};
  return recovery.regressionAfterPass === true
    ? "Earlier pass followed by regression and terminal recovery."
    : "";
}

export function rawRecordForEvent(
  trial: DashboardTrial,
  event: DashboardEvent | undefined,
): RawRecord | undefined {
  if (!event || event.rawRecordIndex < 0) {
    return undefined;
  }
  return trial.rawRecords[event.rawRecordIndex];
}

export function exactJsonLine(record: RawRecord): string {
  return JSON.stringify(record.value);
}

export function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "not recorded";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) {
    return value;
  }
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function statusTone(value: string | boolean | null | undefined): string {
  const normalized = String(value ?? "unknown").toLowerCase();
  if (["true", "pass", "passed", "accepted", "solved", "matched", "approve"].includes(normalized)) {
    return "pass";
  }
  if (
    ["false", "fail", "failed", "rejected", "blocked", "gap", "unsolved", "unresolved", "violation", "silent_failure"].includes(
      normalized,
    )
  ) {
    return "fail";
  }
  if (["active", "candidate", "recovery", "repair", "warning"].includes(normalized)) {
    return "active";
  }
  return "neutral";
}
