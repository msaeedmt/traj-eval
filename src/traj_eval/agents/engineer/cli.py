from __future__ import annotations

import argparse
import sys

from .session import run_session


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Codex-style file/tool engineer agent for traj-eval."
    )
    parser.add_argument("--task-id", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--task")
    source.add_argument("--task-file")
    source.add_argument("--step-file", help="JSON step context produced by the outer runtime.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--actions-file", help="JSONL actions produced by the engineer model.")
    parser.add_argument("--allow-shell", action="store_true", help="Allow run tool actions to execute shell commands.")
    parser.add_argument("--write-prompt-only", action="store_true", help="Only write prompt/schema artifacts.")
    parser.add_argument("--qwen", action="store_true", help="Call the configured OpenAI-compatible Qwen endpoint for engineer actions.")
    parser.add_argument("--execute-qwen-actions", action="store_true", help="Execute qwen_actions.jsonl after a successful Qwen call.")
    parser.add_argument("--qwen-interactive-tools", action="store_true", help="Send tool results back to Qwen for multiple tool turns.")
    parser.add_argument("--max-tool-turns", type=int, default=6, help="Maximum Qwen tool-result turns when --qwen-interactive-tools is enabled.")
    parser.add_argument("--provider-env", help="Env file with OPENAI_BASE_URL/OPENAI_API_KEY/model.")
    parser.add_argument("--qwen-model", help="Qwen model override.")
    parser.add_argument("--qwen-timeout", type=float, help="OpenAI client request timeout in seconds.")
    parser.add_argument("--qwen-max-retries", type=int, help="OpenAI client max retries.")
    parser.add_argument("--qwen-max-tokens", type=int, default=8000)
    parser.add_argument("--qwen-enable-thinking", action="store_true", help="Enable Qwen thinking; default off to improve JSONL action parsing.")
    parser.add_argument("--monitor-interval", type=float, default=15.0)
    parser.add_argument("--context-file", action="append", help="Repo-relative file to inline into the engineer prompt.")
    parser.add_argument("--artifact-rel", action="append", help="Repo-relative private artifact path or directory to list in run_manifest.json.")
    parser.add_argument("--run-root-rel", default="runs/engineer", help="Repo-relative root for engineer run artifacts.")
    parser.add_argument("--skip-changed-files", action="store_true", help="Do not snapshot dirty worktree files into run artifacts.")
    parser.add_argument("--skip-repo-guard", action="store_true")
    parser.add_argument("--create-branch", action="store_true")
    parser.add_argument("--branch-prefix", default="engineer/")
    parser.add_argument("--allow-dirty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    run_session(parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
