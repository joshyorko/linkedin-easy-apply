# LinkedIn Easy Apply Action Server - AI Agent Instructions

## Project Overview

This is a **Sema4.ai Action Server** that automates LinkedIn Easy Apply job applications using:
- **Browser automation** (Playwright via `robocorp-browser`)
- **AI enrichment** (OpenAI Structured Outputs for job validation & form answering)
- **Dual database support** (SQLite for local dev, PostgreSQL for production)
- **MCP-compatible** server exposing actions as tools

**Key workflow**: Search LinkedIn → Scrape jobs → AI enrichment → Generate form answers → Auto-apply

## Architecture Patterns

### 1. Action-Based Architecture
All public endpoints are decorated with `@action` from `sema4ai.actions`:
```python
from sema4ai.actions import action, Response

@action
def search_linkedin_easy_apply(query: str, max_jobs: int = 25) -> Response:
    """Phase 1: Scrape jobs and store in database."""
```

**Module Organization**:
- `src/linkedin/search_actions/` - Job scraping (search.py, parallel_search.py)
- `src/linkedin/ai_actions/` - OpenAI integration (enrichment.py, profile.py)
- `src/linkedin/apply_actions/` - Form automation (apply.py, oneoff_apply.py)
- `src/linkedin/server_actions/` - Server utilities (monitoring.py, database.py, exports.py, browser.py)
- `src/linkedin/utils/` - Shared utilities (db layer, OpenAI client, models, prompts)

### 2. Database Abstraction Layer
**Critical**: `src/linkedin/utils/db.py` is a facade that dynamically imports backend:
```python
# Environment variable determines backend
DATABASE_TYPE=sqlite  # or "postgres"

# db.py switches at import time:
if _database_type == "postgres":
    from .db_postgres import *
else:
    from .db_sqlite import *
```

**Key functions** (identical signatures across backends):
- `write_jobs(jobs: List[dict])` - Upsert job records
- `read_job_by_id(job_id: str)` - Fetch single job
- `get_jobs_by_run_id(run_id: str)` - Jobs from search session
- `update_job_enrichment(job_id, enrichment_data)` - Store AI analysis
- `update_answers_json(job_id, answers)` - Store form answers
- `save_profile_to_db(profile_dict)` - User profile versioning
- `get_active_profile()` - Current profile for form filling

**Schema**: See `sql/schema.sql` for complete DDL (SQLite/PostgreSQL, adapted per backend)

### 3. OpenAI Integration (Structured Outputs)
**Location**: `src/linkedin/utils/openai_client.py`

**Pattern**: Uses Pydantic models with OpenAI SDK's structured output beta:
```python
from openai import OpenAI
from pydantic import BaseModel

class JobEnrichment(BaseModel):
    title: str
    required_skills: List[str]
    good_fit: bool
    fit_score: float  # 0.0-1.0
    fit_reasoning: Optional[str]

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
response = client.beta.chat.completions.parse(
    model="gpt-5-nano",  # Default, configurable via OPENAI_MODEL
    messages=[...],
    response_format=JobEnrichment
)
```

**Two main functions**:
1. `enrich_job(job_data, profile)` → Job validation + fit analysis
2. `generate_answers(form_fields, job_data, profile)` → Easy Apply form answers

**Prompts**: Defined in `src/linkedin/utils/prompts.py` with reasoning effort tuning

### 4. Three-Phase Workflow

**Phase 1 - Search** (`search_linkedin_easy_apply`):
- Scrapes LinkedIn with filters (remote/hybrid/onsite)
- Stores raw job data with `run_id` (e.g., `search_20250114_143022`)
- Returns job IDs for next phase
- **No AI enrichment** (moved to Phase 2)

**Phase 2 - Enrichment** (`enrich_and_generate_answers`):
- Loads jobs by `run_id` or explicit `job_ids`
- Calls `enrich_job()` → Updates `good_fit`, `fit_score`, `ai_confidence_score`
- Calls `generate_answers()` → Saves to `enriched_answers` table
- Skips if `force_answer_regeneration=False` and answers exist

**Phase 3 - Apply** (`apply_to_job_by_url` or `batch_apply_by_run_id`):
- Loads answers from `enriched_answers` table
- Uses `src/linkedin/utils/apply_core.py` for form detection/filling
- **Skips pre-filled fields** (see `CHANGELOG_PREFILLED_FIELDS.md`)
- Logs `fields_filled` vs `skipped_prefilled` metrics

### 5. Profile System
**New design** (see `docs/PROFILE_SCHEMA_REDESIGN.md`):
- `parse_resume_and_save_profile()` - PDF → structured profile via OpenAI
- `enrich_user_profile()` - Add fields missing from resume (work auth, address, salary)
- Profiles stored in `user_profiles` table with versioning (`profile_id`, `is_active`)
- **Only one active profile at a time** (enforced by `set_active_profile()`)

**Critical fields** for Easy Apply:
```python
work_authorization  # "US Citizen", "H1B", "Requires Sponsorship"
requires_visa_sponsorship  # bool
address_city, address_state, address_zip
salary_min, salary_max
earliest_start_date  # "Immediately", "2 weeks", "1 month"
years_of_experience
```

## Development Workflow

### Running Actions Locally
```bash
# Start action server (port 8080)
action-server start --port 8080

# Or use Makefile
make run-local

# Test individual action
python -c "
from src.linkedin.search_actions.search import search_linkedin_easy_apply
result = search_linkedin_easy_apply('Python Developer', max_jobs=10)
print(result)
"
```

### Testing
**Location**: `tests/` directory
- `test_db_sqlite.py` - Database backend tests
- Pattern: pytest with `clean_db` fixture (creates temp DB per test)
```bash
# Run tests
pytest tests/

# Specific test file
pytest tests/test_db_sqlite.py -v
```

### Database Inspection
**SQLite**:
```bash
sqlite3 linkedin_jobs.sqlite "SELECT job_id, title, good_fit FROM job_postings WHERE run_id = 'search_20250114_143022';"
```

**PostgreSQL**:
```bash
psql $DATABASE_URL -c "SELECT job_id, title, good_fit FROM job_postings WHERE good_fit = true;"
```

**Via Action**: Use `query_database(sql_query)` action (SELECT only for safety)

### Build & Deploy
**Makefile commands**:
```bash
make build              # Docker image (cached)
make build-fast         # No cache clear
make build-multiarch    # amd64 + arm64
make push              # Push to registry
make run-local         # Local development
```

**Docker Compose**:
```bash
docker-compose up -d           # Action server on 8080
# nginx service commented out (see docs/REFACTOR-SUMMARY.md)
```

**Important**: Docker refactoring removed embedded nginx. See `docs/README-DOCKER.md` for migration.

## Critical Conventions

### 1. Environment Variables
**Required**:
```bash
LINKEDIN_USERNAME=your_email@example.com
LINKEDIN_PASSWORD=your_password
OPENAI_API_KEY=sk-proj-...
```

**Database**:
```bash
DATABASE_TYPE=sqlite     # or "postgres"
SQLITE_PATH=./linkedin_jobs.sqlite  # Optional custom path
DATABASE_URL=postgresql://...       # For postgres
```

**OpenAI**:
```bash
OPENAI_MODEL=gpt-4o-mini  # Default, can use gpt-4o for better quality
```

### 2. Logging with robocorp-log
**Pattern**: Use `src/linkedin/utils/robolog.py` wrapper:
```python
from ..utils.robolog import setup_logging, log, capture_screenshot

# Initialize per action
setup_logging(output_dir=f"./output/{run_id}", enable_html_report=True)

# Logging
log.info("Starting job scrape")
log.error("Failed to find search box")

# Screenshots
capture_screenshot(page, "after_login")
```

**Output**: `output/{run_id}/log.html` with screenshots embedded

### 3. Browser Context Persistence
**Location**: `browser_context/` directory
- Contains LinkedIn session cookies/local storage
- Reused across action calls to avoid repeated logins
- **Do NOT commit** (in .gitignore)

### 4. Run IDs
**Format**: `{action}_{YYYYMMDD_HHMMSS}` (e.g., `search_20250114_143022`)
- Used for:
  - Grouping jobs from same search (`run_id` column)
  - Output directories (`output/{run_id}/`)
  - Database queries (`get_jobs_by_run_id()`)

### 5. Boolean Handling (SQLite)
**Critical**: SQLite has no native boolean type. `db_sqlite.py` converts:
```python
# Writing: bool → int
job['easy_apply'] = 1 if job.get('easy_apply') else 0

# Reading: int → bool
job['easy_apply'] = bool(job.get('easy_apply'))
```

**Always use `bool()` when reading** from SQLite to avoid truthy int issues.

## Common Tasks

### Adding a New Action
1. Create function in appropriate module (`*_actions/`)
2. Decorate with `@action` or `@action(is_consequential=True)`
3. Return `Response` object (not dict)
4. Document with comprehensive docstring (appears in MCP)

### Modifying Database Schema
1. Update `sql/schema.sql` (reference)
2. Update `db_sqlite.py` and `db_postgres.py` (actual schemas in code)
3. Add migration logic or manual SQL for existing databases
4. Update tests in `tests/test_db_sqlite.py`

### Changing OpenAI Prompts
1. Edit `src/linkedin/utils/prompts.py`
2. Test with `reenrich_jobs(job_ids=[...], force_regenerate=True)`
3. Compare old vs new with `query_database("SELECT job_id, fit_score, fit_reasoning FROM job_postings WHERE job_id IN (...)")`

### Debugging Form Filling
1. Set `headless=False` to watch browser
2. Check `output/{run_id}/screenshots/` for visual timeline
3. Look for `[Fill] ⏭️ Field 'X' already has value: 'Y' - SKIPPING` logs
4. Inspect `form_elements` JSON in database: `SELECT form_elements FROM job_postings WHERE job_id = '...'`

## Known Gotchas

1. **LinkedIn rate limits**: Parallel search can trigger CAPTCHA. Use `parallel_workers=3` max.
2. **Headless mode differences**: Search box selectors differ. See fallback logic in `search.py:85-100`.
3. **OpenAI token costs**: `gpt-4o-mini` is ~15x cheaper than `gpt-4o`. Default is mini.
4. **Profile required**: Form answering needs active profile. Call `parse_resume_and_save_profile()` first.
5. **Pre-filled fields**: Bot now skips fields with existing values. Don't expect 100% fill rate.
6. **Database switch**: Change `DATABASE_TYPE` requires restart (import-time decision).

## Key Documentation

- `README.md` - Quick start, feature overview
- `docs/DATABASE_SETUP.md` - PostgreSQL configuration
- `docs/QUICK_START_PROFILE_ENRICHMENT.md` - Profile system usage
- `docs/REFACTOR-SUMMARY.md` - Docker architecture changes
- `docs/CUSTOM_WORKITEM_ADAPTER_GUIDE.md` - Producer-consumer pattern (future scaling)
- `sql/schema.sql` - Database schema reference
- `Makefile` - All build/deploy commands with examples

## Recent Changes (Check CHANGELOG.md)


- Profile enrichment system with work authorization fields
- Pre-filled field skipping in form automation
- Docker refactoring: removed embedded nginx, direct port 8080 exposure
