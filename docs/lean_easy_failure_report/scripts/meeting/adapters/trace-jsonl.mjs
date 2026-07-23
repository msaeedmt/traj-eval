import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { relative, resolve } from "node:path";

export function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

export function toRepoRelative(repoRoot, path) {
  return relative(repoRoot, path).replaceAll("\\", "/");
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function createPublicSanitizer({ repoRoot }) {
  const leanSourcePlaceholder = "<sanitized-lean-source>";
  const resolvedRoot = resolve(repoRoot);
  const doubledRootPattern = new RegExp(
    escapeRegExp(resolvedRoot.replaceAll("\\", "\\\\")),
    "gi",
  );
  const rootPattern = new RegExp(escapeRegExp(resolvedRoot), "gi");
  const tempPathPattern = new RegExp(
    String.raw`\.traj_eval_tmp(?:\\{1,2}|/)check_[A-Za-z0-9_-]+\.lean`,
    "gi",
  );
  const tempFileNamePattern = /check_[A-Za-z0-9_-]+\.lean/gi;
  const legacyTempPlaceholderPattern = /<lean-temp>\.lean/gi;
  let replacementCount = 0;

  function sanitizeString(value) {
    let next = value.replace(legacyTempPlaceholderPattern, () => {
      replacementCount += 1;
      return leanSourcePlaceholder;
    });
    next = next.replace(tempPathPattern, () => {
      replacementCount += 1;
      return leanSourcePlaceholder;
    });
    next = next.replace(tempFileNamePattern, () => {
      replacementCount += 1;
      return leanSourcePlaceholder;
    });
    next = next.replace(doubledRootPattern, () => {
      replacementCount += 1;
      return "<repo-root>";
    });
    next = next.replace(rootPattern, () => {
      replacementCount += 1;
      return "<repo-root>";
    });
    return next;
  }

  function sanitize(value) {
    if (typeof value === "string") {
      return sanitizeString(value);
    }
    if (Array.isArray(value)) {
      return value.map(sanitize);
    }
    if (value && typeof value === "object") {
      return Object.fromEntries(
        Object.entries(value).map(([key, nested]) => [key, sanitize(nested)]),
      );
    }
    return value;
  }

  return {
    sanitize,
    get replacementCount() {
      return replacementCount;
    },
  };
}

export function sanitizeValue(value, options) {
  return createPublicSanitizer(options).sanitize(value);
}

function parseArguments(raw) {
  if (typeof raw !== "string" || !raw.trim()) {
    return null;
  }
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function normalizeEvent(record, rawRecordIndex) {
  const payload = record.payload ?? {};
  const toolCalls = (payload.tool_calls ?? []).map((call) => ({
    id: call.id ?? null,
    name: call.name ?? null,
    argumentsRaw: call.arguments ?? null,
    arguments: parseArguments(call.arguments),
  }));
  const toolResponses = (payload.tool_responses ?? []).map((response) => ({
    id: response.id ?? null,
    contentRaw: response.content ?? null,
  }));
  return {
    eventId: record.event_id,
    seq: record.seq,
    timestamp: record.timestamp ?? null,
    kind: record.event_type,
    role: record.agent_role,
    causedBy: Array.isArray(record.caused_by) ? record.caused_by : [],
    rawRecordIndex,
    text: payload.text ?? null,
    toolCalls,
    toolResponses,
    phase: payload.phase ?? null,
  };
}

function validateTrial(header, events, sourcePath) {
  const issues = [];
  const add = (severity, code, message, extra = {}) =>
    issues.push({ severity, code, message, sourcePath, trialId: header.trial_id, ...extra });

  if (!header.trial_id || !header.task_id) {
    add("error", "invalid_trial_header", "Trial header requires trial_id and task_id.");
  }
  const eventIds = new Set();
  const sequences = new Set();
  let previousSeq = -Infinity;
  for (const event of events) {
    if (!event.eventId) {
      add("error", "missing_event_id", `Event at seq ${event.seq} has no event_id.`);
      continue;
    }
    if (eventIds.has(event.eventId)) {
      add("error", "duplicate_event_id", `Duplicate event_id ${event.eventId}.`);
    }
    eventIds.add(event.eventId);
    if (sequences.has(event.seq)) {
      add("error", "duplicate_event_seq", `Duplicate event seq ${event.seq}.`);
    }
    sequences.add(event.seq);
    if (event.seq < previousSeq) {
      add("error", "non_monotonic_seq", `Event seq ${event.seq} is out of order.`);
    }
    previousSeq = event.seq;
  }
  for (const event of events) {
    for (const parent of event.causedBy) {
      if (!eventIds.has(parent)) {
        add(
          "warning",
          "missing_causal_parent",
          `Event ${event.eventId} references missing parent ${parent}.`,
          { eventId: event.eventId },
        );
      }
    }
  }
  return issues;
}

function readTrial(path, repoRoot, experimentId) {
  const sourceText = readFileSync(path, "utf8");
  const lines = sourceText.split(/\r?\n/).filter((line) => line.trim());
  if (lines.length < 2) {
    throw new Error(`Trace must contain a header and at least one event: ${path}`);
  }
  const parsed = lines.map((line, index) => {
    try {
      return JSON.parse(line);
    } catch (error) {
      throw new Error(`Invalid JSON at ${path}:${index + 1}: ${error.message}`);
    }
  });
  const sanitizer = createPublicSanitizer({ repoRoot });
  const sanitized = parsed.map((record) => sanitizer.sanitize(record));
  const [header, ...eventRecords] = sanitized;
  const rawRecords = sanitized.map((value, index) => ({
    lineNumber: index + 1,
    kind: index === 0 ? "header" : "event",
    value,
  }));
  const events = eventRecords.map((record, index) => normalizeEvent(record, index + 1));
  const sourcePath = toRepoRelative(repoRoot, path);
  const sourceRef = `source:${experimentId}:${header.trial_id}`;
  const graph = {
    nodes: events.map((event) => ({
      id: event.eventId,
      eventId: event.eventId,
      seq: event.seq,
      role: event.role,
      kind: event.kind,
      label: `${event.seq}: ${event.role}`,
    })),
    edges: events.flatMap((event) =>
      event.causedBy.map((parent) => ({ source: parent, target: event.eventId })),
    ),
  };
  const issues = validateTrial(header, events, sourcePath);
  const publishedText = rawRecords.map((record) => JSON.stringify(record.value)).join("\n");

  return {
    trial: {
      trialId: header.trial_id,
      experimentId,
      taskId: header.task_id,
      trialNumber: Number(header.trial_id.match(/_t(\d+)$/)?.[1] ?? NaN),
      source: null,
      difficulty: null,
      sectionId: null,
      groupId: null,
      metadata: {
        schemaVersion: header.schema_version ?? null,
        testbed: header.testbed ?? null,
        architecture: header.architecture ?? null,
        backbone: header.backbone ?? null,
        grounding: header.grounding ?? null,
        stressLevel: header.stress_level ?? null,
        startedAt: header.started_at ?? null,
        config: header.config ?? {},
      },
      outcome: {},
      classifications: { auditFlags: [] },
      summary: {
        eventCount: events.length,
        causalEdgeCount: graph.edges.length,
        toolCallCount: events.reduce((sum, event) => sum + event.toolCalls.length, 0),
      },
      rawRecords,
      events,
      checks: [],
      graph,
      annotations: [],
      extensions: {},
      provenance: {
        sourceRef,
        analysisRefs: [],
        adapter: { id: "trace-jsonl", version: "1.0.0" },
        enrichers: [],
      },
    },
    sourceFile: {
      sourceRef,
      experimentId,
      trialId: header.trial_id,
      path: sourcePath,
      format: "jsonl",
      schemaVersion: header.schema_version ?? null,
      recordCount: rawRecords.length,
      eventCount: events.length,
      rawSha256: sha256(sourceText),
      publishedSha256: sha256(publishedText),
      sanitizationCount: sanitizer.replacementCount,
    },
    issues,
  };
}

export function loadTraceJsonlExperiment({ repoRoot, experimentSpec }) {
  const directory = resolve(repoRoot, experimentSpec.rawDir);
  if (!existsSync(directory)) {
    throw new Error(`Missing experiment trace directory: ${directory}`);
  }
  const paths = readdirSync(directory)
    .filter((name) => name.endsWith(".jsonl"))
    .sort()
    .map((name) => resolve(directory, name));
  const loaded = paths.map((path) => readTrial(path, repoRoot, experimentSpec.id));
  const trialIds = loaded.map(({ trial }) => trial.trialId);
  if (new Set(trialIds).size !== trialIds.length) {
    throw new Error(`Experiment ${experimentSpec.id} contains duplicate trial IDs.`);
  }
  return {
    experiment: {
      id: experimentSpec.id,
      label: experimentSpec.label,
      description: experimentSpec.description,
      order: experimentSpec.order,
      capabilities: [...experimentSpec.capabilities],
      trialIds,
      metrics: {},
      sourceRefs: loaded.map(({ sourceFile }) => sourceFile.sourceRef),
    },
    trials: loaded.map(({ trial }) => trial),
    sourceFiles: loaded.map(({ sourceFile }) => sourceFile),
    issues: loaded.flatMap(({ issues }) => issues),
  };
}
