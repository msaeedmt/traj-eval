export const BUNDLE_SCHEMA_VERSION = "meeting-dashboard.bundle.v1";
export const BUILD_VERSION = "meeting-dashboard-data.v1";

export const EXPECTED_SCOPE = Object.freeze({
  trialCount: 82,
  eventCount: 4430,
  causalEdgeCount: 4311,
  easyFailureCount: 44,
  mediumFailureCount: 20,
  recoverySuccessCount: 17,
  oneShotExemplarCount: 1,
});

export const RECOVERY_TRIAL_IDS = Object.freeze([
  "easy_fatem_012_t0",
  "easy_fatem_012_t1",
  "easy_fatem_012_t2",
  "easy_fatem_012_t3",
  "easy_fatem_012_t4",
  "easy_fatem_012_t5",
  "easy_fatem_012_t7",
  "easy_fatem_012_t8",
  "easy_fatem_012_t9",
  "easy_fatem_020_t0",
  "easy_fatem_020_t1",
  "easy_leancat_001_t1",
  "easy_leancat_001_t7",
  "easy_leancat_001_t9",
  "easy_leancat_002_t4",
  "easy_leancat_002_t7",
  "easy_leancat_002_t9",
]);

export const ONE_SHOT_EXEMPLAR_ID = "easy_fatem_011_t0";

export const MEETING_EXPERIMENTS = Object.freeze([
  {
    id: "qwen-easy-v1",
    label: "Easy Lean trials",
    description:
      "Qwen easy-task cohort with independent exact-target validation and reviewed failure diagnoses.",
    order: 1,
    adapter: "trace-jsonl",
    enrichers: ["easy-analysis", "meeting-taxonomy"],
    enricherOptions: {
      "easy-analysis": {
        recoveryTrialIds: RECOVERY_TRIAL_IDS,
        oneShotExemplarId: ONE_SHOT_EXEMPLAR_ID,
      },
    },
    metricProfile: "validated-target",
    rawDir: "data/batch/version_1_trial_traces",
    analysisPath:
      "docs/lean_easy_failure_report/public/data/lean_easy_failure_traces.json",
    capabilities: ["role_graph", "exact_json", "compiler_checks"],
  },
  {
    id: "qwen-medium-subgoals-v1",
    label: "Medium subgoal-tool trials",
    description:
      "Twenty medium Lean trials using the deterministic typed subgoal ledger.",
    order: 2,
    adapter: "trace-jsonl",
    enrichers: ["subgoal-ledger-replay", "meeting-taxonomy"],
    enricherOptions: {},
    metricProfile: "subgoal-ledger",
    rawDir: "data/batch/qwen_medium_subgoals_v1",
    summaryPath: "data/analysis/qwen_medium_subgoals_v1/summary.json",
    capabilities: [
      "role_graph",
      "exact_json",
      "compiler_checks",
      "subgoal_dag",
      "subgoal_history",
    ],
  },
]);

export const EASY_FAILURE_MODES = Object.freeze([
  {
    categoryId: "statement-drift",
    symptomCode: "statement_drift",
    label: "Statement drift / false acceptance",
    description:
      "The workflow approves a declaration that does not preserve the requested theorem statement.",
    order: 1,
    expectedCount: 5,
  },
  {
    categoryId: "opaque-verifier-feedback",
    symptomCode: "opaque_compiler_failure",
    label: "Opaque verifier feedback",
    description:
      "A failed Lean check returns no actionable diagnostic text.",
    order: 2,
    expectedCount: 15,
  },
  {
    categoryId: "application-type-mismatch",
    symptomCode: "application_type_mismatch",
    label: "Application / type mismatch",
    description:
      "A term or declaration is applied with an incompatible argument or result type.",
    order: 3,
    expectedCount: 7,
  },
  {
    categoryId: "typeclass-resolution",
    symptomCode: "typeclass_resolution",
    label: "Typeclass-resolution failure",
    description:
      "Lean cannot synthesize an instance required by the proposed proof term.",
    order: 4,
    expectedCount: 6,
  },
  {
    categoryId: "unknown-mathlib-api",
    symptomCode: "unknown_symbol",
    label: "Unknown Mathlib symbol / API",
    description:
      "The proof relies on a declaration or projection that is unavailable in the active Mathlib API.",
    order: 5,
    expectedCount: 5,
  },
  {
    categoryId: "target-not-attempted",
    symptomCode: "target_not_attempted",
    label: "Target never attempted",
    description:
      "The trace terminates without a Lean check of the supplied theorem.",
    order: 6,
    expectedCount: 6,
  },
]);

export const SUCCESS_PATTERNS = Object.freeze([
  {
    categoryId: "recovery",
    label: "Recovery after compiler failure",
    description:
      "At least one failed compiler result precedes the accepted exact-target result.",
    order: 1,
  },
  {
    categoryId: "one-shot",
    label: "One-shot exact-target success",
    description:
      "The first exact-target attempt is accepted with no earlier failed compiler result.",
    order: 2,
  },
]);

export const MEDIUM_PROGRESS_STAGES = Object.freeze([
  {
    categoryId: "p0-plan-only",
    label: "P0 · Plan only",
    description: "No returned check_lean result.",
    order: 0,
    expectedCount: 2,
  },
  {
    categoryId: "p1-compiler-engaged",
    label: "P1 · Compiler engaged",
    description: "Compiler evidence exists, but no subgoal review result is returned.",
    order: 1,
    expectedCount: 3,
  },
  {
    categoryId: "p2-critic-none-accepted",
    label: "P2 · Critic reached, none accepted",
    description: "At least one subgoal review is returned, but no node is ledger-accepted.",
    order: 2,
    expectedCount: 4,
  },
  {
    categoryId: "p3-one-ledger-accept",
    label: "P3 · One ledger milestone",
    description: "Exactly one node is ledger-accepted; the final theorem remains unverified.",
    order: 3,
    expectedCount: 7,
  },
  {
    categoryId: "p4-multiple-ledger-accepts",
    label: "P4 · Multiple ledger milestones",
    description: "At least two nodes are ledger-accepted; the final theorem remains unverified.",
    order: 4,
    expectedCount: 4,
  },
  {
    categoryId: "p5-verified-theorem",
    label: "P5 · Verified theorem",
    description: "Independent final exact-target validation passes.",
    order: 5,
    expectedCount: 0,
  },
]);

export const MEDIUM_FAILURE_BEHAVIORS = Object.freeze([
  {
    categoryId: "formalization-interface-barrier",
    label: "Formalization / interface barrier",
    description:
      "Lean rejects the identifier, application, rewrite, coercion, typeclass, or tactic interface used for the active node.",
    order: 1,
    expectedCount: 8,
  },
  {
    categoryId: "search-recovery-loop",
    label: "Search / recovery loop",
    description:
      "Searches, probes, or revisions repeat without producing another accepted artifact or executable invariant.",
    order: 2,
    expectedCount: 5,
  },
  {
    categoryId: "subgoal-scope-mismatch",
    label: "Subgoal-scope mismatch",
    description:
      "The candidate crosses the declared node boundary or substitutes a larger sorry-bearing artifact for the requested local result.",
    order: 3,
    expectedCount: 4,
  },
  {
    categoryId: "critic-acceptance-mismatch",
    label: "Critic-acceptance mismatch",
    description:
      "A node is accepted even though the critic feedback records that the declared objective is incomplete.",
    order: 4,
    expectedCount: 1,
  },
  {
    categoryId: "handoff-without-execution",
    label: "Handoff without execution",
    description:
      "A plan and route are recorded, but no returned compiler result follows.",
    order: 5,
    expectedCount: 2,
  },
]);

const behavior = (categoryId, evidenceSeqs = [], auditFlags = []) => ({
  categoryId,
  evidenceSeqs,
  auditFlags,
});

export const MEDIUM_REVIEWED_ASSIGNMENTS = Object.freeze({
  medium_fateh_001_t0: behavior("formalization-interface-barrier", [64, 161]),
  medium_fateh_001_t1: behavior("formalization-interface-barrier"),
  medium_fateh_001_t2: behavior("formalization-interface-barrier"),
  medium_fateh_001_t3: behavior("formalization-interface-barrier"),
  medium_fateh_001_t4: behavior("subgoal-scope-mismatch", [85, 88, 91, 122]),
  medium_fateh_001_t5: behavior("handoff-without-execution", [12, 14, 15, 19]),
  medium_fateh_001_t6: behavior("subgoal-scope-mismatch"),
  medium_fateh_001_t7: behavior("subgoal-scope-mismatch"),
  medium_fateh_001_t8: behavior("formalization-interface-barrier"),
  medium_fateh_001_t9: behavior("handoff-without-execution"),
  medium_leancat_008_t0: behavior("formalization-interface-barrier", [201]),
  medium_leancat_008_t1: behavior("search-recovery-loop"),
  medium_leancat_008_t2: behavior("search-recovery-loop"),
  medium_leancat_008_t3: behavior("search-recovery-loop"),
  medium_leancat_008_t4: behavior("formalization-interface-barrier"),
  medium_leancat_008_t5: behavior(
    "critic-acceptance-mismatch",
    [101, 131, 201],
    ["scope-disputed-acceptance"],
  ),
  medium_leancat_008_t6: behavior("search-recovery-loop"),
  medium_leancat_008_t7: behavior(
    "subgoal-scope-mismatch",
    [150],
    ["accepted-artifact-in-sorry-bearing-context"],
  ),
  medium_leancat_008_t8: behavior("formalization-interface-barrier"),
  medium_leancat_008_t9: behavior("search-recovery-loop", [100, 199, 201]),
});

export const AUDIT_FLAGS = Object.freeze([
  {
    categoryId: "scope-disputed-acceptance",
    label: "Scope-disputed ledger acceptance",
    description:
      "The critic accepted a node while its feedback stated that the declared objective was not fully established.",
    order: 1,
  },
  {
    categoryId: "accepted-artifact-in-sorry-bearing-context",
    label: "Accepted local artifact in sorry-bearing context",
    description:
      "The accepted local definition is valid, but it appears inside a larger theorem body that still contains sorry.",
    order: 2,
  },
]);

export const METRIC_DEFINITIONS = Object.freeze([
  {
    metricId: "recovery_success_count",
    label: "Recovery successes",
    unit: "trials",
    definition:
      "Solved exact-target trials with at least one failed compiler result whose result sequence precedes the accepted exact-target result sequence.",
  },
  {
    metricId: "ledger_accepted_nodes",
    label: "Ledger-accepted subgoals",
    unit: "nodes",
    definition:
      "Terminal subgoal nodes with controller status accepted. This is a workflow-ledger measure, not a count or percentage of proved theorems.",
  },
  {
    metricId: "verified_completion_count",
    label: "Verified final completions",
    unit: "trials",
    definition:
      "Trials whose independent final exact-target validation explicitly passed.",
  },
  {
    metricId: "compiler_result_count",
    label: "Returned compiler results",
    unit: "results",
    definition:
      "Matched check_lean tool calls with a returned execution result; unmatched calls are excluded and reported separately.",
  },
]);

export const TAXONOMIES = Object.freeze([
  {
    axisId: "easy-failure-mode",
    label: "Easy failure mode",
    description: "Reviewed primary failure recorded in the easy analysis snapshot.",
    exclusive: true,
    categories: EASY_FAILURE_MODES,
  },
  {
    axisId: "success-pattern",
    label: "Success pattern",
    description: "One-shot or compiler-error recovery among shown solved trials.",
    exclusive: true,
    categories: SUCCESS_PATTERNS,
  },
  {
    axisId: "medium-progress-stage",
    label: "Medium controller progress",
    description:
      "Deterministic stage derived from returned compiler evidence, subgoal reviews, ledger acceptance, and final validation.",
    exclusive: true,
    categories: MEDIUM_PROGRESS_STAGES,
  },
  {
    axisId: "medium-failure-behavior",
    label: "Medium dominant observed failure behavior",
    description:
      "Exploratory manually reviewed presentation label; it is not a causal or gold-standard annotation.",
    exclusive: true,
    categories: MEDIUM_FAILURE_BEHAVIORS,
  },
  {
    axisId: "audit-flag",
    label: "Audit flag",
    description: "Non-exclusive evidence-quality qualifications.",
    exclusive: false,
    categories: AUDIT_FLAGS,
  },
]);

export const VIEWS = Object.freeze([
  {
    id: "failure-tree",
    label: "Failures",
    order: 1,
    sectionId: "failures",
    groupAxisIds: ["easy-failure-mode", "medium-failure-behavior"],
  },
  {
    id: "success-tree",
    label: "Success contrasts",
    order: 2,
    sectionId: "successes",
    groupAxisIds: ["success-pattern"],
  },
  {
    id: "medium-progress-matrix",
    label: "Medium failure behavior × progress",
    order: 3,
    sectionId: "failures",
    rowAxisId: "medium-failure-behavior",
    columnAxisId: "medium-progress-stage",
  },
]);
