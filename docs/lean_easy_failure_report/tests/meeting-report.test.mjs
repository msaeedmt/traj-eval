import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { buildMeetingExperimentBundle } from "../scripts/meeting/experiment-data.mjs";
import {
  createMeetingArtifacts,
  extractEmbeddedBundle,
} from "../scripts/build-meeting-report.mjs";
import { renderMeetingMarkdown } from "../scripts/meeting/render-markdown.mjs";

const reportRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(reportRoot, "..", "..");

const EXPECTED_RECOVERIES = [
  "easy_fatem_012_t0", "easy_fatem_012_t1", "easy_fatem_012_t2",
  "easy_fatem_012_t3", "easy_fatem_012_t4", "easy_fatem_012_t5",
  "easy_fatem_012_t7", "easy_fatem_012_t8", "easy_fatem_012_t9",
  "easy_fatem_020_t0", "easy_fatem_020_t1",
  "easy_leancat_001_t1", "easy_leancat_001_t7", "easy_leancat_001_t9",
  "easy_leancat_002_t4", "easy_leancat_002_t7", "easy_leancat_002_t9",
];

const EXPECTED_EASY_MODES = {
  "statement-drift": 5,
  "opaque-verifier-feedback": 15,
  "application-type-mismatch": 7,
  "typeclass-resolution": 6,
  "unknown-mathlib-api": 5,
  "target-not-attempted": 6,
};

const EXPECTED_PROGRESS = { P0: 2, P1: 3, P2: 4, P3: 7, P4: 4, P5: 0 };

const EXPECTED_MEDIUM_MATRIX = {
  "formalization-interface-barrier": [0, 3, 1, 2, 2, 0],
  "search-recovery-loop": [0, 0, 0, 5, 0, 0],
  "subgoal-scope-mismatch": [0, 0, 3, 0, 1, 0],
  "critic-acceptance-mismatch": [0, 0, 0, 0, 1, 0],
  "handoff-without-execution": [2, 0, 0, 0, 0, 0],
};

let bundlePromise;
let artifactsPromise;

function getBundle() {
  bundlePromise ??= Promise.resolve(buildMeetingExperimentBundle({ repoRoot, reportRoot }));
  return bundlePromise;
}

function getArtifacts() {
  artifactsPromise ??= Promise.resolve(createMeetingArtifacts({ repoRoot, reportRoot }));
  return artifactsPromise;
}

function categoryId(value) {
  if (typeof value === "string") return value;
  return value?.categoryId ?? value?.id;
}

function stageCode(trial) {
  const value = trial?.classifications?.progressStage;
  if (typeof value === "string" && /^P[0-5]$/i.test(value)) return value.toUpperCase();
  if (value?.stageCode) return String(value.stageCode).toUpperCase();
  const candidate = value?.label ?? value?.categoryId ?? value?.id ?? trial?.summary?.progressStage;
  const match = String(candidate ?? "").match(/\bP([0-5])\b/i) ??
    String(candidate ?? "").match(/^p([0-5])-/i);
  return match ? `P${match[1]}` : undefined;
}

function graphEdges(trial) {
  return trial?.graph?.edges ?? trial?.causalEdges ?? [];
}

function findEvent(trial, seq) {
  return trial.events.find((event) => event.seq === seq);
}

function checkAtResult(trial, seq) {
  return trial.checks.find((check) => check.resultSeq === seq);
}

function isExactTargetCheck(check) {
  if (!check) return false;
  const match = String(check.statementMatch ?? "").toLowerCase();
  const kind = String(check.candidateKind ?? "").toLowerCase();
  return check.statementMatch === true ||
    ["exact", "exact-target", "matched", "match"].includes(match) ||
    kind.includes("exact");
}

test("bundle scope and complete trace totals reconcile", { timeout: 120_000 }, async () => {
  const bundle = await getBundle();
  assert.equal(bundle.schemaVersion, "meeting-dashboard.bundle.v1");
  assert.equal(bundle.validation?.ok, true, JSON.stringify(bundle.validation?.issues ?? []));
  assert.deepEqual(bundle.scope, {
    trialCount: 82,
    eventCount: 4430,
    causalEdgeCount: 4311,
    easyFailureCount: 44,
    mediumFailureCount: 20,
    recoverySuccessCount: 17,
    oneShotExemplarCount: 1,
  });
  assert.equal(bundle.trials.length, 82);
  assert.equal(bundle.trials.reduce((n, trial) => n + trial.events.length, 0), 4430);
  assert.equal(bundle.trials.reduce((n, trial) => n + graphEdges(trial).length, 0), 4311);
  assert.equal(new Set(bundle.trials.map((trial) => trial.trialId)).size, 82);

  for (const trial of bundle.trials) {
    assert.equal(
      trial.rawRecords.length,
      trial.events.length + 1,
      `${trial.trialId}: expected one raw header plus every event`,
    );
    const seqs = trial.events.map((event) => event.seq);
    const eventIds = trial.events.map((event) => event.eventId);
    assert.equal(new Set(seqs).size, seqs.length, `${trial.trialId}: duplicate sequence`);
    for (const edge of graphEdges(trial)) {
      const source = edge.source ?? edge.from ?? edge.parentSeq;
      const target = edge.target ?? edge.to ?? edge.childSeq;
      assert.ok(eventIds.includes(source) || seqs.includes(source));
      assert.ok(eventIds.includes(target) || seqs.includes(target));
    }
  }
});

test("all 17 recoveries satisfy failed-result then exact-target acceptance", { timeout: 120_000 }, async () => {
  const bundle = await getBundle();
  const recoveryTrials = bundle.trials
    .filter((trial) => categoryId(trial.classifications?.successPattern) === "recovery")
    .sort((a, b) => a.trialId.localeCompare(b.trialId));

  assert.deepEqual(
    recoveryTrials.map((trial) => trial.trialId),
    EXPECTED_RECOVERIES.slice().sort(),
  );

  for (const trial of recoveryTrials) {
    const recovery = trial.summary?.recovery;
    const failures = recovery?.failureResultSeqsBeforeAcceptance ?? [];
    assert.equal(recovery?.qualifies, true);
    assert.ok(failures.length >= 1);
    assert.equal(recovery.firstFailureSeq, failures[0]);
    assert.equal(recovery.lastFailureSeq, failures.at(-1));

    for (const seq of failures) {
      assert.ok(seq < recovery.terminalAcceptanceSeq);
      assert.ok(findEvent(trial, seq));
      assert.equal(checkAtResult(trial, seq)?.compiled, false);
    }

    assert.ok(findEvent(trial, recovery.terminalAcceptanceSeq));
    const accepted = checkAtResult(trial, recovery.terminalAcceptanceSeq);
    assert.equal(accepted?.compiled, true);
    assert.ok(isExactTargetCheck(accepted), `${trial.trialId}: terminal check is not exact-target`);
  }
});

test("easy_fatem_012_t1 is early pass, regression, terminal recovery", { timeout: 120_000 }, async () => {
  const bundle = await getBundle();
  const trial = bundle.trials.find((item) => item.trialId === "easy_fatem_012_t1");
  assert.ok(trial);
  const recovery = trial.summary.recovery;
  assert.equal(recovery.regressionAfterPass, true);
  assert.ok(recovery.earlierPassResultSeqs.length >= 1);
  assert.ok(recovery.earlierPassResultSeqs.some(
    (seq) => seq < recovery.firstFailureSeq &&
      recovery.firstFailureSeq < recovery.terminalAcceptanceSeq,
  ));
  assert.equal(checkAtResult(trial, recovery.earlierPassResultSeqs[0])?.compiled, true);
  assert.equal(checkAtResult(trial, recovery.firstFailureSeq)?.compiled, false);
  assert.equal(checkAtResult(trial, recovery.terminalAcceptanceSeq)?.compiled, true);
});

test("39 one-shot successes are indexed and only the contrast is embedded", { timeout: 120_000 }, async () => {
  const bundle = await getBundle();
  const experiment = bundle.experiments.find((item) => item.id === "qwen-easy-v1");
  const ids = experiment?.indexes?.oneShotTrialIds ?? [];
  assert.equal(ids.length, 39);
  assert.equal(new Set(ids).size, 39);
  assert.ok(ids.includes("easy_fatem_011_t0"));

  const embedded = bundle.trials.filter(
    (trial) => categoryId(trial.classifications?.successPattern) === "one-shot",
  );
  assert.deepEqual(embedded.map((trial) => trial.trialId), ["easy_fatem_011_t0"]);
  assert.ok(embedded[0].rawRecords.length > 1);
});

test("easy modes form the reviewed 5/15/7/6/5/6 partition", { timeout: 120_000 }, async () => {
  const bundle = await getBundle();
  const failures = bundle.trials.filter((trial) => trial.classifications?.failureMode);
  assert.equal(failures.length, 44);
  const counts = Object.fromEntries(Object.keys(EXPECTED_EASY_MODES).map((id) => [id, 0]));

  for (const trial of failures) {
    const classification = trial.classifications.failureMode;
    const id = categoryId(classification);
    assert.ok(id in counts, `${trial.trialId}: unexpected easy mode ${id}`);
    counts[id] += 1;
    for (const seq of classification.evidenceSeqs ?? classification.evidenceEventSeqs ?? []) {
      assert.ok(findEvent(trial, seq), `${trial.trialId}: missing evidence event ${seq}`);
    }
  }
  assert.deepEqual(counts, EXPECTED_EASY_MODES);
});

test("medium behavior matrix, progress totals, and replay agree", { timeout: 120_000 }, async () => {
  const bundle = await getBundle();
  const medium = bundle.trials.filter((trial) => trial.difficulty === "medium");
  assert.equal(medium.length, 20);
  const progress = Object.fromEntries(Object.keys(EXPECTED_PROGRESS).map((stage) => [stage, 0]));
  const matrix = Object.fromEntries(
    Object.keys(EXPECTED_MEDIUM_MATRIX).map((behavior) => [behavior, [0, 0, 0, 0, 0, 0]]),
  );

  for (const trial of medium) {
    const behavior = categoryId(trial.classifications?.failureBehavior);
    const stage = stageCode(trial);
    assert.ok(behavior in matrix, `${trial.trialId}: unexpected behavior ${behavior}`);
    assert.ok(stage in progress, `${trial.trialId}: unexpected progress ${stage}`);
    progress[stage] += 1;
    matrix[behavior][Number(stage.slice(1))] += 1;

    const extension = trial.extensions?.subgoals;
    assert.ok(Array.isArray(extension?.nodes));
    assert.ok(Array.isArray(extension?.frames));
    assert.ok(Array.isArray(extension?.transitions));
    assert.equal(
      extension?.replayValidation?.status,
      "matched",
      `${trial.trialId}: ${JSON.stringify(extension?.replayValidation?.mismatches ?? [])}`,
    );
    assert.deepEqual(extension?.replayValidation?.mismatches ?? [], []);
  }

  assert.deepEqual(progress, EXPECTED_PROGRESS);
  assert.deepEqual(matrix, EXPECTED_MEDIUM_MATRIX);
});

test("HTML embeds the exact bundle offline and exposes synchronized evidence views", { timeout: 120_000 }, async () => {
  const { bundle, html } = await getArtifacts();
  assert.match(html, /^<!doctype html>/i);
  assert.doesNotMatch(html, /<script\b[^>]*\bsrc\s*=/i);
  assert.doesNotMatch(html, /<link\b[^>]*\bhref\s*=/i);
  assert.doesNotMatch(html, /<(?:img|iframe|source)\b[^>]*\bsrc\s*=\s*["'](?:https?:)?\/\//i);
  assert.doesNotMatch(html, /@import\s+(?:url\()?["']?(?:https?:)?\/\//i);
  assert.doesNotMatch(html, /\b(?:fetch|EventSource|WebSocket)\s*\(\s*["']https?:\/\//i);
  assert.doesNotMatch(html, /radial-gradient\s*\(/i);
  const uiWithoutSourceRecords = html.replace(
    /<script\b[^>]*\bid=["']meeting-data["'][^>]*>[\s\S]*?<\/script>/i,
    "",
  );
  assert.doesNotMatch(uiWithoutSourceRecords, /(?:Â·|Ã—|â†’|â€¦)/);
  assert.doesNotMatch(html, /[A-Za-z]:[\\/](?:Users|Dev|tmp|Temp)[\\/]/i);
  assert.doesNotMatch(html, /\/(?:home|Users|tmp)\//i);
  assert.doesNotMatch(
    html,
    /(?:\.traj_eval_tmp|check_[0-9a-f]{8,}\.lean|(?:tmp|temp)[-_][A-Za-z0-9_-]+\.lean|<lean-temp>\.lean)/i,
  );

  const embedded = await Promise.resolve(extractEmbeddedBundle(html));
  assert.deepEqual(embedded, JSON.parse(JSON.stringify(bundle)));
  assert.match(html, /Search trials/i);
  assert.match(html, /data-trial-search/i);
  assert.match(html, /data-matrix-behavior/i);
  assert.match(html, /data-matrix-progress/i);
  assert.match(html, /data-clear-matrix-filter/i);
  assert.match(html, /Previous trace/i);
  assert.match(html, /data-previous-trace/i);
  assert.match(html, /Next trace/i);
  assert.match(html, /data-next-trace/i);
  assert.match(html, /Copy trace reference/i);
  assert.match(html, /data-copy-reference/i);
  assert.match(html, /One-shot contrast/i);
  assert.match(html, /easy_fatem_011_t0/);
  assert.match(html, /Recovery after compiler failure/i);
  assert.match(html, /First failed compiler result/i);
  assert.match(html, /Last failed compiler result/i);
  assert.match(html, /Terminal exact-target acceptance/i);
  assert.match(html, /Exact JSONL/i);
  assert.match(html, /Role graph/i);
  assert.match(html, /hashchange|URLSearchParams/i);
  assert.match(html, /<noscript\b/i);
});

test("Markdown is focused, linked, and generated from the same bundle", { timeout: 120_000 }, async () => {
  const { bundle, markdown } = await getArtifacts();
  assert.equal(markdown, renderMeetingMarkdown(bundle));
  assert.match(markdown, /^# Lean failure and recovery traces/m);
  assert.ok(markdown.includes("**82**"));
  assert.match(markdown, /4,430 events/);
  assert.match(markdown, /4,311 causal edges/);
  assert.match(markdown, /17 complete recovery traces/);
  assert.match(markdown, /easy_fatem_012_t1/);
  assert.match(markdown, /Earlier pass, regression, then terminal recovery/);
  assert.match(markdown, /Statement drift \/ false acceptance/);
  assert.match(markdown, /Medium failures: behavior × controller progress/);
  assert.match(markdown, /ledger accepted/i);
  assert.match(markdown, /lean_failure_modes_meeting\.html#trial=easy_fatem_012_t1&event=\d+&view=trace/);
  assert.doesNotMatch(markdown, /[A-Za-z]:[\\/](?:Users|Dev|tmp|Temp)[\\/]/i);
});

test("trace rows expand and decisive evidence opens automatically", { timeout: 120_000 }, async () => {
  const source = await readFile(resolve(reportRoot, "src", "meeting", "trace-view.ts"), "utf8");
  assert.match(source, /function isDecisiveEvent\s*\(/);
  assert.match(source, /data-event-disclosure/);
  assert.match(source, /data-event-decisive=/);
  assert.match(source, /\$\{open\s*\?\s*"open"\s*:\s*""\}/);
  assert.match(source, /selected\?\.eventId\s*===\s*event\.eventId/);
  assert.match(source, /check\?\.compiled\s*!=\s*null/);
  assert.match(source, /event\.role\.toLowerCase\(\)\s*===\s*"critic"/);

  const { html } = await getArtifacts();
  assert.match(html, /data-event-disclosure/);
  assert.match(html, /data-event-decisive/);
});

test("in-memory build is deterministic and every trace has a stable hash tuple", { timeout: 120_000 }, async () => {
  const first = await getArtifacts();
  const second = await Promise.resolve(createMeetingArtifacts({ repoRoot, reportRoot }));
  assert.equal(second.html, first.html);
  assert.equal(second.markdown, first.markdown);
  assert.deepEqual(second.summary, first.summary);

  for (const trial of first.bundle.trials) {
    const params = new URLSearchParams({
      trial: trial.trialId,
      event: String(trial.events[0].seq),
      view: "trace",
    });
    const decoded = new URLSearchParams(params.toString());
    assert.equal(decoded.get("trial"), trial.trialId);
    assert.equal(Number(decoded.get("event")), trial.events[0].seq);
    assert.equal(decoded.get("view"), "trace");
  }
});

test("responsive, keyboard, recovery-only navigation, and safe-route contracts remain present", async () => {
  const [mainSource, dashboardSource, modelSource, styles] = await Promise.all([
    readFile(resolve(reportRoot, "src", "meeting", "main.ts"), "utf8"),
    readFile(resolve(reportRoot, "src", "meeting", "dashboard-view.ts"), "utf8"),
    readFile(resolve(reportRoot, "src", "meeting", "model.ts"), "utf8"),
    readFile(resolve(reportRoot, "src", "meeting", "styles.css"), "utf8"),
  ]);

  assert.match(mainSource, /function invalidRouteNotice\s*\(/);
  assert.match(mainSource, /event\.key === "Escape"/);
  assert.match(mainSource, /"ArrowUp", "ArrowDown"/);
  assert.match(mainSource, /data-copy-reference/);
  assert.match(dashboardSource, /!isOneShotTrial\(trial\)/);
  assert.match(dashboardSource, /sectionPeers\.filter\(isRecoveryTrial\)/);
  assert.match(modelSource, /Earlier pass followed by regression and terminal recovery\./);
  assert.match(styles, /@media \(max-width: 820px\)/);
  assert.match(styles, /@media print/);
  assert.match(styles, /overflow-x:\s*auto/);
});
