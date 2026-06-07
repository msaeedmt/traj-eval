"""LLM configuration for the AG2 agent substrate.

Single place that knows how to talk to a model endpoint. Everything is read
from environment variables so that:

  * the API key never lives in code or the repo (.env is gitignored);
  * the *backbone* axis from the proposal (small vs large LLM, §5) is a config
    change, not a code change;
  * the same code runs against OpenAI proper or a self-hosted OpenAI-compatible
    gateway (e.g. a lab vLLM server) by changing OPENAI_BASE_URL only.

Environment variables:
  OPENAI_API_KEY   (required)  the secret key.
  TRAJ_EVAL_MODEL  (optional)  model id; defaults to "gpt-4o-mini".
  OPENAI_BASE_URL  (optional)  endpoint override; if unset, hits OpenAI proper.
"""

from __future__ import annotations

import os

from autogen import LLMConfig

DEFAULT_MODEL = "gpt-4o-mini"


def build_llm_config(*, temperature: float = 0.2) -> LLMConfig:
    """Build an AG2 LLMConfig from the environment.

    Raises a clear error if the key is missing, so a misconfigured shell fails
    loudly instead of producing a confusing auth error deep inside a chat.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Export it in your shell or put it in a "
            "(gitignored) .env file before running any agent."
        )

    model = os.environ.get("TRAJ_EVAL_MODEL", DEFAULT_MODEL)

    entry: dict[str, object] = {
        "api_type": "openai",
        "model": model,
        "api_key": api_key,
        "temperature": temperature,
    }

    # Only set base_url when overriding; absent => OpenAI's default endpoint.
    base_url = os.environ.get("OPENAI_BASE_URL")
    if base_url:
        entry["base_url"] = base_url

    return LLMConfig(entry)
