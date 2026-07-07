"""Probe the LeanSearch API (leansearch.net) to learn its real request/response
shape before building the search_lemmas tool. Same discipline as the
lean_interact and AG2 probes: hit the real service a few plausible ways and
print exactly what comes back, rather than guessing the JSON contract.

Run: uv run python scripts/probe_leansearch.py
Needs network egress to leansearch.net. If your environment blocks it, this
will show the connection error -- itself useful (tells us we need the hosted
service reachable, or an env override LEANSEARCHCLIENT_LEANSEARCH_API_URL).

We try, in order, the request patterns LeanSearchClient is documented to use:
  1. GET  https://leansearch.net/api/search?query=...&num_results=...
  2. POST https://leansearch.net/search   with JSON {"query": ..., "num_results": ...}
  3. GET  https://leansearch.net/search?query=...
The query string ends with '?' or '.', as the client requires.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

QUERY = "commutativity of addition for natural numbers?"
N = 4
BASE = "https://leansearch.net"


def _show(label: str, status, body: str) -> None:
    print(f"\n========== {label} ==========")
    print("status:", status)
    snippet = body[:3000]
    print("body[:3000]:")
    print(snippet)
    # If JSON, show its top-level shape so we know how to parse results.
    try:
        data = json.loads(body)
        print("\nparsed JSON type:", type(data).__name__)
        if isinstance(data, list) and data:
            print("outer list length:", len(data))
            first = data[0]
            if isinstance(first, list) and first:
                print("inner list length:", len(first))
                inner = first[0]
                print(
                    "result element keys:",
                    list(inner.keys()) if isinstance(inner, dict) else type(inner).__name__,
                )
            elif isinstance(first, dict):
                print("result element keys:", list(first.keys()))
        elif isinstance(data, dict):
            print("top-level keys:", list(data.keys()))
    except (json.JSONDecodeError, ValueError):
        print("(body is not JSON)")


def _get(url: str, label: str) -> None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "traj-eval-probe"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            _show(label, resp.status, resp.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001 -- probe: any failure is informative
        print(f"\n========== {label} ==========")
        print("ERROR:", type(e).__name__, str(e)[:300])


def _post(url: str, payload: dict, label: str) -> None:
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "traj-eval-probe"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            _show(label, resp.status, resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace") if hasattr(e, "read") else ""
        _show(f"{label} [HTTP {e.code}]", e.code, body)
    except Exception as e:  # noqa: BLE001
        print(f"\n========== {label} ==========")
        print("ERROR:", type(e).__name__, str(e)[:300])


def main() -> None:
    print(f"Probing LeanSearch POST {BASE}/search -- 'query' must be a LIST of strings")
    print("(the 422 detail said loc=body.query type=list_type)\n")

    # The 422 told us: field is 'query', and it must be a list. Now find whether
    # a count field is needed and what the success response looks like.
    payloads = [
        {"query": [QUERY]},
        {"query": [QUERY], "num_results": N},
        {"query": [QUERY], "num_results": [N]},
    ]
    for i, p in enumerate(payloads):
        _post(f"{BASE}/search", p, f"POST /search payload#{i}: {p}")


if __name__ == "__main__":
    main()
