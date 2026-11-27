"""Fixed discovery-only API. Authentication remains the Runtime API-key boundary."""
from __future__ import annotations

from typing import Any

from actions import ActionError, Response, action

from ..utils import search_history
from .discovery import _listing, _read_public_rows


def _run_engine(options: dict[str, Any]) -> Response:
    # These existing engines scrape only. Do not call enrichment/profile/apply actions.
    arguments = {key: value for key, value in options.items() if key not in ("mode", "parallel_workers")}
    if options["mode"] == "parallel":
        from ..search_actions.parallel_search import parallel_search_linkedin_easy_apply
        response = parallel_search_linkedin_easy_apply(**arguments, parallel_workers=options["parallel_workers"])
    else:
        from ..search_actions.search import search_linkedin_easy_apply
        response = search_linkedin_easy_apply(**arguments, skip_ai_enrichment=True)
    if isinstance(response.result, dict):
        return response
    return Response(result={"attempted_count": response.attempted_count, "total_jobs": response.total_jobs})


@action
def start_public_search(
    request_key: str, query: str, mode: str = "standard", max_jobs: int = 25,
    parallel_workers: int = 3, headless: bool = True, remote: bool = False,
    hybrid: bool = False, onsite: bool = False, easy_apply_only: bool = False,
) -> Response:
    """Execute one bounded public-listing search, or reconcile the original request.

    Args:
        request_key: Stable caller idempotency key, reused after a lost response.
        query: Public job query, at most 500 characters.
        mode: Standard or parallel existing peer search engine.
        max_jobs: Maximum jobs attempted, from 1 through 100.
        parallel_workers: Maximum concurrent browsers, from 1 through 3.
        headless: Whether the peer browser runs headlessly.
        remote: Request remote work filtering.
        hybrid: Request hybrid work filtering.
        onsite: Request onsite work filtering.
        easy_apply_only: Restrict to Easy Apply only when explicitly requested.

    Returns:
        Durable bounded-search receipt; running replays never restart browser work.
    """
    options = {"query": query, "mode": mode, "max_jobs": max_jobs, "parallel_workers": parallel_workers,
               "headless": headless, "remote": remote, "hybrid": hybrid, "onsite": onsite,
               "easy_apply_only": easy_apply_only}
    try:
        return Response(result=search_history.execute(request_key, options, _run_engine))
    except ValueError as error:
        raise ActionError("INVALID_SEARCH_REQUEST_OR_CONFLICT") from error
    except Exception as error:
        raise ActionError("SEARCH_EXECUTION_FAILED") from error


@action(is_consequential=False)
def public_search_status(request_key: str) -> Response:
    """Read a durable search receipt using the original request key.

    Args:
        request_key: Original discovery idempotency key.

    Returns:
        Search execution/durability/coverage receipt or SEARCH_NOT_FOUND.
    """
    return Response(result=search_history.lookup(request_key) or {"error_code": "SEARCH_NOT_FOUND"})


@action(is_consequential=False)
def public_search_results(request_key: str) -> Response:
    """Read immutable public observations for a finished bounded search.

    Args:
        request_key: Original discovery idempotency key.

    Returns:
        Receipt and public observations, excluding profiles, AI answers and logs.
    """
    receipt = search_history.lookup(request_key)
    if receipt is None:
        return Response(result={"error_code": "SEARCH_NOT_FOUND"})
    rows = [] if (receipt["execution_state"] == "running" or receipt["persisted_count"] == 0) else _read_public_rows(receipt["run_id"], 101)
    listings = [item for row in rows if (item := _listing(row, receipt["run_id"])) is not None]
    return Response(result={"schema_version": 1, "receipt": receipt, "listings": listings[:100],
                            "rejected_count": len(rows) - len(listings), "truncated": len(rows) > 100})
