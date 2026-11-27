# Standalone JHT compatibility

Package `linkedin-easy-apply-server` 0.0.2 exposes the fixed JHT HTTP actions:

| Action path suffix | Inputs |
| --- | --- |
| `export-recorded-public-listings/run` | `run_id`, optional `limit` (1–100) |
| `start-public-search/run` | `request_key`, `query`, optional bounded search options |
| `public-search-status/run` | `request_key` |
| `public-search-results/run` | `request_key` |

Each path is under `/api/actions/linkedin-easy-apply-server/`. Responses use
the maintained Actions `{result, error}` envelope. Runtime authentication remains
the boundary; this change does not configure a listener, account, or T3 client.

Public search accepts standard or parallel mode, at most 100 jobs and 3 workers.
It defaults to all public listings and always disables Easy Apply form capture.
Existing standalone search actions retain their Easy Apply/form-capture defaults
and typed response fields. All existing live-submission rejection guards remain.

`search_runs` stores durable request fingerprints and receipts. Replaying the same
request returns its original receipt, including running or failed receipts, without
launching another search. Changed options with the same key are rejected.
`search_observations` stores append-only, allowlisted public snapshots in the job
write transaction on SQLite and PostgreSQL. Rediscovery cannot overwrite an old
run's observations. No historical backfill is attempted.

Execution completion and bounded persistence do not prove exhaustive LinkedIn
coverage. Legacy recorded exports remain `unknown` or `partial`; missing storage
and invalid requests do not become successful empty searches. Public results omit
profiles, answers, enrichment, browser state, and private diagnostics.

The JHT owner must point its peer endpoint at this standalone package and update
its operator-pinned Runtime provenance to the deployed version. The former embedded
peer used Runtime 1.0.4; this standalone repository maintains its own Runtime pins.
No JHT files or embedded integration were removed by this change.

Offline verification covers receipt replay/conflicts/concurrency, immutable
observations, rollback, allowlisted exports, broad/filtered search behavior,
the real serial engine with a synthetic browser, and submission rejection.
PostgreSQL cases require `JHT_PEER_TEST_DATABASE_URL` and otherwise skip.
Live browser, deployed Runtime HTTP, and JHT endpoint acceptance remain
separate gates. No live login or application was performed.

Local verification on 2026-11-27: **85 passed**, no skips or deselections, using
Python 3.12.11, Actions Core 1.1.0, pytest 8.3.5, psycopg2-binary 2.9.11 and
Pydantic 2.14.4. PostgreSQL 15.19 ran in an owned disposable amd64 container from
`postgres@sha256:f7d23353e1b15400d22ebe31189f4d314b87a4c129cc400c8c2d8d4ca127bf81`,
with RAM-only data and a loopback-only random host port. All test schemas and the
container were removed. No image was pulled or removed.

The full suite now exercises supported database helpers instead of obsolete
SQLAlchemy interfaces. Pending-enrichment assertions account for the existing
enrichment timestamp rule; production enrichment behavior was not changed.
Fresh-process acceptance exercises all four actions with duplicate delivery,
populated and bounded-empty runs on both SQLite and PostgreSQL. A discovered
empty-run export defect was fixed: a durable empty observation set no longer
falls through to a missing legacy job table. Coverage remains `bounded_unknown`.
The maintained Actions CLI also collected and validated all four action schemas.
Offline qualification passed 36 module imports and five submission rejections.
The full suite is included in the existing qualification CI;
CI execution is not claimed by these local results.

The owner authorized publication; see `publication-review.md`. This candidate
is **not approved for JHT cleanup**. Local test success is not
an independent Rails Solid Queue or deployed HTTP acceptance receipt.
