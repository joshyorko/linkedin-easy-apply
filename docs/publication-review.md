# Publication review required

Do not push this candidate, upload its patch, open a public PR, or send a cleanup
handoff until the source publication restriction is resolved. Do not delete the
JHT bundled integration.

GitHub repository metadata checked on 2026-11-27 reports JHT as private.
Standalone public main is `9d696ab45e0aa81e051a83ea48db483313cc62c1`, matching
this candidate's base. The earlier turn used a local private JHT checkout as a
source reference before establishing public provenance. This record corrects
that omission; a secret scan alone cannot authorize publishing private source.

The candidate includes copied or adapted private-source material in:

- `src/linkedin/server_actions/discovery.py`
- `src/linkedin/server_actions/search_discovery.py`
- `src/linkedin/utils/recorded_listings.py`
- `src/linkedin/utils/search_history.py`
- `src/linkedin/utils/db_sqlite.py` (thread-local connection initialization)
- `src/linkedin/search_actions/filters.py`
- `tests/test_discovery_export.py`
- `tests/test_search_history.py`
- `tests/test_search_filter_contract.py`

These files need an already-public source/provenance receipt or explicit owner
authorization to publish the reviewed candidate despite the previous restriction.
The remaining changes must be reviewed together with them as one outward diff.
No private source or patch has been sent to GitHub by this lane.

The local compatibility receipt is in `jht-compatibility.md`. The full suite
passes with disposable synthetic PostgreSQL, including actual process restart
and duplicate delivery. This does not qualify independent Rails Solid Queue
delivery, deployed Runtime HTTP, live accounts, or browser behavior.

After publication approval, create the normal public PR, qualify that exact
commit in CI, and run the independent JHT recorded/synthetic Solid Queue
acceptance against the standalone endpoint. Only then send the exact qualified
commit and scope through the approved cleanup handoff. Bundle deletion remains
a separate owner action. This work changes no sign-in, T3 configuration, Pi,
account, submission guard, or deployment state.
