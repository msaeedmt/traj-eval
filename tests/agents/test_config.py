from __future__ import annotations

import pytest

pytest.importorskip("autogen", reason="agents extra (ag2) not installed")

from traj_eval.agents.config import build_llm_config


def test_qwen_limits_flow_to_openai_config(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    config = build_llm_config(
        model="openai/Qwen3.5-27B.gguf",
        max_tokens=384,
        enable_thinking=False,
        json_mode=True,
        timeout_seconds=45,
        max_retries=0,
    )

    entry = config.config_list[0]
    assert entry["max_tokens"] == 384
    assert entry["timeout"] == 45
    assert entry["max_retries"] == 0
    assert entry["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": False}
    }
    assert entry["response_format"] == {"type": "json_object"}


def test_provider_default_omits_qwen_extra_body(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    config = build_llm_config(model="gpt-4o-mini")

    assert config.config_list[0].get("extra_body") is None
    assert config.config_list[0].get("max_retries") is None


def test_explicit_provider_route_does_not_depend_on_process_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "stale-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://stale.invalid/v1")

    config = build_llm_config(
        model="qwen",
        api_key="file-key",
        base_url="https://qwen.invalid/v1",
    )

    entry = config.config_list[0]
    assert entry["api_key"] == "file-key"
    assert str(entry["base_url"]) == "https://qwen.invalid/v1"


def test_provider_limits_must_be_positive(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with pytest.raises(ValueError, match="max_tokens"):
        build_llm_config(max_tokens=0)
    with pytest.raises(ValueError, match="timeout_seconds"):
        build_llm_config(timeout_seconds=0)
    with pytest.raises(ValueError, match="max_retries"):
        build_llm_config(max_retries=-1)
