import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  createPublicSanitizer,
  sha256,
  toRepoRelative,
} from "../adapters/trace-jsonl.mjs";

function finiteNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function checkFromAnalysis(trialId, item, index) {
  const callSeq = finiteNumber(item.seq);
  const resultSeq = finiteNumber(item.result_seq);
  return {
    callId: `${trialId}:check:${callSeq ?? index}`,
    callSeq,
    resultSeq,
    role: item.role ?? null,
    tool: "check_lean",
    purpose: item.candidate_kind === "exact_target" ? "final" : "probe",
    subgoalId: null,
    compiled: typeof item.compiled === "boolean" ? item.compiled : null,
    sorryFree: typeof item.sorry_free === "boolean" ? item.sorry_free : null,
    nSorries: item.sorry_free === false ? null : item.sorry_free === true ? 0 : null,
    verificationStatus: item.verification_status ?? null,
    candidateKind: item.candidate_kind ?? null,
    statementMatch: item.statement_match ?? null,
    diagnostic: item.diagnostic ?? "",
    code: item.code ?? null,
    evidenceHash: null,
    matched: resultSeq != null,
  };
}

function recoverySummary(checks, terminalAcceptanceSeq) {
  const beforeAcceptance = checks.filter(
    (check) =>
      check.compiled === false &&
      check.resultSeq != null &&
      terminalAcceptanceSeq != null &&
      check.resultSeq < terminalAcceptanceSeq,
  );
  const failureResultSeqsBeforeAcceptance = beforeAcceptance
    .map((check) => check.resultSeq)
    .sort((left, right) => left - right);
  const firstFailureSeq = failureResultSeqsBeforeAcceptance[0] ?? null;
  const lastFailureSeq = failureResultSeqsBeforeAcceptance.at(-1) ?? null;
  const earlierPassResultSeqs = checks
    .filter(
      (check) =>
        check.compiled === true &&
        check.resultSeq != null &&
        firstFailureSeq != null &&
        check.resultSeq < firstFailureSeq,
    )
    .map((check) => check.resultSeq)
    .sort((left, right) => left - right);
  const firstPass = checks
    .filter((check) => check.compiled === true && check.resultSeq != null)
    .map((check) => check.resultSeq)
    .sort((left, right) => left - right)[0];
  const regressionAfterPass =
    firstPass != null &&
    failureResultSeqsBeforeAcceptance.some((failureSeq) => failureSeq > firstPass);
  return {
    qualifies: failureResultSeqsBeforeAcceptance.length > 0,
    failureResultSeqsBeforeAcceptance,
    firstFailureSeq,
    lastFailureSeq,
    terminalAcceptanceSeq,
    earlierPassResultSeqs,
    regressionAfterPass,
  };
}

function incidentAnnotation(trialId, incident, index) {
  return {
    annotationId: `${trialId}:incident:${index}`,
    kind: incident.recovered ? "recovered-failure" : "failure-evidence",
    label: incident.symptom_code ?? "Lean failure",
    eventSeq: finiteNumber(incident.event_seq),
    resultSeq: finiteNumber(incident.result_event_seq),
    subgoalId: null,
    evidence: incident.evidence ?? "",
    confidence: incident.confidence ?? null,
    source: "easy-analysis-snapshot",
  };
}

function primaryFailureAnnotation(trialId, failure) {
  if (!failure) {
    return null;
  }
  return {
    annotationId: `${trialId}:primary-failure`,
    kind: "primary-failure",
    label: failure.symptom_code ?? "Primary failure",
    eventSeq: finiteNumber(failure.event_seq),
    resultSeq: finiteNumber(failure.result_event_seq),
    subgoalId: null,
    evidence: failure.evidence ?? "",
    confidence: failure.confidence ?? null,
    source: "easy-analysis-snapshot",
  };
}

export function enrichEasyTrials({
  repoRoot,
  experimentSpec,
  trials,
  recoveryTrialIds,
  oneShotExemplarId,
}) {
  const analysisPath = resolve(repoRoot, experimentSpec.analysisPath);
  const sourceText = readFileSync(analysisPath, "utf8");
  const sanitizer = createPublicSanitizer({ repoRoot });
  const analysisRows = sanitizer.sanitize(JSON.parse(sourceText));
  if (!Array.isArray(analysisRows)) {
    throw new Error("Easy analysis payload must be an array.");
  }
  const byTrial = new Map(analysisRows.map((row) => [row.trial_id, row]));
  const expectedRecoveries = new Set(recoveryTrialIds);
  const issues = [];
  const selected = [];
  const oneShotSuccesses = [];
  const recoverySuccesses = [];

  for (const trial of trials) {
    const analysis = byTrial.get(trial.trialId);
    if (!analysis) {
      issues.push({
        severity: "error",
        code: "missing_easy_analysis",
        trialId: trial.trialId,
        message: "No easy analysis record matches this raw trial.",
      });
      continue;
    }
    const checks = (analysis.tool_calls ?? []).map((item, index) =>
      checkFromAnalysis(trial.trialId, item, index),
    );
    const verification = analysis.diagnosis?.verification ?? {};
    const candidate = analysis.diagnosis?.candidate ?? {};
    const validatorOutcome = verification.validator_outcome ?? "unknown";
    const solved = validatorOutcome === "solved";
    const terminalAcceptanceSeq = finiteNumber(candidate.result_event_seq);
    const recovery = recoverySummary(checks, terminalAcceptanceSeq);
    const isRecovery =
      solved && candidate.kind === "exact_target" && recovery.qualifies;
    const isOneShotExemplar = trial.trialId === oneShotExemplarId;
    const include = !solved || isRecovery || isOneShotExemplar;

    if (solved && candidate.kind === "exact_target") {
      const entry = {
        trialId: trial.trialId,
        experimentId: trial.experimentId,
        taskId: trial.taskId,
        trialNumber: trial.trialNumber,
        source: analysis.source ?? null,
        difficulty: analysis.difficulty ?? "easy",
        acceptedResultSeq: terminalAcceptanceSeq,
        eventCount: trial.summary.eventCount,
      };
      if (isRecovery) {
        recoverySuccesses.push({
          ...entry,
          failedResultSeqs: [...recovery.failureResultSeqsBeforeAcceptance],
        });
      } else {
        oneShotSuccesses.push(entry);
      }
    }

    if (isRecovery !== expectedRecoveries.has(trial.trialId)) {
      issues.push({
        severity: "error",
        code: "recovery_membership_mismatch",
        trialId: trial.trialId,
        message: `Derived recovery=${isRecovery} differs from the reviewed recovery scope.`,
      });
    }
    if (!include) {
      continue;
    }

    trial.source = analysis.source ?? null;
    trial.difficulty = analysis.difficulty ?? "easy";
    trial.metadata = {
      ...trial.metadata,
      informal: analysis.informal ?? null,
      formalStatement: analysis.formal_statement ?? null,
      submittedCode: analysis.submitted_code ?? null,
      acceptedCandidateCode: analysis.accepted_candidate_code ?? null,
      sourceSha256: analysis.source_sha256 ?? null,
      analysisSnapshotSha256: analysis.analysis_snapshot_sha256 ?? null,
      reviewSha256: analysis.review_sha256 ?? null,
    };
    trial.outcome = {
      status: validatorOutcome,
      validatorOutcome,
      declaredSuccess: Boolean(analysis.declared_success),
      verificationLevel: verification.verification_level ?? null,
      kernelStatus: verification.kernel_status ?? null,
      validationStatus: verification.validation_status ?? null,
      statementPreserved: verification.statement_preserved ?? null,
      sorryFree: verification.final_proof_sorry_free ?? null,
      axiomClean: verification.axiom_clean ?? null,
      exactTargetAccepted: solved && candidate.kind === "exact_target",
      terminalAcceptanceSeq,
      verifiedCompletion: solved,
    };
    trial.checks = checks;
    trial.summary = {
      ...trial.summary,
      checkCount: checks.length,
      matchedCheckCount: checks.filter((check) => check.matched).length,
      failedCompilerResults: checks.filter((check) => check.compiled === false).length,
      acceptedCompilerResults: checks.filter((check) => check.compiled === true).length,
      recovery,
    };
    const primary = primaryFailureAnnotation(
      trial.trialId,
      analysis.diagnosis?.critical_failure,
    );
    trial.annotations = [
      ...(analysis.diagnosis?.incidents ?? []).map((incident, index) =>
        incidentAnnotation(trial.trialId, incident, index),
      ),
      ...(primary ? [primary] : []),
    ];
    trial.extensions.easyAnalysis = {
      reviewStatus: analysis.diagnosis?.review_status ?? null,
      reviewConfidence: analysis.diagnosis?.review_confidence ?? null,
      primaryFailure: analysis.diagnosis?.critical_failure ?? null,
      workflow: analysis.diagnosis?.workflow ?? null,
      candidate,
      verification,
      taskDiagnosis: analysis.diagnosis?.task_diagnosis ?? null,
    };
    trial.provenance.analysisRefs.push("analysis:qwen-easy-v1");
    trial.provenance.enrichers.push({ id: "easy-analysis", version: "1.0.0" });
    selected.push(trial);
  }

  const selectedIds = new Set(selected.map((trial) => trial.trialId));
  for (const trialId of recoveryTrialIds) {
    if (!selectedIds.has(trialId)) {
      issues.push({
        severity: "error",
        code: "missing_recovery_trial",
        trialId,
        message: "Reviewed recovery trial is absent from the selected easy scope.",
      });
    }
  }

  const publishedText = JSON.stringify(analysisRows);
  return {
    trials: selected.sort((left, right) => left.trialId.localeCompare(right.trialId)),
    sourceFile: {
      sourceRef: "analysis:qwen-easy-v1",
      experimentId: experimentSpec.id,
      trialId: null,
      path: toRepoRelative(repoRoot, analysisPath),
      format: "json",
      schemaVersion: "easy-analysis.v1",
      recordCount: analysisRows.length,
      eventCount: null,
      rawSha256: sha256(sourceText),
      publishedSha256: sha256(publishedText),
      sanitizationCount: sanitizer.replacementCount,
    },
    issues,
    indexes: {
      oneShotSuccesses: oneShotSuccesses.sort((left, right) =>
        left.trialId.localeCompare(right.trialId),
      ),
      recoverySuccesses: recoverySuccesses.sort((left, right) =>
        left.trialId.localeCompare(right.trialId),
      ),
    },
  };
}
