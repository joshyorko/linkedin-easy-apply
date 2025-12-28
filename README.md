# LinkedIn Easy Apply Automation

Automated LinkedIn job scraping, AI-powered enrichment, and Easy Apply form filling. Built as a **Sema4.ai Action Server** with MCP integration for VS Code Copilot Agent.

## Features

- **Job Search & Scraping**: Search LinkedIn with filters (Remote, Hybrid, On-site, Easy Apply)
- **AI Enrichment**: OpenAI validates jobs and generates personalized form answers
- **Dual Database**: SQLite (zero-config) or PostgreSQL (production)
- **MCP Integration**: Use actions as tools in VS Code Copilot Agent
- **Profile System**: Parse resumes to auto-fill applications
- **Docker Ready**: Supervisord-managed container with Cloudflare tunnel support

## Quick Start

### 1. Prerequisites

- Python 3.12+ (or Docker)
- OpenAI API key
- LinkedIn account

### 2. Configuration

Create `.env` in project root:

```bash
# Required
LINKEDIN_USERNAME=your_email@example.com
LINKEDIN_PASSWORD=your_password
OPENAI_API_KEY=sk-proj-your-key

# Database (pick one)
DATABASE_TYPE=sqlite                    # Default, zero-config
DATABASE_TYPE=postgres
DATABASE_URL=postgresql://user:pass@host:5432/linkedin_jobs

# Optional
OPENAI_MODEL=gpt-4o-mini               # Default model
ACTION_SERVER_API_KEY=your-api-key     # Secure the action server
```

### 3. Run with Docker (Recommended)

```bash
# Start full stack: PostgreSQL + Action Server + Retro UI
docker compose up -d

# View logs
docker compose logs -f action-server

# Stop
docker compose down
```

Services:
- **Action Server**: http://localhost:8080
- **Retro UI**: http://localhost:3001
- **PostgreSQL**: localhost:5432

### 4. Run Locally

```bash
# Install dependencies
pip install sema4ai-actions robocorp-browser python-dotenv pandas openai beautifulsoup4 psycopg2-binary

# Start action server
action-server start --port 8080
```

## Three-Phase Workflow

### Phase 1: Search Jobs

```python
from src.linkedin.search_actions.search import search_linkedin_easy_apply

result = search_linkedin_easy_apply(
    query="Python Developer",
    max_jobs=25,
    remote=True,
    headless=True
)
# Returns: run_id, job_ids_found, easy_apply_job_ids
```

### Phase 2: AI Enrichment

```python
from src.linkedin.ai_actions.enrichment import enrich_and_generate_answers

result = enrich_and_generate_answers(
    run_id="search_20250114_143022",  # From Phase 1
    enrich_jobs=True,
    generate_answers=True
)
# OpenAI validates jobs, generates form answers
```

### Phase 3: Apply

```python
from src.linkedin.apply_actions.apply import apply_to_job_by_url

result = apply_to_job_by_url(
    job_url="https://www.linkedin.com/jobs/view/123456",
    allow_submit=False  # Set True to actually submit
)
```

## MCP Integration (VS Code Copilot Agent)

This project exposes actions as MCP tools. Configure in `.vscode/mcp.json`:

```json
{
    "servers": {
        "easy-apply-actions": {
            "url": "http://localhost:8080/mcp",
            "type": "http"
        }
    }
}
```

Then ask Copilot: *"Search for Python Developer jobs on LinkedIn"* and it will invoke the action.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   LinkedIn      │────▶│   OpenAI API    │────▶│    Database     │
│   (Scraping)    │     │  (Enrichment)   │     │ SQLite/Postgres │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                      │                        │
         └──────────────────────┴────────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Action Server       │
                    │   (Sema4.ai + MCP)    │
                    │   Port 8080           │
                    └───────────────────────┘
```

### Module Organization

```
src/linkedin/
├── search_actions/   # Job scraping (search.py, parallel_search.py)
├── ai_actions/       # OpenAI integration (enrichment.py, profile.py)
├── apply_actions/    # Form automation (apply.py, oneoff_apply.py)
├── server_actions/   # Server utilities (database.py, exports.py)
└── utils/            # Shared: db.py, openai_client.py, models.py, prompts.py
```

### Docker Architecture

The container uses **supervisord** to manage the action server process:

```
docker/
└── supervisor/
    ├── supervisord.conf      # Main supervisor config
    └── action-server.conf    # Action server process config

scripts/
└── start-action-server.sh    # Startup script with API key handling
```

**Key features:**
- Auto-restart on crash
- Conditional API key authentication
- Cloudflare tunnel support (optional)

## Database

### Schema Overview

Two main tables:
- `job_postings` - Scraped jobs with AI enrichment (fit_score, good_fit, required_skills)
- `enriched_answers` - AI-generated form answers per job

### Database Abstraction

`src/linkedin/utils/db.py` switches backend at import time:

```python
# Set DATABASE_TYPE=postgres to use PostgreSQL
# Default is SQLite (zero config)
```

Both backends expose identical functions:
- `write_jobs()`, `read_job_by_id()`, `get_jobs_by_run_id()`
- `update_job_enrichment()`, `save_profile_to_db()`, `get_active_profile()`

## Actions Reference

| Action | Description |
|--------|-------------|
| `search_linkedin_easy_apply` | Phase 1: Scrape jobs with filters |
| `enrich_and_generate_answers` | Phase 2: AI enrichment + form answers |
| `apply_to_job_by_url` | Phase 3: Fill and submit Easy Apply |
| `parse_resume_and_save_profile` | Extract profile from PDF resume |
| `check_which_jobs_ready` | List jobs ready to apply (good fit + answers) |
| `get_job_fit_analysis` | Fit statistics for a search run |
| `update_job_fit_status` | Manually override AI fit decisions |
| `set_browser_context` | Persist LinkedIn login session |

## Development

### Testing

```bash
pytest tests/                    # All tests
pytest tests/test_db_sqlite.py -v  # Database tests
```

### Linting

```bash
ruff check src/ tests/
ruff format src/ tests/
```

### Building Docker Image

```bash
docker build -t linkedin-easy-apply .
docker run -p 8080:8080 --env-file .env linkedin-easy-apply
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LINKEDIN_USERNAME` | Yes | - | LinkedIn email |
| `LINKEDIN_PASSWORD` | Yes | - | LinkedIn password |
| `OPENAI_API_KEY` | Yes | - | OpenAI API key |
| `DATABASE_TYPE` | No | `sqlite` | `sqlite` or `postgres` |
| `DATABASE_URL` | If postgres | - | PostgreSQL connection string |
| `SQLITE_PATH` | No | `./linkedin_jobs.sqlite` | SQLite file path |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | OpenAI model |
| `ACTION_SERVER_API_KEY` | No | `None` | Secure the action server |
| `CLOUDFLARED_TOKEN` | No | - | Cloudflare tunnel token |

## Troubleshooting

### "SQLite database locked"
Another process has the file open. Check with `lsof linkedin_jobs.sqlite`.

### LinkedIn CAPTCHA triggered
Reduce parallel workers and add delays between searches. Use `set_browser_context()` to persist login.

### Low AI confidence scores
Job description may be vague. Try `OPENAI_MODEL=gpt-4o` for better quality (higher cost).

### Profile required error
Run `parse_resume_and_save_profile()` with your resume PDF before generating answers.

## Project Structure

```
linkedin-easy-apply/
├── src/linkedin/           # Action server code
├── docker/supervisor/      # Supervisord configs
├── scripts/                # Utility scripts
├── retro-ui/               # Optional web UI (Node.js)
├── sql/                    # Schema reference
├── tests/                  # Pytest tests
├── docker-compose.yml      # Full stack deployment
├── Dockerfile              # Container build
└── package.yaml            # Sema4AI dependencies
```

## License

For personal use. Respect LinkedIn's Terms of Service.

---

Built with [Sema4.ai Actions](https://sema4.ai/) • [Robocorp Browser](https://github.com/robocorp/robocorp) • [OpenAI](https://openai.com/)
