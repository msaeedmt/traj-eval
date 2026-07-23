import {
  AUDIT_FLAGS,
  EASY_FAILURE_MODES,
  MEDIUM_FAILURE_BEHAVIORS,
  MEDIUM_PROGRESS_STAGES,
  MEDIUM_REVIEWED_ASSIGNMENTS,
  SUCCESS_PATTERNS,
} from "../../../config/meeting-experiments.mjs";

function categoryById(categories, categoryId) {
  const category = categories.find((item) => item.categoryId === categoryId);
  if (!category) {
    throw new Error(`Unknown taxonomy category: ${categoryId}`);
  }
  return category;
}

function assignment({
  axisId,
  category,
  method,
  confidence,
  evidenceRefs = [],
  extra = {},
}) {
  return {
    axisId,
    categoryId: category.categoryId,
    label: category.label,
    description: category.description,
    order: category.order,
    method,
    confidence,
    evidenceRefs,
    ...extra,
  };
}

function evidenceRef(trialId, eventSeq, extra = {}) {
  return { trialId, eventSeq, ...extra };
}

function easyFailureAssignment(trial) {
  const failure = trial.extensions.easyAnalysis?.primaryFailure;
  const category = EASY_FAILURE_MODES.find(
    (item) => item.symptomCode === failure?.symptom_code,
  );
  if (!category) {
    return null;
  }
  return assignment({
    axisId: "easy-failure-mode",
    category,
    method: "reviewed-analysis",
    confidence: failure?.confidence ?? trial.extensions.easyAnalysis?.reviewConfidence ?? null,
    evidenceRefs: [
      evidenceRef(trial.trialId, failure?.event_seq ?? null, {
        resultSeq: failure?.result_event_seq ?? null,
      }),
    ],
  });
}

function successAssignment(trial) {
  const recovery = trial.summary.recovery;
  const categoryId = recovery?.qualifies ? "recovery" : "one-shot";
  const category = categoryById(SUCCESS_PATTERNS, categoryId);
  const evidenceRefs = [
    ...(recovery?.failureResultSeqsBeforeAcceptance ?? []).map((seq) =>
      evidenceRef(trial.trialId, seq),
    ),
    evidenceRef(trial.trialId, recovery?.terminalAcceptanceSeq ?? null),
  ];
  return assignment({
    axisId: "success-pattern",
    category,
    method: "rule",
    confidence: "deterministic",
    evidenceRefs,
  });
}

function mediumEvidenceSeqs(trial, reviewed) {
  if (reviewed.evidenceSeqs.length > 0) {
    return [...reviewed.evidenceSeqs];
  }
  const categoryId = reviewed.categoryId;
  if (categoryId === "formalization-interface-barrier") {
    const seq = trial.checks
      .filter((check) => check.compiled === false && check.resultSeq != null)
      .map((check) => check.resultSeq)
      .sort((left, right) => left - right)
      .at(-1);
    if (seq != null) return [seq];
  }
  if (categoryId === "search-recovery-loop") {
    const seq = trial.events
      .filter((event) => event.toolCalls.some((call) => call.name === "search_lemmas"))
      .map((event) => event.seq)
      .sort((left, right) => left - right)
      .at(-1);
    if (seq != null) return [seq];
  }
  if (
    categoryId === "subgoal-scope-mismatch" ||
    categoryId === "critic-acceptance-mismatch"
  ) {
    const relevant = trial.extensions.subgoals?.transitions
      ?.filter((transition) => ["accepted", "rejected"].includes(transition.kind))
      .map((transition) => transition.seq)
      .sort((left, right) => left - right)
      .at(-1);
    if (relevant != null) return [relevant];
  }
  return [trial.events.at(-1)?.seq].filter((seq) => seq != null);
}

function applyEasy(trial, issues) {
  trial.classifications.outcome = {
    axisId: "outcome",
    categoryId: trial.outcome.status,
    label: trial.outcome.status,
    method: "validator",
    confidence: "deterministic",
    evidenceRefs: [],
  };
  if (trial.outcome.status !== "solved") {
    const failureMode = easyFailureAssignment(trial);
    if (!failureMode) {
      issues.push({
        severity: "error",
        code: "missing_easy_failure_mode",
        trialId: trial.trialId,
        message: "Failed easy trial has no mapped reviewed primary failure.",
      });
      return;
    }
    trial.classifications.failureMode = failureMode;
    trial.sectionId = "failures";
    trial.groupId = failureMode.categoryId;
  } else {
    const successPattern = successAssignment(trial);
    trial.classifications.successPattern = successPattern;
    trial.sectionId = "successes";
    trial.groupId = successPattern.categoryId;
  }
}

function applyMedium(trial, issues) {
  const reviewed = MEDIUM_REVIEWED_ASSIGNMENTS[trial.trialId];
  const stageId = trial.extensions.subgoals?.progress?.stageId;
  const stage = MEDIUM_PROGRESS_STAGES.find((item) => item.categoryId === stageId);
  if (!reviewed) {
    issues.push({
      severity: "error",
      code: "missing_medium_reviewed_assignment",
      trialId: trial.trialId,
      message: "Medium trial has no reviewed dominant failure behavior.",
    });
    return;
  }
  if (!stage) {
    issues.push({
      severity: "error",
      code: "missing_medium_progress_stage",
      trialId: trial.trialId,
      message: `Unknown derived progress stage ${stageId}.`,
    });
    return;
  }
  const behaviorCategory = categoryById(
    MEDIUM_FAILURE_BEHAVIORS,
    reviewed.categoryId,
  );
  const behaviorSeqs = mediumEvidenceSeqs(trial, reviewed);
  const terminalFrame = trial.extensions.subgoals?.frames?.at(-1);
  trial.classifications.outcome = {
    axisId: "outcome",
    categoryId: "unsolved",
    label: "unsolved",
    method: "final-validator",
    confidence: "deterministic",
    evidenceRefs: [],
  };
  trial.classifications.progressStage = assignment({
    axisId: "medium-progress-stage",
    category: stage,
    method: "rule",
    confidence: "controller-observed",
    evidenceRefs: [
      evidenceRef(trial.trialId, terminalFrame?.seq ?? trial.events.at(-1)?.seq ?? null),
    ],
    extra: { stageCode: `P${stage.order}` },
  });
  trial.classifications.failureBehavior = assignment({
    axisId: "medium-failure-behavior",
    category: behaviorCategory,
    method: "manual-trace-synthesis",
    confidence: "exploratory",
    evidenceRefs: behaviorSeqs.map((seq) => evidenceRef(trial.trialId, seq)),
  });
  trial.classifications.auditFlags = (reviewed.auditFlags ?? []).map((categoryId) =>
    assignment({
      axisId: "audit-flag",
      category: categoryById(AUDIT_FLAGS, categoryId),
      method: "manual-trace-audit",
      confidence: "strong",
      evidenceRefs: behaviorSeqs.map((seq) => evidenceRef(trial.trialId, seq)),
    }),
  );
  trial.annotations.push(
    ...behaviorSeqs.map((seq, index) => ({
      annotationId: `${trial.trialId}:failure-behavior:${index}`,
      kind: "classification-evidence",
      label: behaviorCategory.label,
      eventSeq: seq,
      resultSeq: seq,
      subgoalId: null,
      evidence: behaviorCategory.description,
      confidence: "exploratory",
      source: "manual-medium-trace-synthesis",
    })),
  );
  trial.sectionId = "failures";
  trial.groupId = behaviorCategory.categoryId;
}

export function applyMeetingTaxonomy({ trials, experimentSpecs }) {
  const issues = [];
  const specsById = new Map(experimentSpecs.map((spec) => [spec.id, spec]));
  for (const trial of trials) {
    const spec = specsById.get(trial.experimentId);
    if (!spec) {
      issues.push({
        severity: "error",
        code: "missing_experiment_spec",
        trialId: trial.trialId,
        message: `No experiment specification exists for ${trial.experimentId}.`,
      });
    } else if (trial.extensions.easyAnalysis) {
      applyEasy(trial, issues);
    } else if (spec.capabilities.includes("subgoal_history") && trial.extensions.subgoals) {
      applyMedium(trial, issues);
    } else {
      issues.push({
        severity: "error",
        code: "unsupported_experiment_taxonomy",
        trialId: trial.trialId,
        message: `No meeting taxonomy enricher is registered for ${trial.experimentId}.`,
      });
    }
    trial.provenance.enrichers.push({ id: "meeting-taxonomy", version: "1.0.0" });
  }
  return { trials, issues };
}
