"""Premise retrieval via the LeanSearch API (leansearch.net) -- the search_lemmas
tool for the reasoner and engineer (Step 4i).

Natural-language search over Mathlib: given a description, return candidate
declarations (name + signature + a one-line informal description) so an agent
can find the lemma it needs without already knowing its exact name. This is the
field's most-cited augmentation -- "knowing the right lemma exists is often
harder than applying it" -- and directly attacks the dominant failure we saw
(a weak engineer perseverating because it could not find Nat.add_comm).

Contract (confirmed by scripts/probe_leansearch.py against the live service):
  POST https://leansearch.net/search
  body: {"query": ["...?"], "num_results": <int>}   # query is a LIST; count is int
  -> 200, a list (one per query) of lists of {"result": {...}, "distance": float}
     result fields: module_name (list), kind, name (list), signature, type,
                    value, docstring, informal_name, informal_description.
Lower distance = closer match. Results are conceptually related declarations
(instances, structures, lemmas), NOT guaranteed to be the single applicable
lemma -- the agent still reads and chooses.

The tool is best-effort: network failures / non-200 return a readable message,
never raise, so a retrieval hiccup degrades gracefully (and "search failed" is
itself an observable trajectory event) rather than killing the run.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

LEANSEARCH_URL = "https://leansearch.net/search"
_TIMEOUT = 30


@dataclass(frozen=True)
class LemmaHit:
    """One retrieved declaration, flattened from a LeanSearch result."""

    name: str  # dotted full name, e.g. "Nat.add_comm"
    signature: str
    kind: str
    informal: str  # informal_name / description, for the agent to judge relevance
    distance: float

    def render(self) -> str:
        """One-line readable form for the agent."""
        sig = self.signature.strip()
        sig = f" {sig}" if sig and not sig.startswith(":") else sig
        desc = f"  -- {self.informal}" if self.informal else ""
        return f"{self.name}{(' ' + sig) if sig else ''}{desc}"


def _flatten(record: dict) -> LemmaHit | None:
    r = record.get("result") or {}
    name_parts = r.get("name") or []
    name = ".".join(name_parts) if isinstance(name_parts, list) else str(name_parts)
    if not name:
        return None
    informal = r.get("informal_name") or r.get("docstring") or ""
    return LemmaHit(
        name=name,
        signature=(r.get("signature") or r.get("type") or "").strip(),
        kind=r.get("kind") or "",
        informal=informal.strip() if isinstance(informal, str) else "",
        distance=float(record.get("distance", 0.0)),
    )


def _query_leansearch(query: str, num_results: int, url: str) -> list[LemmaHit]:
    """POST a single query; return parsed hits. Raises on transport/HTTP error
    (the public search_lemmas wrapper catches and renders failures)."""
    body = json.dumps({"query": [query], "num_results": num_results}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "traj-eval"},
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    # Response is a list (one per query) of lists of result records.
    if not isinstance(data, list) or not data:
        return []
    first = data[0]
    if not isinstance(first, list):
        return []
    hits = [_flatten(rec) for rec in first if isinstance(rec, dict)]
    return [h for h in hits if h is not None]


def make_search_lemmas(*, num_results: int = 5, url: str = LEANSEARCH_URL):
    """Return the search_lemmas tool function (closes over k and the endpoint).

    Best-effort: any failure returns a readable string rather than raising, so a
    retrieval problem degrades into an observable 'search unavailable' turn
    instead of crashing the run.
    """

    def search_lemmas(query: str) -> str:
        """Search Mathlib for lemmas/definitions matching a natural-language
        description. Returns candidate declarations with their names and
        signatures; pick the one whose statement matches what you need.

        Args:
            query: a natural-language description of the lemma you want
                (e.g. "commutativity of addition on natural numbers").
        """
        q = query.strip()
        if q and q[-1] not in ".?":
            q += "?"  # the API expects queries ending in '.' or '?'
        try:
            hits = _query_leansearch(q, num_results, url)
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as e:
            return f"search_lemmas unavailable ({type(e).__name__}); proceed without retrieval."
        if not hits:
            return "No lemmas found for that query. Try rephrasing the description."
        lines = [h.render() for h in hits]
        return "Top matches (name signature -- description):\n" + "\n".join(lines)

    return search_lemmas
