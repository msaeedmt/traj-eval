import {
  BUNDLE_SCHEMA_VERSION,
  BUILD_VERSION,
  EASY_FAILURE_MODES,
  EXPECTED_SCOPE,
  MEETING_EXPERIMENTS,
  MEDIUM_FAILURE_BEHAVIORS,
  MEDIUM_PROGRESS_STAGES,
  METRIC_DEFINITIONS,
  ONE_SHOT_EXEMPLAR_ID,
  RECOVERY_TRIAL_IDS,
  TAXONOMIES,
  VIEWS,
} from "../../config/meeting-experiments.mjs";
import { loadTraceJsonlExperiment, sha256 } from "./adapters/trace-jsonl.mjs";
import { enrichEasyTrials } from "./enrichers/easy-analysis.mjs";
import { enrichMediumSubgoalTrials } from "./enrichers/subgoals.mjs";
import { applyMeetingTaxonomy } from "./enrichers/taxonomy.mjs";

export const ADAPTER_REGISTRY = Object.freeze({
  "trace-jsonl": loadTraceJsonlExperiment,
});

export const ENRICHER_REGISTRY = Object.freeze({
  "easy-analysis": ({ repoRoot, experimentSpec, trials, options }) =>
    enrichEasyTrials({
      repoRoot,
      experimentSpec,
      trials,
      recoveryTrialIds: options.recoveryTrialIds ?? [],
      oneShotExemplarId: options.oneShotExemplarId ?? null,
    }),
  "subgoal-ledger-replay": ({ repoRoot, experimentSpec, trials }) =>
    enrichMediumSubgoalTrials({ repoRoot, experimentSpec, trials }),
});

function countBy(items, key) {
  const counts = {};
  for (const item of items) {
    const value = typeof key === "function" ? key(item) : item[key];
    const normalized = value ?? "unclassified";
    counts[normalized] = (counts[normalized] ?? 0) + 1;
  }
  return Object.fromEntries(Object.entries(counts).sort(([left], [right]) => left.localeCompare(right)));
}

function expectedCheck(issues, checkId, expected, observed) {
  const status = JSON.stringify(expected) === JSON.stringify(observed) ? "passed" : "failed";
  if (status === "failed") {
    issues.push({
      severity: "error",
      code: checkId,
      message: `Expected ${JSON.stringify(expected)}; observed ${JSON.stringify(observed)}.`,
    });
  }
  return { checkId, status, expected, observed };
}

function categoryCounts(trials, field) {
  return countBy(trials, (trial) => trial.classifications[field]?.categoryId ?? null);
}

function sectionDefinitions(trials) {
  const sectionSpecs = [
    { sectionId: "failures", label: "Failure modes", order: 1 },
    { sectionId: "successes", label: "Success contrasts", order: 2 },
  ];
  return sectionSpecs.map((section) => {
    const sectionTrials = trials.filter((trial) => trial.sectionId === section.sectionId);
    const byGroup = new Map();
    for (const trial of sectionTrials) {
      const classification =
        trial.classifications.failureMode ??
        trial.classifications.failureBehavior ??
        trial.classifications.successPattern;
      if (!classification) continue;
      const existing = byGroup.get(trial.groupId) ?? {
        groupId: trial.groupId,
        label: classification.label,
        axisId: classification.axisId,
        order: classification.order,
        trialIds: [],
      };
      existing.trialIds.push(trial.trialId);
      byGroup.set(trial.groupId, existing);
    }
    const groups = [...byGroup.values()]
      .map((group) => ({
        ...group,
        trialIds: group.trialIds.sort(),
        count: group.trialIds.length,
      }))
      .sort((left, right) => left.order - right.order || left.label.localeCompare(right.label));
    return {
      ...section,
      count: sectionTrials.length,
      trialIds: sectionTrials.map((trial) => trial.trialId).sort(),
      groups,
    };
  });
}

function experimentMetrics(experimentSpec, trials, indexes) {
  if (experimentSpec.metricProfile === "validated-target") {
    const failures = trials.filter((trial) => trial.sectionId === "failures");
    const recoveries = trials.filter(
      (trial) => trial.classifications.successPattern?.categoryId === "recovery",
    );
    return {
      embeddedTrialCount: trials.length,
      failureCount: failures.length,
      recoverySuccessCount: recoveries.length,
      oneShotExemplarCount: trials.filter(
        (trial) => trial.classifications.successPattern?.categoryId === "one-shot",
      ).length,
      oneShotIndexCount: indexes.oneShotSuccesses.length,
      outcomeCounts: categoryCounts(trials, "outcome"),
      failureModeCounts: categoryCounts(failures, "failureMode"),
    };
  }
  if (experimentSpec.metricProfile !== "subgoal-ledger") {
    return {
      embeddedTrialCount: trials.length,
      outcomeCounts: categoryCounts(trials, "outcome"),
    };
  }
  const nodes = trials.flatMap((trial) => trial.extensions.subgoals?.nodes ?? []);
  const matrix = {};
  for (const behavior of MEDIUM_FAILURE_BEHAVIORS) {
    matrix[behavior.categoryId] = {};
    for (const stage of MEDIUM_PROGRESS_STAGES) {
      matrix[behavior.categoryId][stage.categoryId] = trials.filter(
        (trial) =>
          trial.classifications.failureBehavior?.categoryId === behavior.categoryId &&
          trial.classifications.progressStage?.categoryId === stage.categoryId,
      ).length;
    }
  }
  return {
    embeddedTrialCount: trials.length,
    verifiedCompletionCount: trials.filter((trial) => trial.outcome.verifiedCompletion).length,
    compilerCallCount: trials.reduce((sum, trial) => sum + trial.checks.length, 0),
    returnedCompilerResultCount: trials.reduce(
      (sum, trial) => sum + trial.checks.filter((check) => check.matched).length,
      0,
    ),
    unmatchedCompilerCallCount: trials.reduce(
      (sum, trial) => sum + trial.checks.filter((check) => !check.matched).length,
      0,
    ),
    subgoalsDefined: nodes.length,
    subgoalsAttempted: nodes.filter((node) => node.attempts > 0).length,
    ledgerAcceptedNodes: nodes.filter((node) => node.status === "accepted").length,
    progressStageCounts: categoryCounts(trials, "progressStage"),
    failureBehaviorCounts: categoryCounts(trials, "failureBehavior"),
    progressByFailureBehavior: matrix,
  };
}

function selectedSourceFiles(sourceFiles, trials, analysisRefs) {
  const trialIds = new Set(trials.map((trial) => trial.trialId));
  return sourceFiles.filter(
    (source) =>
      source.trialId == null || trialIds.has(source.trialId) || analysisRefs.has(source.sourceRef),
  );
}

function countAbsoluteWindowsPaths(value) {
  if (typeof value === "string") {
    return /\b[A-Za-z]:[\\/]/.test(value) ? 1 : 0;
  }
  if (Array.isArray(value)) {
    return value.reduce((sum, item) => sum + countAbsoluteWindowsPaths(item), 0);
  }
  if (value && typeof value === "object") {
    return Object.values(value).reduce(
      (sum, item) => sum + countAbsoluteWindowsPaths(item),
      0,
    );
  }
  return 0;
}

function addValidation({ bundleCore, issues }) {
  const trials = bundleCore.trials;
  const checks = [];
  const scope = bundleCore.scope;
  for (const [key, expected] of Object.entries(EXPECTED_SCOPE)) {
    checks.push(expectedCheck(issues, `scope_${key}`, expected, scope[key]));
  }
  const recoveryIds = trials
    .filter((trial) => trial.classifications.successPattern?.categoryId === "recovery")
    .map((trial) => trial.trialId)
    .sort();
  checks.push(
    expectedCheck(issues, "recovery_trial_ids", [...RECOVERY_TRIAL_IDS].sort(), recoveryIds),
  );
  checks.push(
    expectedCheck(
      issues,
      "one_shot_index_count",
      39,
      bundleCore.indexes.oneShotSuccesses.length,
    ),
  );
  const easyFailures = trials.filter((trial) => trial.classifications.failureMode);
  const easyModeCounts = categoryCounts(easyFailures, "failureMode");
  for (const mode of EASY_FAILURE_MODES) {
    checks.push(
      expectedCheck(
        issues,
        `easy_mode_${mode.categoryId}`,
        mode.expectedCount,
        easyModeCounts[mode.categoryId] ?? 0,
      ),
    );
  }
  const medium = trials.filter((trial) => trial.classifications.progressStage);
  const stageCounts = categoryCounts(medium, "progressStage");
  const behaviorCounts = categoryCounts(medium, "failureBehavior");
  for (const stage of MEDIUM_PROGRESS_STAGES) {
    checks.push(
      expectedCheck(
        issues,
        `medium_stage_${stage.categoryId}`,
        stage.expectedCount,
        stageCounts[stage.categoryId] ?? 0,
      ),
    );
  }
  for (const behavior of MEDIUM_FAILURE_BEHAVIORS) {
    checks.push(
      expectedCheck(
        issues,
        `medium_behavior_${behavior.categoryId}`,
        behavior.expectedCount,
        behaviorCounts[behavior.categoryId] ?? 0,
      ),
    );
  }
  checks.push(
    expectedCheck(
      issues,
      "medium_replay_matches",
      20,
      medium.filter(
        (trial) => trial.extensions.subgoals?.replayValidation?.status === "matched",
      ).length,
    ),
  );
  checks.push(
    expectedCheck(
      issues,
      "unique_trial_ids",
      trials.length,
      new Set(trials.map((trial) => trial.trialId)).size,
    ),
  );
  checks.push(
    expectedCheck(
      issues,
      "no_windows_absolute_paths",
      0,
      countAbsoluteWindowsPaths(bundleCore),
    ),
  );
  return {
    ok: issues.every((issue) => issue.severity !== "error"),
    checks,
    issues: issues.sort((left, right) =>
      `${left.severity}:${left.code}:${left.trialId ?? ""}`.localeCompare(
        `${right.severity}:${right.code}:${right.trialId ?? ""}`,
      ),
    ),
  };
}

export function buildMeetingExperimentBundle({ repoRoot, reportRoot = null, strict = true }) {
  if (!repoRoot) {
    throw new Error("buildMeetingExperimentBundle requires repoRoot.");
  }
  void reportRoot;
  const indexes = { oneShotSuccesses: [], recoverySuccesses: [] };
  const pipeline = MEETING_EXPERIMENTS.map((experimentSpec) => {
    const adapter = ADAPTER_REGISTRY[experimentSpec.adapter];
    if (!adapter) {
      throw new Error(
        `Experiment ${experimentSpec.id} requests unknown adapter ${experimentSpec.adapter}.`,
      );
    }
    const base = adapter({ repoRoot, experimentSpec });
    let currentTrials = base.trials;
    const sourceFiles = [...base.sourceFiles];
    const issues = [...base.issues];
    for (const enricherId of experimentSpec.enrichers.filter(
      (id) => id !== "meeting-taxonomy",
    )) {
      const enricher = ENRICHER_REGISTRY[enricherId];
      if (!enricher) {
        throw new Error(
          `Experiment ${experimentSpec.id} requests unknown enricher ${enricherId}.`,
        );
      }
      const result = enricher({
        repoRoot,
        experimentSpec,
        trials: currentTrials,
        options: experimentSpec.enricherOptions?.[enricherId] ?? {},
      });
      currentTrials = result.trials;
      if (result.sourceFile) sourceFiles.push(result.sourceFile);
      issues.push(...(result.issues ?? []));
      for (const [name, entries] of Object.entries(result.indexes ?? {})) {
        indexes[name] = [...(indexes[name] ?? []), ...entries].sort((left, right) =>
          left.trialId.localeCompare(right.trialId),
        );
      }
    }
    return {
      experimentSpec,
      experiment: {
        ...base.experiment,
        adapter: experimentSpec.adapter,
        enrichers: [...experimentSpec.enrichers],
        metricProfile: experimentSpec.metricProfile,
      },
      trials: currentTrials,
      sourceFiles,
      issues,
    };
  });
  const taxonomyInput = pipeline
    .filter(({ experimentSpec }) => experimentSpec.enrichers.includes("meeting-taxonomy"))
    .flatMap(({ trials: experimentTrials }) => experimentTrials);
  const taxonomy = applyMeetingTaxonomy({
    trials: taxonomyInput,
    experimentSpecs: MEETING_EXPERIMENTS,
  });
  const classifiedById = new Map(taxonomy.trials.map((trial) => [trial.trialId, trial]));
  const trials = pipeline
    .flatMap(({ trials: experimentTrials }) =>
      experimentTrials.map((trial) => classifiedById.get(trial.trialId) ?? trial),
    )
    .sort(
    (left, right) =>
      left.experimentId.localeCompare(right.experimentId) ||
      left.trialId.localeCompare(right.trialId),
  );
  const pipelineSourceFiles = pipeline.flatMap(({ sourceFiles }) => sourceFiles);
  const analysisRefs = new Set(
    pipelineSourceFiles
      .filter((source) => source.trialId == null)
      .map((source) => source.sourceRef),
  );
  const sourceFiles = selectedSourceFiles(
    pipelineSourceFiles,
    trials,
    analysisRefs,
  ).sort((left, right) => left.sourceRef.localeCompare(right.sourceRef));
  const experiments = pipeline
    .map(({ experiment, experimentSpec }) => {
      const experimentTrials = trials.filter(
        (trial) => trial.experimentId === experiment.id,
      );
      return {
        ...experiment,
        trialIds: experimentTrials.map((trial) => trial.trialId),
        metrics: experimentMetrics(experimentSpec, experimentTrials, indexes),
        indexes:
          experimentSpec.metricProfile === "validated-target"
            ? {
                oneShotTrialIds: indexes.oneShotSuccesses.map((entry) => entry.trialId),
                recoveryTrialIds: indexes.recoverySuccesses.map((entry) => entry.trialId),
              }
            : {},
        sourceRefs: sourceFiles
          .filter((source) => source.experimentId === experiment.id)
          .map((source) => source.sourceRef),
      };
    })
    .sort((left, right) => left.order - right.order);
  const scope = {
    trialCount: trials.length,
    eventCount: trials.reduce((sum, trial) => sum + trial.summary.eventCount, 0),
    causalEdgeCount: trials.reduce(
      (sum, trial) => sum + trial.summary.causalEdgeCount,
      0,
    ),
    easyFailureCount: trials.filter((trial) => trial.classifications.failureMode).length,
    mediumFailureCount: trials.filter((trial) => trial.classifications.progressStage).length,
    recoverySuccessCount: trials.filter(
      (trial) => trial.classifications.successPattern?.categoryId === "recovery",
    ).length,
    oneShotExemplarCount: trials.filter(
      (trial) => trial.classifications.successPattern?.categoryId === "one-shot",
    ).length,
  };
  const views = VIEWS.map((view) => ({
    ...view,
    trialIds: trials
      .filter((trial) => {
        if (view.id === "medium-progress-matrix") {
          return Boolean(trial.classifications.progressStage);
        }
        return trial.sectionId === view.sectionId;
      })
      .map((trial) => trial.trialId)
      .sort(),
  }));
  const issues = [
    ...pipeline.flatMap((item) => item.issues),
    ...taxonomy.issues,
  ];
  const sourceSetSha256 = sha256(
    sourceFiles
      .map((source) => `${source.sourceRef}:${source.rawSha256}:${source.publishedSha256}`)
      .join("\n"),
  );
  const bundleCore = {
    schemaVersion: BUNDLE_SCHEMA_VERSION,
    generatedAt: null,
    scope,
    indexes,
    sections: sectionDefinitions(trials),
    experiments,
    trials,
    taxonomies: TAXONOMIES,
    metricDefinitions: METRIC_DEFINITIONS,
    views,
    provenance: {
      buildVersion: BUILD_VERSION,
      sourceSetSha256,
      sourceFiles,
      sanitizationPolicy: {
        id: "meeting-public-paths.v1",
        rules: [
          "Replace repository-root absolute paths with <repo-root>.",
          "Replace transient Lean check-file paths with <sanitized-lean-source>.",
          "Do not alter any other source field.",
        ],
        replacementCount: sourceFiles.reduce(
          (sum, source) => sum + Number(source.sanitizationCount ?? 0),
          0,
        ),
      },
    },
  };
  const validation = addValidation({ bundleCore, issues });
  const bundle = { ...bundleCore, validation };
  if (strict && !validation.ok) {
    const errors = validation.issues
      .filter((issue) => issue.severity === "error")
      .map((issue) => `${issue.code}${issue.trialId ? `(${issue.trialId})` : ""}`)
      .join(", ");
    throw new Error(`Meeting experiment bundle validation failed: ${errors}`);
  }
  return bundle;
}
