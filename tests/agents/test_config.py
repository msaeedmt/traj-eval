from __future__ import annotations

import pytest

pytest.importorskip("autogen", reason="agents extra (ag2) not installed")

from traj_eval.agents.config import build_llm_config


def test_qwen_thinking_setting_flows_to_openai_extra_body(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    config = build_llm_config(
        model="openai/Qwen3.5-27B.gguf",
        max_tokens=384,
        enable_thinking=False,
        timeout_seconds=45,
    )

    entry = config.config_list[0]
    assert entry["max_tokens"] == 384
    assert entry["timeout"] == 45
    assert entry["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": False}
    }


def test_provider_default_omits_qwen_specific_extra_body(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    config = build_llm_config(model="gpt-4o-mini")

    assert config.config_list[0].get("extra_body") is None


def test_provider_limits_must_be_positive(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with pytest.raises(ValueError, match="max_tokens"):
        build_llm_config(max_tokens=0)
    with pytest.raises(ValueError, match="timeout_seconds"):
        build_llm_config(timeout_seconds=0)
