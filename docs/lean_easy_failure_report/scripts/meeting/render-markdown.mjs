import { writeFile } from "node:fs/promises";

const HTML_FILE = "lean_failure_modes_meeting.html";

const EASY_MODE_ORDER = [
  "statement-drift",
  "opaque-verifier-feedback",
  "application-type-mismatch",
  "typeclass-resolution",
  "unknown-mathlib-api",
  "target-not-attempted",
];

const MEDIUM_BEHAVIOR_ORDER = [
  "formalization-interface-barrier",
  "search-recovery-loop",
  "subgoal-scope-mismatch",
  "critic-acceptance-mismatch",
  "handoff-without-execution",
];

const PROGRESS_STAGES = ["P0", "P1", "P2", "P3", "P4", "P5"];

function requireBundle(bundle) {
  if (!bundle || typeof bundle !== "object" || !Array.isArray(bundle.trials)) {
    throw new TypeError("renderMeetingMarkdown requires a meeting bundle with a trials array");
  }
}

function text(value, fallback = "") {
  if (value === null || value === undefined) return fallback;
  return String(value);
}

function markdownCell(value) {
  return text(value, "—")
    .replaceAll("\r", " ")
    .replaceAll("\n", " ")
    .replaceAll("|", "\\|")
    .trim() || "—";
}

function labelOf(classification, fallback = "Unclassified") {
  if (!classification) return fallback;
  if (typeof classification === "string") return classification;
  return (
    classification.label ??
    classification.name ??
    classification.categoryLabel ??
    classification.categoryId ??
    classification.id ??
    fallback
  );
}

function idOf(classification, fallback = "unclassified") {
  if (!classification) return fallback;
  if (typeof classification === "string") return classification;
  return classification.categoryId ?? classification.id ?? classification.stageId ?? fallback;
}

function stageOf(trial) {
  const stage = trial?.classifications?.progressStage;
  if (typeof stage === "string" && /^P[0-5]$/i.test(stage)) return stage.toUpperCase();
  if (stage?.stageCode) return String(stage.stageCode).toUpperCase();
  const candidate =
    stage?.stageId ?? stage?.label ?? stage?.categoryId ?? stage?.id ?? trial?.summary?.progressStage;
  const match = String(candidate ?? "").match(/\bP([0-5])\b/i) ??
    String(candidate ?? "").match(/^p([0-5])-/i);
  return match ? `P${match[1]}` : "P0";
}

function edgeCount(trial) {
  if (Array.isArray(trial?.graph?.edges)) return trial.graph.edges.length;
  if (Array.isArray(trial?.causalEdges)) return trial.causalEdges.length;
  return 0;
}

function recoveryOf(trial) {
  return trial?.summary?.recovery ?? {};
}

function isRecovery(trial) {
  return idOf(trial?.classifications?.successPattern) === "recovery";
}

function isMedium(trial) {
  return (
    trial?.difficulty === "medium" ||
    trial?.sectionId === "medium-failures" ||
    Boolean(trial?.classifications?.failureBehavior) ||
    Boolean(trial?.extensions?.subgoals)
  );
}

function isEasyFailure(trial) {
  return Boolean(trial?.classifications?.failureMode);
}

function traceLink(trialId, event, view = "trace", label = trialId) {
  const hash = new URLSearchParams({
    trial: trialId,
    event: text(event, "0"),
    view,
  });
  return `[${markdownCell(label)}](${HTML_FILE}#${hash.toString()})`;
}

function firstEventSeq(trial) {
  return trial?.events?.[0]?.seq ?? 0;
}

function terminalEventSeq(trial) {
  const recovery = recoveryOf(trial);
  return (
    recovery.terminalAcceptanceSeq ??
    trial?.summary?.terminalAcceptanceSeq ??
    trial?.events?.at(-1)?.seq ??
    firstEventSeq(trial)
  );
}

function trialList(trials, view = "trace") {
  if (!trials.length) return "—";
  return trials
    .slice()
    .sort((a, b) => a.trialId.localeCompare(b.trialId))
    .map((trial) => traceLink(trial.trialId, terminalEventSeq(trial), view, trial.trialId))
    .join(", ");
}

function taxonomyAxis(bundle, axisId) {
  const taxonomies = Array.isArray(bundle.taxonomies)
    ? bundle.taxonomies
    : Object.values(bundle.taxonomies ?? {});
  return taxonomies.find((axis) => axis?.axisId === axisId || axis?.id === axisId);
}

function categoryDefinitions(bundle, axisId) {
  const axis = taxonomyAxis(bundle, axisId);
  if (!axis) return [];
  if (Array.isArray(axis.categories)) return axis.categories;
  if (Array.isArray(axis.values)) return axis.values;
  return Object.entries(axis.categories ?? axis.values ?? {}).map(([categoryId, value]) => ({
    categoryId,
    ...(typeof value === "object" ? value : { label: value }),
  }));
}

function orderedGroups(trials, classificationKey, preferredIds, bundle, axisId) {
  const definitionById = new Map(
    categoryDefinitions(bundle, axisId).map((category) => [
      category.categoryId ?? category.id,
      category,
    ]),
  );
  const groups = new Map();

  for (const trial of trials) {
    const classification = trial?.classifications?.[classificationKey];
    const categoryId = idOf(classification);
    if (!groups.has(categoryId)) {
      groups.set(categoryId, {
        categoryId,
        label: labelOf(classification, labelOf(definitionById.get(categoryId), categoryId)),
        trials: [],
      });
    }
    groups.get(categoryId).trials.push(trial);
  }

  const rank = new Map(preferredIds.map((id, index) => [id, index]));
  return [...groups.values()].sort((a, b) => {
    const left = rank.get(a.categoryId) ?? Number.MAX_SAFE_INTEGER;
    const right = rank.get(b.categoryId) ?? Number.MAX_SAFE_INTEGER;
    return left - right || a.label.localeCompare(b.label);
  });
}

function progressCounts(mediumTrials) {
  return Object.fromEntries(
    PROGRESS_STAGES.map((stage) => [
      stage,
      mediumTrials.filter((trial) => stageOf(trial) === stage).length,
    ]),
  );
}

function subgoalCounts(trial) {
  const extension = trial?.extensions?.subgoals ?? {};
  const nodes = Array.isArray(extension.nodes) ? extension.nodes : [];
  const progress = extension.progress ?? {};
  const summary = trial?.summary ?? {};

  const accepted = nodes.filter((node) => {
    const status = text(node?.terminalStatus ?? node?.status ?? node?.state).toLowerCase();
    return status === "accepted" || status === "ledger-accepted";
  }).length;

  return {
    defined: Number(
      progress.defined ?? summary.subgoalsDefined ?? summary.definedCount ?? nodes.length ?? 0
    ),
    attempted: Number(
      progress.attempted ??
      summary.subgoalsAttempted ??
      summary.attemptedCount ??
      nodes.filter((node) => node?.attempted || node?.attempts > 0 || node?.attemptCount > 0).length ??
      0
    ),
    ledgerAccepted: Number(
      progress.ledgerAccepted ??
      summary.subgoalsAccepted ??
      summary.ledgerAcceptedCount ??
      accepted
    ),
    replayStatus: extension?.replayValidation?.status ?? "unavailable",
  };
}

function safeProvenancePaths(bundle) {
  const candidates = [];
  const visit = (value, key = "") => {
    if (value === null || value === undefined) return;
    if (typeof value === "string") {
      if (/path|file|source/i.test(key) && !/^[A-Za-z]:[\\/]/.test(value) && !value.startsWith("/")) {
        candidates.push(value.replaceAll("\\", "/"));
      }
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((entry) => visit(entry, key));
      return;
    }
    if (typeof value === "object") {
      Object.entries(value).forEach(([childKey, child]) => visit(child, childKey));
    }
  };
  visit(bundle.provenance);
  bundle.experiments?.forEach((experiment) => visit(experiment?.provenance ?? experiment?.source));
  return [...new Set(candidates)].filter(Boolean).sort();
}

function provenanceFamilies(paths) {
  const counts = new Map();
  for (const path of paths) {
    const slash = path.lastIndexOf("/");
    if (slash < 0) continue;
    const directory = path.slice(0, slash);
    counts.set(directory, (counts.get(directory) ?? 0) + 1);
  }
  return [...counts.entries()].sort(([left], [right]) => left.localeCompare(right));
}

function renderScope(bundle) {
  const events = bundle.trials.reduce((sum, trial) => sum + (trial.events?.length ?? 0), 0);
  const edges = bundle.trials.reduce((sum, trial) => sum + edgeCount(trial), 0);
  const recovery = bundle.trials.filter(isRecovery);
  const medium = bundle.trials.filter(isMedium);
  const easyFailures = bundle.trials.filter(isEasyFailure);
  const contrast = bundle.trials.filter(
    (trial) => trial.trialId === "easy_fatem_011_t0" || trial.sectionId === "one-shot-contrast",
  );

  return {
    trials: bundle.scope?.trialCount ?? bundle.trials.length,
    events: bundle.scope?.eventCount ?? events,
    edges: bundle.scope?.causalEdgeCount ?? edges,
    recovery: bundle.scope?.recoverySuccessCount ?? recovery.length,
    medium: bundle.scope?.mediumFailureCount ?? medium.length,
    easyFailures: bundle.scope?.easyFailureCount ?? easyFailures.length,
    contrast: bundle.scope?.oneShotExemplarCount ?? contrast.length,
  };
}

export function renderMeetingMarkdown(bundle) {
  requireBundle(bundle);

  const scope = renderScope(bundle);
  const recoveries = bundle.trials.filter(isRecovery);
  const easyFailures = bundle.trials.filter(isEasyFailure);
  const mediumTrials = bundle.trials.filter(isMedium);
  const contrast =
    bundle.trials.find((trial) => trial.trialId === "easy_fatem_011_t0") ??
    bundle.trials.find((trial) => trial.sectionId === "one-shot-contrast");

  const easyGroups = orderedGroups(
    easyFailures,
    "failureMode",
    EASY_MODE_ORDER,
    bundle,
    "easy-failure-mode",
  );
  const mediumGroups = orderedGroups(
    mediumTrials,
    "failureBehavior",
    MEDIUM_BEHAVIOR_ORDER,
    bundle,
    "medium-failure-behavior",
  );
  const progress = progressCounts(mediumTrials);

  const lines = [
    "# Lean failure and recovery traces",
    "",
    "> Meeting report generated from the same validated bundle as the offline dashboard. Raw JSONL records remain separate from reviewed classifications and reconstructed progress.",
    "",
    "## Evidence scope",
    "",
    "| Complete trace cohort | Trials |",
    "|---|---:|",
    `| Easy failures | ${scope.easyFailures} |`,
    `| Medium failures with subgoal tools | ${scope.medium} |`,
    `| Recovery successes | ${scope.recovery} |`,
    `| One-shot contrast | ${scope.contrast} |`,
    `| **Total** | **${scope.trials}** |`,
    "",
    `The bundle contains **${scope.events.toLocaleString("en-US")} events** and **${scope.edges.toLocaleString("en-US")} causal edges**. Open [the interactive offline dashboard](${HTML_FILE}) to inspect exact source records, synchronized role graphs, Lean checks, and event payloads.`,
    "",
    "## Recovery after compiler failure",
    "",
    "A recovery is a kernel-confirmed exact-target run where at least one failed compiler result precedes the terminal selected exact-target acceptance. This includes a run that compiled early, regressed, and later recovered.",
    "",
    `**${recoveries.length} complete recovery traces.** ${contrast ? `Use ${traceLink(contrast.trialId, firstEventSeq(contrast), "trace", "easy_fatem_011_t0")} as the one-shot contrast.` : ""}`,
    "",
    "| Task | Trial | Recovery path |",
    "|---|---|---|",
  ];

  for (const trial of recoveries.slice().sort((a, b) => {
    return a.taskId.localeCompare(b.taskId) || a.trialId.localeCompare(b.trialId);
  })) {
    const recovery = recoveryOf(trial);
    const failures = recovery.failureResultSeqsBeforeAcceptance?.length ?? 0;
    const regression = recovery.regressionAfterPass
      ? " Earlier pass, regression, then terminal recovery."
      : "";
    const path = [
      traceLink(trial.trialId, recovery.firstFailureSeq, "trace", `first failure #${recovery.firstFailureSeq}`),
      traceLink(trial.trialId, recovery.lastFailureSeq, "trace", `last failure #${recovery.lastFailureSeq}`),
      traceLink(
        trial.trialId,
        recovery.terminalAcceptanceSeq,
        "trace",
        `accepted #${recovery.terminalAcceptanceSeq}`,
      ),
    ].join(" → ");

    lines.push(
      `| ${markdownCell(trial.taskId)} | ${traceLink(trial.trialId, recovery.firstFailureSeq, "trace", trial.trialId)} | ${failures} failed check${failures === 1 ? "" : "s"}; ${path}.${regression} |`,
    );
  }

  lines.push(
    "",
    "## Easy failure modes",
    "",
    "The 44 easy failures form a reviewed partition. Labels below are enrichments anchored to raw event evidence, not fields copied from the source JSONL.",
    "",
    "| Reviewed failure mode | Count | Complete trace index |",
    "|---|---:|---|",
  );

  for (const group of easyGroups) {
    lines.push(
      `| ${markdownCell(group.label)} | ${group.trials.length} | ${trialList(group.trials)} |`,
    );
  }

  lines.push(
    "",
    "## Medium failures: behavior × controller progress",
    "",
    "Each medium trial has two labels: a dominant observed failure behavior and a controller-progress stage. Progress is reconstructed from the subgoal tool ledger and is not a proof-completion percentage.",
    "",
    "| Failure behavior | P0 | P1 | P2 | P3 | P4 | P5 | Total |",
    "|---|---:|---:|---:|---:|---:|---:|---:|",
  );

  for (const group of mediumGroups) {
    const row = Object.fromEntries(
      PROGRESS_STAGES.map((stage) => [
        stage,
        group.trials.filter((trial) => stageOf(trial) === stage).length,
      ]),
    );
    lines.push(
      `| ${markdownCell(group.label)} | ${PROGRESS_STAGES.map((stage) => row[stage]).join(" | ")} | ${group.trials.length} |`,
    );
  }

  lines.push(
    `| **Total** | ${PROGRESS_STAGES.map((stage) => `**${progress[stage]}**`).join(" | ")} | **${mediumTrials.length}** |`,
    "",
    "### Medium trace index",
    "",
    "| Trial | Behavior | Stage | Subgoals: defined / attempted / ledger accepted | Replay |",
    "|---|---|---:|---:|---|",
  );

  for (const trial of mediumTrials.slice().sort((a, b) => a.trialId.localeCompare(b.trialId))) {
    const counts = subgoalCounts(trial);
    lines.push(
      `| ${traceLink(trial.trialId, firstEventSeq(trial), "subgoals", trial.trialId)} | ${markdownCell(labelOf(trial.classifications.failureBehavior))} | ${markdownCell(stageOf(trial))} | ${counts.defined} / ${counts.attempted} / ${counts.ledgerAccepted} | ${markdownCell(counts.replayStatus)} |`,
    );
  }

  lines.push(
    "",
    "“Ledger accepted” means that the recorded controller ledger accepted the subgoal. It does **not** mean independently proved. P5 is reserved for an independently verified final theorem.",
    "",
    "## How to verify a statement",
    "",
    "1. Follow a trial link into the dashboard.",
    "2. Select the labeled decisive event in **Trace** or the synchronized node in **Role graph**.",
    "3. Inspect **Checks** for candidate kind, statement match, result, and diagnostic.",
    "4. Open **Exact JSONL** for the complete sanitized source record and its causal parents.",
    "5. For medium trials, compare **Subgoals** replay with the recorded terminal ledger and heed any replay-gap warning.",
    "",
    "## Provenance and interpretation",
    "",
    `- Bundle schema: \`${markdownCell(bundle.schemaVersion ?? "unspecified")}\`.`,
    `- Bundle validation: **${bundle.validation?.ok === false ? "failed" : "passed"}**; ${(bundle.validation?.issues ?? []).filter((issue) => issue.severity === "error").length} errors and ${(bundle.validation?.issues ?? []).filter((issue) => issue.severity !== "error").length} retained warnings.`,
    "- Source records, normalized views, and reviewed enrichments are stored as separate layers.",
    "- Recovery uses ordered compiler and exact-target acceptance evidence; it is not inferred from the final outcome label alone.",
    "- Medium behavior is a dominant observed trace pattern, not a complete causal explanation.",
    "- Role-graph edges represent event `caused_by` relations. Subgoal edges represent `depends_on`; the two graphs are not interchangeable.",
  );

  const provenancePaths = safeProvenancePaths(bundle);
  if (provenancePaths.length) {
    lines.push(
      "",
      `Registered provenance is embedded in the dashboard (${provenancePaths.length} relative references). Source-file families:`,
      "",
    );
    provenanceFamilies(provenancePaths).forEach(([directory, count]) =>
      lines.push(`- \`${markdownCell(directory)}/\` — ${count} file${count === 1 ? "" : "s"}`),
    );
  }

  lines.push(
    "",
    "Build and extension details are documented in [`MEETING_DASHBOARD_BUILD.md`](MEETING_DASHBOARD_BUILD.md).",
    "",
  );

  return lines.join("\n");
}

export async function writeMeetingMarkdown(bundleOrOptions, maybeOutputPath) {
  const bundle = bundleOrOptions?.bundle ?? bundleOrOptions;
  const outputPath = bundleOrOptions?.outputPath ?? maybeOutputPath;
  if (!outputPath) {
    throw new TypeError("writeMeetingMarkdown requires an outputPath");
  }
  const markdown = renderMeetingMarkdown(bundle);
  await writeFile(outputPath, markdown, "utf8");
  return markdown;
}
