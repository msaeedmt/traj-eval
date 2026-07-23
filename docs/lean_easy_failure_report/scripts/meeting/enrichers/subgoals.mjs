import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

import {
  createPublicSanitizer,
  sha256,
  toRepoRelative,
} from "../adapters/trace-jsonl.mjs";

function runExtractor(inputDir) {
  const script = fileURLToPath(
    new URL("../extract-subgoal-states.py", import.meta.url),
  );
  const candidates = [
    ...(process.env.PYTHON ? [[process.env.PYTHON, ["-B"]]] : []),
    ["py", ["-3", "-B"]],
    ["python", ["-B"]],
    ["python3", ["-B"]],
  ];
  const failures = [];
  for (const [command, prefix] of candidates) {
    const result = spawnSync(command, [...prefix, script, inputDir], {
      encoding: "utf8",
      maxBuffer: 64 * 1024 * 1024,
      windowsHide: true,
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" },
    });
    if (result.status === 0) {
      try {
        return JSON.parse(result.stdout);
      } catch (error) {
        failures.push(`${command}: invalid JSON (${error.message})`);
        continue;
      }
    }
    failures.push(
      `${command}: ${result.error?.message ?? result.stderr?.trim() ?? `status ${result.status}`}`,
    );
  }
  throw new Error(`Could not run subgoal extractor: ${failures.join(" | ")}`);
}

function nodeFromState(node) {
  return {
    id: node.id,
    objective: node.objective ?? "",
    dependsOn: [...(node.depends_on ?? [])],
    status: node.status ?? "pending",
    attempts: Number(node.attempts ?? 0),
    consecutiveFailures: Number(node.consecutive_failures ?? 0),
    candidateHash: node.candidate_hash ?? null,
    acceptedHash: node.accepted_hash ?? null,
    failures: [...(node.failures ?? [])],
    feedback: node.feedback ?? "",
  };
}

function transitionFromExtracted(transition) {
  return {
    seq: transition.seq,
    eventId: transition.event_id ?? null,
    subgoalId: transition.subgoal_id ?? null,
    kind: transition.kind,
    fromStatus: transition.from_status ?? null,
    toStatus: transition.to_status ?? null,
    detail: transition.detail ?? "",
    attemptDelta: transition.attempt_delta ?? null,
  };
}

function frameFromExtracted(frame) {
  return {
    seq: frame.seq,
    eventId: frame.event_id ?? null,
    version: frame.version ?? null,
    tool: frame.tool ?? null,
    activeSubgoal: frame.active_subgoal ?? null,
    planReady: frame.plan_ready ?? false,
    forcedRecoveries: Number(frame.forced_recoveries ?? 0),
    strategyRevisions: Number(frame.strategy_revisions ?? 0),
    nodes: (frame.nodes ?? []).map(nodeFromState),
    changes: (frame.changes ?? []).map(transitionFromExtracted),
  };
}

function diagnostics(result) {
  if (!result || typeof result !== "object") {
    return "";
  }
  const chunks = (result.errors ?? []).map((item) =>
    typeof item === "string" ? item : item?.data ?? JSON.stringify(item),
  );
  if (chunks.length === 0 && result.error) {
    chunks.push(String(result.error));
  }
  return chunks.join("\n");
}

function checkFromInvocation(invocation) {
  const result = invocation.result;
  const args = invocation.arguments ?? {};
  return {
    callId: invocation.call_id ?? null,
    callSeq: invocation.call_seq ?? null,
    resultSeq: invocation.result_seq ?? null,
    role: invocation.role ?? null,
    tool: "check_lean",
    purpose: result?.purpose ?? args.purpose ?? "subgoal",
    subgoalId: result?.subgoal_id ?? args.subgoal_id ?? null,
    compiled: typeof result?.compiled === "boolean" ? result.compiled : null,
    sorryFree: typeof result?.sorry_free === "boolean" ? result.sorry_free : null,
    nSorries: Number.isFinite(Number(result?.n_sorries))
      ? Number(result.n_sorries)
      : null,
    verificationStatus: result?.verification_status ?? null,
    candidateKind: null,
    statementMatch: null,
    diagnostic: diagnostics(result),
    code: args.code ?? null,
    evidenceHash: result?.evidence_hash ?? null,
    matched: Boolean(invocation.matched),
  };
}

function parseTaskSource(trial) {
  const prompt = trial.events.find(
    (event) => event.role === "system" && typeof event.text === "string",
  )?.text;
  return prompt?.match(/\(source:\s*([^,]+),\s*difficulty:/i)?.[1]?.trim() ?? null;
}

function progressStageId({ verifiedCompletion, returnedChecks, reviews, accepted }) {
  if (verifiedCompletion) {
    return "p5-verified-theorem";
  }
  if (returnedChecks === 0) {
    return "p0-plan-only";
  }
  if (reviews === 0) {
    return "p1-compiler-engaged";
  }
  if (accepted === 0) {
    return "p2-critic-none-accepted";
  }
  if (accepted === 1) {
    return "p3-one-ledger-accept";
  }
  return "p4-multiple-ledger-accepts";
}

function summaryTrialMap(summary) {
  return new Map(
    (summary.trials ?? []).map((row) => [
      `${row.task_id}_t${row.trial}`,
      row,
    ]),
  );
}

export function enrichMediumSubgoalTrials({
  repoRoot,
  experimentSpec,
  trials,
}) {
  const inputDir = resolve(repoRoot, experimentSpec.rawDir);
  const extractedRaw = runExtractor(inputDir);
  const sanitizer = createPublicSanitizer({ repoRoot });
  const extracted = sanitizer.sanitize(extractedRaw);
  const byTrial = new Map(
    (extracted.trials ?? []).map((trial) => [trial.trial_id, trial]),
  );
  const summaryPath = resolve(repoRoot, experimentSpec.summaryPath);
  const summaryText = readFileSync(summaryPath, "utf8");
  const summary = sanitizer.sanitize(JSON.parse(summaryText));
  const summaryByTrial = summaryTrialMap(summary);
  const issues = [];

  for (const trial of trials) {
    const item = byTrial.get(trial.trialId);
    if (!item) {
      issues.push({
        severity: "error",
        code: "missing_subgoal_extraction",
        trialId: trial.trialId,
        message: "The subgoal extractor returned no record for this trial.",
      });
      continue;
    }
    const summaryRow = summaryByTrial.get(trial.trialId);
    const invocations = item.tool_invocations ?? [];
    const checks = invocations
      .filter((invocation) => invocation.tool === "check_lean")
      .map(checkFromInvocation);
    const reviewInvocations = invocations.filter(
      (invocation) => invocation.tool === "review_subgoal" && invocation.matched,
    );
    const nodes = (item.terminal_state?.nodes ?? []).map(nodeFromState);
    const statusCounts = Object.fromEntries(
      ["pending", "active", "candidate", "accepted", "rejected", "blocked"].map(
        (status) => [status, nodes.filter((node) => node.status === status).length],
      ),
    );
    const returnedChecks = checks.filter((check) => check.matched).length;
    const verifiedCompletion =
      summaryRow?.communication?.verified_completion === true;
    const stageId = progressStageId({
      verifiedCompletion,
      returnedChecks,
      reviews: reviewInvocations.length,
      accepted: statusCounts.accepted,
    });
    const frames = (item.frames ?? []).map(frameFromExtracted);
    const transitions = (item.transitions ?? []).map(transitionFromExtracted);
    const replay = item.replay_validation ?? {};

    trial.source = parseTaskSource(trial);
    trial.difficulty = "medium";
    trial.outcome = {
      status: summaryRow?.outcome ?? "unsolved",
      validatorOutcome: summaryRow?.outcome ?? "unsolved",
      declaredSuccess: false,
      verificationLevel: "not_verified",
      kernelStatus: null,
      validationStatus: null,
      statementPreserved: null,
      sorryFree: null,
      axiomClean: null,
      exactTargetAccepted: false,
      terminalAcceptanceSeq: null,
      verifiedCompletion,
      terminationReason: summaryRow?.termination ?? item.termination?.termination_reason ?? null,
    };
    trial.checks = checks;
    trial.summary = {
      ...trial.summary,
      checkCount: checks.length,
      matchedCheckCount: returnedChecks,
      failedCompilerResults: checks.filter((check) => check.compiled === false).length,
      acceptedCompilerResults: checks.filter((check) => check.compiled === true).length,
      sorryBearingCompilerResults: checks.filter(
        (check) => check.compiled === true && check.sorryFree === false,
      ).length,
      subgoalsDefined: nodes.length,
      subgoalsAttempted: nodes.filter((node) => node.attempts > 0).length,
      subgoalsAccepted: statusCounts.accepted,
      subgoalStatusCounts: statusCounts,
      forcedRecoveries: Number(item.terminal_state?.forced_recoveries ?? 0),
      strategyRevisions: Number(item.terminal_state?.strategy_revisions ?? 0),
      progressStageId: stageId,
    };
    trial.annotations = [
      ...trial.annotations,
      ...transitions.map((transition, index) => ({
        annotationId: `${trial.trialId}:subgoal-transition:${index}`,
        kind: "subgoal-transition",
        label: transition.kind,
        eventSeq: transition.seq,
        resultSeq: transition.seq,
        subgoalId: transition.subgoalId,
        evidence: transition.detail,
        confidence: "controller_observed",
        source: "subgoal-ledger-replay",
      })),
    ];
    trial.extensions.subgoals = {
      nodes,
      frames,
      transitions,
      progress: {
        stageId,
        defined: nodes.length,
        attempted: nodes.filter((node) => node.attempts > 0).length,
        ledgerAccepted: statusCounts.accepted,
        statusCounts,
        compilerResults: returnedChecks,
        reviewResults: reviewInvocations.length,
        forcedRecoveries: Number(item.terminal_state?.forced_recoveries ?? 0),
        strategyRevisions: Number(item.terminal_state?.strategy_revisions ?? 0),
        verifiedCompletion,
      },
      replayValidation: {
        status: replay.status ?? "unavailable",
        expectedVersion: replay.expected_version ?? null,
        observedVersion: replay.observed_version ?? null,
        mismatches: [...(replay.mismatches ?? [])],
      },
    };
    trial.extensions.toolProtocol = {
      callCount: invocations.length,
      matchedResultCount: invocations.filter((invocation) => invocation.matched).length,
      unmatchedCalls: invocations
        .filter((invocation) => !invocation.matched)
        .map((invocation) => ({
          callId: invocation.call_id,
          tool: invocation.tool,
          callSeq: invocation.call_seq,
        })),
      parseErrors: [...(item.parse_errors ?? [])],
    };
    trial.provenance.analysisRefs.push("summary:qwen-medium-subgoals-v1");
    trial.provenance.enrichers.push({ id: "subgoal-ledger-replay", version: "1.0.0" });

    for (const parseError of item.parse_errors ?? []) {
      issues.push({
        severity: "warning",
        code: "tool_result_parse_error",
        trialId: trial.trialId,
        message: `Could not parse tool response ${parseError.call_id}: ${parseError.error}`,
      });
    }
    for (const invocation of invocations.filter((candidate) => !candidate.matched)) {
      issues.push({
        severity: "warning",
        code: "unmatched_tool_call",
        trialId: trial.trialId,
        eventSeq: invocation.call_seq,
        message: `No execution result matched ${invocation.tool} call ${invocation.call_id}.`,
      });
    }
    if (replay.status !== "matched") {
      issues.push({
        severity: "error",
        code: "subgoal_replay_gap",
        trialId: trial.trialId,
        message: `Subgoal replay status is ${replay.status}; mismatches=${(replay.mismatches ?? []).join(",") || "none"}.`,
      });
    }
  }

  const publishedSummaryText = JSON.stringify(summary);
  return {
    trials: [...trials].sort((left, right) => left.trialId.localeCompare(right.trialId)),
    sourceFile: {
      sourceRef: "summary:qwen-medium-subgoals-v1",
      experimentId: experimentSpec.id,
      trialId: null,
      path: toRepoRelative(repoRoot, summaryPath),
      format: "json",
      schemaVersion: summary.schema_version ?? null,
      recordCount: summary.trials?.length ?? null,
      eventCount: null,
      rawSha256: sha256(summaryText),
      publishedSha256: sha256(publishedSummaryText),
      sanitizationCount: sanitizer.replacementCount,
    },
    extraction: {
      schemaVersion: extracted.schema_version ?? null,
      sanitizationCount: sanitizer.replacementCount,
    },
    issues,
  };
}
