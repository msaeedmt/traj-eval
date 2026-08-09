"""Interactive dashboard over data/batch/*: single-batch, multi-batch
comparison, and single-trial views. Nothing here is hardcoded to a specific
arm/model/phase -- every number comes from traj_eval.metrics.lean.batch_report,
which reads it fresh off the trial JSONL files (and, when kernel validation is
turned on, off a live LeanCompiler), the same way scripts/analyze_batch.py and
scripts/compare_offline_kernel.py do.

Run with:
    uv run streamlit run src/traj_eval/dashboard/app.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from traj_eval.metrics.lean.batch_report import (
    KNOWN_TOOLS,
    BatchMeta,
    build_batch_report,
    build_comparison_report,
    build_tool_usage_report,
    discover_batches,
    list_trial_files,
    load_trial_detail,
)
from traj_eval.trace_core.schema import EventType

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BATCH_ROOT = PROJECT_ROOT / "data" / "batch"
DEFAULT_DATASET_ROOT = PROJECT_ROOT / "dataset" / "Lean"
DEFAULT_LEAN_PROJECT = Path.home() / "lean_anchor"

st.set_page_config(page_title="Lean Anchor batch dashboard", layout="wide")


# --------------------------------------------------------------------------
# Cached resources: kernel + dataset tasks are expensive, so they are built
# once per session and reused across every report on this page.
# --------------------------------------------------------------------------


@st.cache_resource(show_spinner="Starting Lean compiler (first call is slow)...")
def _get_compiler(project_dir: str):
    from traj_eval.tools.lean_compiler import LeanCompiler

    return LeanCompiler(Path(project_dir))


@st.cache_resource(show_spinner="Loading task dataset...")
def _get_tasks(dataset_root: str):
    from traj_eval.dataset.loader import load_dataset, to_lean_task

    return {r.id: to_lean_task(r) for r in load_dataset(Path(dataset_root))}


@st.cache_data(show_spinner=False)
def _discover(batch_root: str) -> list[BatchMeta]:
    return discover_batches(Path(batch_root))


@st.cache_data(show_spinner="Reading batch (offline)...")
def _cached_batch_report(folder: str, difficulty: str | None):
    return build_batch_report(Path(folder), difficulty=difficulty)


@st.cache_data(show_spinner="Reading tool-usage stats...")
def _cached_tool_usage(folder: str, difficulty: str | None):
    return build_tool_usage_report(Path(folder), difficulty=difficulty)


# Kernel-bound reports cannot be st.cache_data'd directly (compiler is not
# hashable/picklable); key the cache manually on folder+difficulty instead and
# store the *result* (plain dataclasses of primitives), not the compiler.
def _validated_batch_report(
    folder: str, difficulty: str | None, project_dir: str, dataset_root: str
):
    key = ("batch", folder, difficulty, project_dir, dataset_root)
    if key not in st.session_state:
        compiler = _get_compiler(project_dir)
        tasks = _get_tasks(dataset_root)
        st.session_state[key] = build_batch_report(
            Path(folder), difficulty=difficulty, compiler=compiler, tasks=tasks
        )
    return st.session_state[key]


def _comparison_report(folder: str, difficulty: str | None, project_dir: str, dataset_root: str):
    key = ("cmp", folder, difficulty, project_dir, dataset_root)
    if key not in st.session_state:
        compiler = _get_compiler(project_dir)
        tasks = _get_tasks(dataset_root)
        st.session_state[key] = build_comparison_report(
            Path(folder), tasks, compiler, difficulty=difficulty
        )
    return st.session_state[key]


# --------------------------------------------------------------------------
# Shared sidebar: where the data lives.
# --------------------------------------------------------------------------

st.sidebar.title("Lean Anchor batch dashboard")
batch_root = st.sidebar.text_input("Batch root", value=str(DEFAULT_BATCH_ROOT))
dataset_root = st.sidebar.text_input("Dataset root", value=str(DEFAULT_DATASET_ROOT))
lean_project = st.sidebar.text_input(
    "Lean project (for kernel validation)", value=str(DEFAULT_LEAN_PROJECT)
)

mode = st.sidebar.radio(
    "View",
    ["Single batch", "Compare batches", "Trial viewer"],
    help="Single batch: one config's stats. Compare batches: side-by-side across configs. "
    "Trial viewer: one trial's raw event timeline.",
)

batches = _discover(batch_root)
if not batches:
    st.error(f"No batch folders with trial JSONL files found under {batch_root}.")
    st.stop()

batch_by_name = {b.name: b for b in batches}


def _difficulty_selector(key: str) -> str | None:
    choice = st.selectbox("Difficulty filter", ["all", "easy", "medium", "hard"], key=key)
    return None if choice == "all" else choice


def _task_rows_df(report) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "task": r.task,
                "n": r.n,
                "success": r.success,
                "fail": r.fail,
                "rate": r.rate,
                "thrash": r.thrash,
                **({"silent": r.silent} if report.validated else {}),
            }
            for r in report.rows
        ]
    )


def _tool_usage_df(tu) -> pd.DataFrame:
    rows = []
    for role, tools in tu.calls.items():
        for tool, n in tools.items():
            rows.append(
                {
                    "role": role,
                    "tool": tool,
                    "calls": n,
                    "calls_per_trial": n / tu.n_trials if tu.n_trials else 0.0,
                    "trials_used": tu.trials_with_tool.get(role, {}).get(tool, 0),
                    "trial_rate": tu.tool_rate(role, tool),
                }
            )
    return pd.DataFrame(rows)


def _malformed_df(tu) -> pd.DataFrame:
    if not tu.malformed_tool_calls:
        return pd.DataFrame(columns=["role", "tool_name", "trial"])
    return pd.DataFrame(
        [
            {"role": m.role, "tool_name": m.tool_name, "trial": m.trial}
            for m in tu.malformed_tool_calls
        ]
    )


# --------------------------------------------------------------------------
# Mode 1: Single batch
# --------------------------------------------------------------------------

if mode == "Single batch":
    name = st.sidebar.selectbox(
        "Batch folder",
        list(batch_by_name),
        format_func=lambda n: batch_by_name[n].label,
    )
    meta = batch_by_name[name]
    difficulty = _difficulty_selector("single_difficulty")
    validate_on = st.sidebar.checkbox(
        "Enable kernel validation (slow first run; needs a built Lean project)"
    )

    st.header(meta.label)
    cols = st.columns(4)
    cols[0].metric("Phase", meta.phase or "—")
    cols[1].metric("Arm", meta.arm_id or "—")
    cols[2].metric("Trial files", meta.n_trial_files)
    cols[3].metric("Trials/task (config)", meta.trials_per_task or "—")
    if meta.models:
        st.caption(
            "Models: " + " · ".join(f"**{role}**: {model}" for role, model in meta.models.items())
        )

    if validate_on:
        try:
            report = _validated_batch_report(str(meta.path), difficulty, lean_project, dataset_root)
        except Exception as e:  # noqa: BLE001 -- kernel/project may not be set up
            st.error(f"Kernel validation unavailable: {type(e).__name__}: {e}")
            report = _cached_batch_report(str(meta.path), difficulty)
    else:
        report = _cached_batch_report(str(meta.path), difficulty)

    if report.skipped:
        with st.expander(f"{len(report.skipped)} file(s) skipped"):
            for fname, err in report.skipped:
                st.text(f"{fname}: {err}")

    if not report.rows:
        st.warning("No matching trial logs for this filter.")
        st.stop()

    m = st.columns(4)
    m[0].metric("Total trials", report.total_n)
    m[1].metric("Success rate", f"{report.total_rate:.0%}")
    m[2].metric("Successes", report.total_success)
    if report.validated:
        m[3].metric("Silent failures", sum(r.silent for r in report.rows))

    df = _task_rows_df(report)
    st.subheader("Per-task success/failure")
    fig = px.bar(
        df.sort_values("rate"),
        x="rate",
        y="task",
        orientation="h",
        color="thrash",
        color_continuous_scale="Reds",
        hover_data=["n", "success", "fail", "thrash"] + (["silent"] if report.validated else []),
        title=None,
    )
    fig.update_layout(height=max(320, 24 * len(df)), xaxis_tickformat=".0%")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(df, width="stretch", hide_index=True)

    if validate_on:
        st.subheader("Offline vs. kernel disagreement")
        try:
            cmp = _comparison_report(str(meta.path), difficulty, lean_project, dataset_root)
            c = st.columns(4)
            c[0].metric("Agree", cmp.total - len(cmp.silent) - len(cmp.offline_miss))
            c[1].metric("Silent failures", len(cmp.silent), help="offline PASS, kernel FAIL")
            c[2].metric("Offline misses", len(cmp.offline_miss), help="offline FAIL, kernel PASS")
            c[3].metric("Disagreement", f"{cmp.disagreement_rate:.1%}")
            if cmp.silent:
                st.markdown("**Silent failures**")
                st.dataframe(
                    pd.DataFrame(
                        [{"trial": r.trial, "reasons": ", ".join(r.reasons)} for r in cmp.silent]
                    ),
                    hide_index=True,
                    width="stretch",
                )
            if cmp.offline_miss:
                st.markdown("**Offline misses** (kernel accepted, offline signal missed it)")
                st.dataframe(
                    pd.DataFrame([{"trial": r.trial} for r in cmp.offline_miss]),
                    hide_index=True,
                    width="stretch",
                )
        except Exception as e:  # noqa: BLE001
            st.error(f"Comparison unavailable: {type(e).__name__}: {e}")

    st.subheader("Tool-call usage")
    tu = _cached_tool_usage(str(meta.path), difficulty)
    tdf = _tool_usage_df(tu)
    if tdf.empty:
        st.info("No tool calls found.")
    else:
        cc = st.columns(2)
        cc[0].metric(
            "Critic self-check rate (calls check_lean itself)", f"{tu.critic_self_check_rate:.0%}"
        )
        cc[1].metric(
            "Critic text-verdict rate",
            f"{tu.critic_text_verdict_trials / tu.n_trials:.0%}" if tu.n_trials else "—",
        )
        fig2 = px.bar(
            tdf,
            x="tool",
            y="trial_rate",
            color="role",
            barmode="group",
            title="Share of trials where a role calls each tool at least once",
        )
        fig2.update_layout(yaxis_tickformat=".0%")
        st.plotly_chart(fig2, width="stretch")
        st.dataframe(tdf.sort_values(["role", "tool"]), hide_index=True, width="stretch")

    mdf = _malformed_df(tu)
    if not mdf.empty:
        st.markdown(
            f"**{len(mdf)} malformed/unrecognized tool call(s)** "
            f"(name outside {sorted(KNOWN_TOOLS)}, or a verdict emitted as a tool call "
            "instead of text)"
        )
        st.dataframe(mdf, hide_index=True, width="stretch")


# --------------------------------------------------------------------------
# Mode 2: Compare batches
# --------------------------------------------------------------------------

elif mode == "Compare batches":
    names = st.sidebar.multiselect(
        "Batches to compare",
        list(batch_by_name),
        default=list(batch_by_name)[: min(3, len(batch_by_name))],
        format_func=lambda n: batch_by_name[n].label,
    )
    difficulty = _difficulty_selector("cmp_difficulty")
    validate_on = st.sidebar.checkbox(
        "Enable kernel validation for all selected batches (slow)", key="cmp_validate"
    )

    if not names:
        st.info("Pick at least one batch in the sidebar.")
        st.stop()

    summary_rows = []
    per_task = {}
    tool_rows = []
    for name in names:
        meta = batch_by_name[name]
        if validate_on:
            try:
                report = _validated_batch_report(
                    str(meta.path), difficulty, lean_project, dataset_root
                )
            except Exception as e:  # noqa: BLE001
                st.error(f"{meta.label}: kernel validation unavailable: {e}")
                report = _cached_batch_report(str(meta.path), difficulty)
        else:
            report = _cached_batch_report(str(meta.path), difficulty)

        disagreement = None
        if validate_on:
            try:
                cmp = _comparison_report(str(meta.path), difficulty, lean_project, dataset_root)
                disagreement = cmp.disagreement_rate
            except Exception:  # noqa: BLE001
                disagreement = None

        tu = _cached_tool_usage(str(meta.path), difficulty)
        summary_rows.append(
            {
                "batch": meta.label,
                "phase": meta.phase,
                "arm": meta.arm_id,
                "n_trials": report.total_n,
                "success_rate": report.total_rate,
                "disagreement_rate": disagreement,
                "critic_self_check_rate": tu.critic_self_check_rate,
                "try_tactic_rate(engineer)": tu.tool_rate("engineer", "try_tactic"),
                "show_goals_rate(engineer)": tu.tool_rate("engineer", "show_goals"),
                "malformed_tool_calls": len(tu.malformed_tool_calls),
            }
        )
        per_task[meta.label] = {r.task: r.rate for r in report.rows}
        for role, tools in tu.calls.items():
            for tool in tools:
                tool_rows.append(
                    {
                        "batch": meta.label,
                        "role": role,
                        "tool": tool,
                        "rate": tu.tool_rate(role, tool),
                    }
                )

    sdf = pd.DataFrame(summary_rows)
    st.subheader("Summary")
    st.dataframe(sdf, hide_index=True, width="stretch")

    fig = px.bar(sdf, x="batch", y="success_rate", title="Success rate by batch")
    fig.update_layout(yaxis_tickformat=".0%")
    st.plotly_chart(fig, width="stretch")

    if validate_on and sdf["disagreement_rate"].notna().any():
        fig = px.bar(
            sdf, x="batch", y="disagreement_rate", title="Offline vs. kernel disagreement rate"
        )
        fig.update_layout(yaxis_tickformat=".0%")
        st.plotly_chart(fig, width="stretch")

    st.subheader("Critic self-verification rate")
    fig = px.bar(
        sdf,
        x="batch",
        y="critic_self_check_rate",
        title="Trials where the critic itself calls check_lean",
    )
    fig.update_layout(yaxis_tickformat=".0%")
    st.plotly_chart(fig, width="stretch")

    st.subheader("Tool usage rate by role/tool, across batches")
    tdf = pd.DataFrame(tool_rows)
    if not tdf.empty:
        role_pick = st.multiselect(
            "Roles", sorted(tdf["role"].unique()), default=sorted(tdf["role"].unique())
        )
        tdf = tdf[tdf["role"].isin(role_pick)]
        fig = px.bar(
            tdf,
            x="tool",
            y="rate",
            color="batch",
            facet_col="role",
            barmode="group",
            title="Share of trials with >=1 call, by tool/role/batch",
        )
        fig.update_layout(yaxis_tickformat=".0%")
        st.plotly_chart(fig, width="stretch")

    st.subheader("Per-task success rate heatmap")
    all_tasks = sorted({t for d in per_task.values() for t in d})
    if all_tasks:
        z = [[per_task[b].get(t) for t in all_tasks] for b in per_task]
        heat = go.Figure(
            data=go.Heatmap(
                z=z,
                x=all_tasks,
                y=list(per_task.keys()),
                colorscale="RdYlGn",
                zmin=0,
                zmax=1,
                colorbar={"tickformat": ".0%"},
            )
        )
        heat.update_layout(height=max(300, 40 * len(per_task)), xaxis_tickangle=-45)
        st.plotly_chart(heat, width="stretch")


# --------------------------------------------------------------------------
# Mode 3: Trial viewer
# --------------------------------------------------------------------------

else:
    name = st.sidebar.selectbox(
        "Batch folder", list(batch_by_name), format_func=lambda n: batch_by_name[n].label
    )
    meta = batch_by_name[name]
    files = list_trial_files(meta.path)
    if not files:
        st.warning("No trial files in this batch.")
        st.stop()

    labels = {f: f.name for f in files}
    file_choice = st.sidebar.selectbox("Trial", files, format_func=lambda f: labels[f])

    detail = load_trial_detail(file_choice)
    st.header(f"{detail.task}  ·  trial {detail.trial_index}")
    st.caption(str(file_choice))

    m = st.columns(5)
    m[0].metric("Offline success", "yes" if detail.offline_success else "no")
    m[1].metric("Declared success (critic)", "yes" if detail.artifacts.declared_success else "no")
    m[2].metric("check_lean calls", detail.artifacts.n_tool_calls)
    m[3].metric("Failed compiles", detail.artifacts.n_failed_compiles)
    m[4].metric("Submitted == last verified", str(detail.artifacts.submitted_eq_last_verified))

    validate_on = st.checkbox("Run kernel validation on this trial")
    if validate_on:
        try:
            compiler = _get_compiler(lean_project)
            tasks = _get_tasks(dataset_root)
            if detail.task not in tasks:
                st.warning(f"Task '{detail.task}' not found in dataset at {dataset_root}.")
            else:
                from traj_eval.metrics.lean.validator import validate as validate_trial

                tm = validate_trial(detail.events, tasks[detail.task], compiler=compiler)
                vc = st.columns(4)
                vc[0].metric("Compiles", str(tm.final_proof_compiles))
                vc[1].metric("Sorry-free", str(tm.final_proof_sorry_free))
                vc[2].metric("Statement preserved", str(tm.statement_preserved))
                vc[3].metric("Axiom clean", str(tm.axiom_clean))
                if tm.extra_axioms:
                    st.warning(f"Extra axioms: {tm.extra_axioms}")
                if tm.silent_failure:
                    st.error("SILENT FAILURE: declared success, kernel rejects.")
        except Exception as e:  # noqa: BLE001
            st.error(f"Kernel validation unavailable: {type(e).__name__}: {e}")

    with st.expander("Submitted proof"):
        st.code(detail.artifacts.submitted or "(none)", language="lean")
    with st.expander("Last verified (compiled) code"):
        st.code(detail.artifacts.last_verified or "(none)", language="lean")

    st.subheader("Tool call counts")
    st.dataframe(
        pd.DataFrame(
            [{"tool": t, "calls": n} for t, n in detail.artifacts.tool_call_counts.items()]
        ),
        hide_index=True,
        width="stretch",
    )

    st.subheader("Event timeline")
    role_filter = st.multiselect(
        "Roles",
        sorted({str(e.agent_role) for e in detail.events}),
        default=sorted({str(e.agent_role) for e in detail.events}),
    )
    for e in detail.events:
        if str(e.agent_role) not in role_filter:
            continue
        label = f"#{e.seq} · {e.agent_role} · {e.event_type}"
        with st.expander(label):
            if e.event_type is EventType.MESSAGE:
                text = e.payload.get("text")
                if text:
                    st.markdown(text)
                else:
                    st.json(e.payload)
            elif e.event_type is EventType.TOOL_CALL:
                for tc in e.payload.get("tool_calls") or []:
                    st.markdown(f"**{tc.get('name')}**")
                    args = tc.get("arguments")
                    st.code(args if isinstance(args, str) else str(args))
            elif e.event_type is EventType.EXECUTION_RESULT:
                st.json(e.payload)
            else:
                st.json(e.payload)
