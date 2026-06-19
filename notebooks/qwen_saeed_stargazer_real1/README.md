# Qwen Saeed Stargazer Notebook

Run from the `traj-eval` checkout on branch `Han`.

Use Python 3.11. The notebooks were verified with a Python environment that has notebook, data, OpenAI client, and agent dependencies installed.

```powershell
python -m pip install -e ".[agents]" notebook pandas openai httpx python-dotenv
```

If you use `uv`, the equivalent setup is:

```powershell
uv sync --all-extras
uv pip install notebook pandas openai httpx python-dotenv
```

## Provider Setup

The notebooks load an OpenAI-compatible Qwen endpoint from the repo-level env files:

```text
configs/qwen.remote.example.env
configs/qwen.remote.local.env
```

`configs/qwen.remote.example.env` is a public template. Copy it to `configs/qwen.remote.local.env`, then fill in your endpoint URL and API key. The local env file must stay untracked.

Required keys:

```text
OPENAI_BASE_URL=https://your-qwen-endpoint.example/v1
OPENAI_API_BASE=https://your-qwen-endpoint.example/v1
OPENAI_API_KEY=...
```

Optional key:

```text
CMBAGENT_EVAL_LOCAL_MODEL=
```

If the model field is blank, the notebooks ask `/models` and use the first model returned by the endpoint. You can also point to another env file with `TRAJ_EVAL_PROVIDER_ENV`.

For larger role prompts, use a longer request timeout before starting Jupyter:

```powershell
$env:QWEN_REQUEST_TIMEOUT="300"
$env:QWEN_MAX_RETRIES="1"
```

## Run Order

1. Optional smoke test: run `qwen_test.ipynb` first to confirm the endpoint, key, and model selection.
2. Run `qwen_saeed_agent_stargazer.ipynb`. It writes generated artifacts under:

   ```text
   notebooks/qwen_saeed_stargazer_real1/outputs/qwen_saeed_agent_stargazer/
   ```

3. Run `qwen_saeed_stargazer_eval.ipynb` after the agent notebook. It reads the agent output and writes evaluation artifacts under:

   ```text
   notebooks/qwen_saeed_stargazer_real1/outputs/qwen_saeed_stargazer_eval/
   ```

For a short mechanics-only smoke run, set this before starting Jupyter:

```powershell
$env:STARGAZER_AGENT_MAX_ITERATIONS="3"
```

For the real run, leave `STARGAZER_AGENT_MAX_ITERATIONS` unset so the notebook can use its default loop budget.

The task JSON and minimal Stargazer evaluator support code are intentionally local to this notebook folder so running the notebooks does not depend on any private source checkout.
