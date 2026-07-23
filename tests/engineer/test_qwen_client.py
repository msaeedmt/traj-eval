from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from traj_eval.agents.engineer import qwen_client


def _args(*, provider_env=None, qwen_model="test-model"):
    return SimpleNamespace(
        provider_env=provider_env,
        qwen_model=qwen_model,
        qwen_timeout=30,
        qwen_max_retries=0,
    )


def test_explicit_provider_file_takes_precedence():
    environment = {
        "TRAJ_EVAL_PROVIDER_ENV": "inherited.env",
        "OPENAI_BASE_URL": "https://explicit.invalid/v1",
        "OPENAI_API_KEY": "test-key",
    }
    with (
        patch.dict(os.environ, environment, clear=True),
        patch.object(qwen_client.Path, "is_file", return_value=True),
        patch.object(qwen_client, "load_env_file", return_value={}) as load,
    ):
        config = qwen_client.resolve_qwen_config(
            qwen_client.Path("repo"),
            _args(provider_env="explicit.env"),
        )

    assert config["env_path"] == "explicit.env"
    assert config["base_url"] == "https://explicit.invalid/v1"
    load.assert_called_once_with(qwen_client.Path("explicit.env"))


def test_provider_file_can_come_from_environment():
    environment = {
        "TRAJ_EVAL_PROVIDER_ENV": "provider.env",
        "OPENAI_BASE_URL": "https://provider.invalid/v1",
        "OPENAI_API_KEY": "test-key",
    }
    with (
        patch.dict(os.environ, environment, clear=True),
        patch.object(qwen_client.Path, "is_file", return_value=True),
        patch.object(qwen_client, "load_env_file", return_value={}) as load,
    ):
        config = qwen_client.resolve_qwen_config(qwen_client.Path("repo"), _args())

    assert config["env_path"] == "provider.env"
    load.assert_called_once_with(qwen_client.Path("provider.env"))


def test_environment_only_configuration_needs_no_provider_file():
    environment = {
        "OPENAI_BASE_URL": "https://environment.invalid/v1",
        "OPENAI_API_KEY": "test-key",
        "TRAJ_EVAL_MODEL": "environment-model",
    }
    with (
        patch.dict(os.environ, environment, clear=True),
        patch.object(qwen_client, "load_env_file") as load,
    ):
        config = qwen_client.resolve_qwen_config(
            qwen_client.Path("repo"),
            _args(qwen_model=None),
        )

    assert config["env_path"] is None
    assert config["loaded_redacted"] == {}
    assert config["base_url"] == "https://environment.invalid/v1"
    assert config["api_key_set"] is True
    assert config["model"] == "environment-model"
    load.assert_not_called()


def test_repo_local_provider_file_is_not_selected_silently():
    environment = {
        "OPENAI_BASE_URL": "https://environment.invalid/v1",
        "OPENAI_API_KEY": "test-key",
    }
    with (
        patch.dict(os.environ, environment, clear=True),
        patch.object(qwen_client, "load_env_file") as load,
    ):
        config = qwen_client.resolve_qwen_config(
            qwen_client.Path("repo-with-legacy-config"),
            _args(),
        )

    assert config["env_path"] is None
    load.assert_not_called()


def test_missing_environment_values_are_reported_by_later_client_validation():
    with (
        patch.dict(os.environ, {}, clear=True),
        patch.object(qwen_client, "load_env_file") as load,
    ):
        config = qwen_client.resolve_qwen_config(
            qwen_client.Path("repo"),
            _args(qwen_model=None),
        )

    assert config["env_path"] is None
    assert config["base_url"] == ""
    assert config["api_key_set"] is False
    assert config["model"] == ""
    load.assert_not_called()


def test_missing_selected_provider_file_fails_clearly():
    with (
        patch.dict(os.environ, {}, clear=True),
        patch.object(qwen_client.Path, "is_file", return_value=False),
        pytest.raises(FileNotFoundError, match="provider environment file not found"),
    ):
        qwen_client.resolve_qwen_config(
            qwen_client.Path("repo"),
            _args(provider_env="missing.env"),
        )
