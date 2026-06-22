from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = Path("tests/engineer/evidence/stargazer_true_task")
SUPPORT_REL = Path("notebooks/qwen_saeed_stargazer_real1/support")
EXPECTED_TOOLS = ["write_file", "run", "run", "git_status", "git_diff", "finish"]
LEGACY_PLACEHOLDER_WORD = "smo" + "ke"
PRIVATE_MARKERS = [
    "local" + "_" + "reference",
    "Science" + "-" + "Work" + "-" + "Flow",
    "C:" + "\\Dev",
    "C:" + "\\Users",
    ".".join(["131", "220", "150", "238"]),
    "sk" + "-proj" + "-",
]


def _load_json(rel_path: Path) -> dict:
    return json.loads((REPO / rel_path).read_text(encoding="utf-8"))


def _artifact_index() -> dict:
    return _load_json(EVIDENCE_ROOT / "artifact_index.json")


def _run_rel() -> Path:
    return Path(_artifact_index()["run_dir"]).relative_to(EVIDENCE_ROOT)


def _required_artifacts(run_rel: Path) -> list[Path]:
    return [
        Path("artifact_index.json"),
        Path("planner_record.json"),
        Path("critic_criteria.json"),
        Path("critic_review.json"),
        Path("README.md"),
        run_rel / "after_branch.txt",
        run_rel / "after_cached_diff.patch",
        run_rel / "after_diff.patch",
        run_rel / "after_head.txt",
        run_rel / "after_status.txt",
        run_rel / "before_branch.txt",
        run_rel / "before_cached_diff.patch",
        run_rel / "before_diff.patch",
        run_rel / "before_head.txt",
        run_rel / "before_status.txt",
        run_rel / "changed_files.json",
        run_rel / "critic_read_me.md",
        run_rel / "engineer_prompt.md",
        run_rel / "events.jsonl",
        run_rel / "example_engineer_actions.jsonl",
        run_rel / "qwen_actions.jsonl",
        run_rel / "qwen_config_redacted.json",
        run_rel / "qwen_engineer_response_turn_01.txt",
        run_rel / "qwen_engineer_response_turn_02.txt",
        run_rel / "qwen_engineer_response_turn_03.txt",
        run_rel / "qwen_engineer_response_turn_04.txt",
        run_rel / "qwen_engineer_response_turn_05.txt",
        run_rel / "qwen_engineer_response_turn_06.txt",
        run_rel / "qwen_monitor.jsonl",
        run_rel / "run_manifest.json",
        run_rel / "task.md",
        run_rel / "tool_outputs/0008_run.stdout.txt",
        run_rel / "tool_outputs/0008_run.stderr.txt",
        run_rel / "tool_outputs/0012_run.stdout.txt",
        run_rel / "tool_outputs/0012_run.stderr.txt",
        run_rel / "tool_outputs/0016_git_status.txt",
        run_rel / "tool_outputs/0020_git_diff.patch",
        run_rel / "trace_validation.json",
        run_rel / "version_index.json",
        Path("workdir/stargazer_engineer_script.py"),
        Path("workdir/stargazer_workdir/agent_submission.json"),
        Path("workdir/stargazer_workdir/fit_diagnostics.json"),
    ]


def test_qwen_stargazer_true_task_artifact_is_complete() -> None:
    artifact_index = _artifact_index()
    assert artifact_index["schema"] == "traj_eval_qwen_engineer_true_stargazer_task_v1"
    assert LEGACY_PLACEHOLDER_WORD not in artifact_index["description"].lower()

    run_rel = _run_rel()
    for rel in _required_artifacts(run_rel):
        assert (REPO / EVIDENCE_ROOT / rel).exists(), rel

    manifest = _load_json(EVIDENCE_ROOT / run_rel / "run_manifest.json")
    trace_validation = _load_json(EVIDENCE_ROOT / run_rel / "trace_validation.json")
    critic_review = _load_json(EVIDENCE_ROOT / "critic_review.json")

    assert manifest["task_id"] == "stargazer_real_001_qwen_true_task"
    assert manifest["qwen"]["ok"] is True
    assert manifest["qwen"]["mode"] == "interactive_tools"
    assert manifest["qwen"]["turn_count"] == 6
    assert manifest["qwen"]["action_count"] == 6
    assert manifest["qwen_interactive_tools"] is True
    assert manifest["run_diagnosis"]["classification"] == "completed_with_verification"
    assert manifest["run_diagnosis"]["tools_requested"] == EXPECTED_TOOLS
    assert manifest["run_diagnosis"]["run_returncodes"] == [0, 0]
    assert manifest["run_diagnosis"]["failed_tools"] == []
    assert manifest["trace_validation"]["ok"] is True
    assert trace_validation["ok"] is True
    assert trace_validation["event_count"] == 24
    assert critic_review["verdict"] == "APPROVE"

    actions = [
        json.loads(line)
        for line in (REPO / EVIDENCE_ROOT / run_rel / "qwen_actions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [action["tool"] for action in actions] == EXPECTED_TOOLS
    assert (REPO / EVIDENCE_ROOT / run_rel / "tool_outputs/0012_run.stdout.txt").read_text(encoding="utf-8").strip() == "1"


def test_qwen_stargazer_true_task_is_not_placeholder() -> None:
    run_rel = _run_rel()
    script = (REPO / EVIDENCE_ROOT / "workdir/stargazer_engineer_script.py").read_text(encoding="utf-8")
    submission = _load_json(EVIDENCE_ROOT / "workdir/stargazer_workdir/agent_submission.json")
    diagnostics = _load_json(EVIDENCE_ROOT / "workdir/stargazer_workdir/fit_diagnostics.json")

    lowered_script = script.lower()
    assert LEGACY_PLACEHOLDER_WORD not in lowered_script
    assert "search_period" in lowered_script or "least_squares" in lowered_script
    assert "fit_diagnostics" in lowered_script
    assert '"P_days": 100.0' not in script
    assert '"m_sin_i_mjup": 0.1' not in script
    assert '"sigma_jitter_ms": 1.0' not in script

    planet = submission["planets"][0]
    assert planet["P_days"] > 0.0
    assert planet["m_sin_i_mjup"] > 0.0
    assert submission["noise"]["sigma_jitter_ms"] > 0.0
    assert abs(float(planet["P_days"]) - 100.0) > 1e-6
    assert abs(float(planet["m_sin_i_mjup"]) - 0.1) > 1e-6
    assert abs(float(submission["noise"]["sigma_jitter_ms"]) - 1.0) > 1e-6
    assert submission["metadata"]["source"] == "qwen_public_fit"
    assert submission["metadata"].get("fit_method")

    assert diagnostics["tested_period_count"] >= 100
    assert diagnostics["best_period_days"] == planet["P_days"]
    assert diagnostics["m_sin_i_mjup"] == planet["m_sin_i_mjup"]
    assert diagnostics["sigma_jitter_ms"] == submission["noise"]["sigma_jitter_ms"]
    assert diagnostics["residual_rms_ms"] > 0.0

    support = REPO / SUPPORT_REL
    if str(support) not in sys.path:
        sys.path.insert(0, str(support))
    from stargazer.evaluator import _parse_submission_planets

    assert len(_parse_submission_planets(submission, "params_and_model")) == 1
    assert LEGACY_PLACEHOLDER_WORD not in (REPO / EVIDENCE_ROOT / run_rel / "task.md").read_text(encoding="utf-8").lower()


def test_stargazer_true_task_evidence_is_shareable() -> None:
    for path in (REPO / EVIDENCE_ROOT).rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            for marker in PRIVATE_MARKERS:
                assert marker not in text, f"{marker!r} leaked in {path}"
            assert "stargazer_" + LEGACY_PLACEHOLDER_WORD not in text
            assert "stargazer_engineer_" + LEGACY_PLACEHOLDER_WORD not in text
