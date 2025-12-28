# LinkedIn Easy Apply Action Server - AI Agent Instructions

## Project Overview

**Sema4.ai Action Server** automating LinkedIn Easy Apply job applications:
- **Browser automation**: Playwright via `robocorp-browser`
- **AI enrichment**: OpenAI Structured Outputs for job validation & form answering  
- **Dual database**: SQLite (local dev) / PostgreSQL (production)
- **MCP-compatible**: Actions exposed as tools for VS Code Copilot Agent (see `.vscode/mcp.json`)

**Workflow**: Search LinkedIn → Scrape jobs → AI enrichment → Generate form answers → Auto-apply

## Architecture

### Module Organization
```
src/linkedin/
├── search_actions/   # Job scraping (search.py, parallel_search.py)
├── ai_actions/       # OpenAI integration (enrichment.py, profile.py)
├── apply_actions/    # Form automation (apply.py, oneoff_apply.py)
├── server_actions/   # Server utilities (monitoring.py, database.py, exports.py)
└── utils/            # Shared: db layer, OpenAI client, models, prompts
```

### Action Pattern
All endpoints use `@action` decorator, return `Response` objects:
```python
from sema4ai.actions import action, Response

@action
def my_action(param: str) -> Response:
    """Docstring appears in MCP tool description."""
    return Response(result={"key": "value"})
```

### Database Abstraction (`src/linkedin/utils/db.py`)
Facade that switches backend at import-time via `DATABASE_TYPE` env var:
```python
# db.py dynamically imports based on environment
if _database_type == "postgres":
    from .db_postgres import *
else:
    from .db_sqlite import *
```

**Key functions** (identical signatures across backends):
- `write_jobs(jobs)`, `read_job_by_id(job_id)`, `get_jobs_by_run_id(run_id)`
- `update_job_enrichment(job_id, data)`, `update_answers_json(job_id, answers)`
- `save_profile_to_db(profile)`, `get_active_profile()`

**SQLite boolean handling**: SQLite has no native boolean. Always use `bool()` when reading:
```python
job['easy_apply'] = bool(job.get('easy_apply'))  # int → bool
```

### OpenAI Integration (`src/linkedin/utils/openai_client.py`)
Uses Pydantic models with OpenAI's structured output beta:
```python
class JobEnrichment(BaseModel):
    title: str
    good_fit: bool
    fit_score: float  # 0.0-1.0

response = client.beta.chat.completions.parse(
    model="gpt-4o-mini",  # Default, configurable via OPENAI_MODEL
    response_format=JobEnrichment
)
```

**Two main functions**: `enrich_job(job_data, profile)` and `generate_answers(questions, profile, job)`

### Three-Phase Workflow

1. **Search** (`search_linkedin_easy_apply`) - Scrapes LinkedIn, stores raw jobs with `run_id`
2. **Enrichment** (`enrich_and_generate_answers`) - AI validates jobs, generates form answers
3. **Apply** (`apply_to_job_by_url`) - Fills forms using stored answers

## Development

### Running Locally
```bash
# Start action server (port 8080)
action-server start --port 8080

# Or via Docker Compose (includes PostgreSQL + retro-ui)
docker compose up -d
```

### Testing
```bash
pytest tests/                    # Run all tests
pytest tests/test_db_sqlite.py -v  # Specific test file
ruff check src/ tests/           # Lint
ruff format src/ tests/          # Format
```

### Docker Commands
```bash
docker compose up -d             # Start full stack (postgres, action-server, retro-ui)
docker compose logs -f action-server  # View logs
docker compose down              # Stop all services
```

## Environment Variables

**Required**:
```bash
LINKEDIN_USERNAME=your_email@example.com
LINKEDIN_PASSWORD=your_password
OPENAI_API_KEY=sk-proj-...
```

**Database** (pick one):
```bash
DATABASE_TYPE=sqlite              # Default, zero-config
SQLITE_PATH=./linkedin_jobs.sqlite

DATABASE_TYPE=postgres
DATABASE_URL=postgresql://user:pass@host:5432/linkedin_jobs
```

**OpenAI**:
```bash
OPENAI_MODEL=gpt-4o-mini          # Default. Use gpt-4o for better quality
```

## Key Patterns

### Run IDs
Format: `{action}_{YYYYMMDD_HHMMSS}` (e.g., `search_20250114_143022`)
- Groups jobs from same search session
- Used for output directories: `output/{run_id}/`
- Query with: `get_jobs_by_run_id(run_id)`

### Logging (`src/linkedin/utils/robolog.py`)
```python
from ..utils.robolog import setup_logging, log, capture_screenshot

setup_logging(output_dir=f"./output/{run_id}", enable_html_report=True)
log.info("Starting job scrape")
capture_screenshot(page, "after_login")
```
Output: `output/{run_id}/log.html` with embedded screenshots

### Browser Context Persistence
Directory: `browser_context/` - Contains LinkedIn session cookies/local storage.
Reused across action calls to avoid repeated logins. **Do NOT commit** (in .gitignore).

## Common Tasks

### Adding a New Action
1. Create function in appropriate `*_actions/` module
2. Decorate with `@action` (or `@action(is_consequential=True)` for mutations)
3. Return `Response` object with result dict
4. Document with comprehensive docstring (appears in MCP)

### Modifying Database Schema
1. Update `sql/schema.sql` (reference)
2. Update both `db_sqlite.py` and `db_postgres.py` (actual schemas in code)
3. Add migration SQL for existing databases
4. Update tests in `tests/test_db_sqlite.py`

### Debugging Form Filling
1. Set `headless=False` to watch browser
2. Check `output/{run_id}/screenshots/` for visual timeline
3. Inspect form elements: `SELECT form_elements FROM job_postings WHERE job_id = '...'`

## Gotchas

1. **LinkedIn rate limits**: Parallel search triggers CAPTCHA. Use `parallel_workers=3` max
2. **Headless mode differences**: Search box selectors differ. See fallback logic in `search.py:85-100`
3. **Profile required**: Form answering needs active profile. Call `parse_resume_and_save_profile()` first
4. **Database switch**: Changing `DATABASE_TYPE` requires restart (import-time decision)
5. **OpenAI costs**: `gpt-4o-mini` is ~15x cheaper than `gpt-4o`. Default is mini

## Key Files

| File | Purpose |
|------|---------|
| `src/linkedin/utils/db.py` | Database abstraction facade |
| `src/linkedin/utils/openai_client.py` | OpenAI structured outputs |
| `src/linkedin/utils/prompts.py` | AI prompt definitions |
| `src/linkedin/search_actions/search.py` | Main search action |
| `src/linkedin/ai_actions/enrichment.py` | Phase 2 enrichment |
| `sql/schema.sql` | Database schema reference |
| `docker-compose.yml` | Full stack deployment |
