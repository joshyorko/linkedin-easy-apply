# LinkedIn Easy Apply Automation

Automated LinkedIn job scraping, AI-powered data enrichment, and Easy Apply form filling using OpenAI. Supports both SQLite (embedded) and PostgreSQL (production) databases.

## Model Context Protocol (MCP) & VS Code Copilot Agent Integration

This project is also designed to work seamlessly with AI agents in VS Code, such as GitHub Copilot Agent, using the Model Context Protocol (MCP). MCP is an open standard that allows AI models and agents to interact with external tools and services through a unified interface. MCP servers expose tools (actions) that can be invoked by AI agents, enabling seamless integration with APIs, databases, automation scripts, and more.

### Why is `.vscode/mcp.json` in this project?
The `.vscode/mcp.json` file configures MCP servers for your workspace. This enables VS Code (with Copilot Agent mode) to discover and use the Sema4.ai Action Server as a set of tools directly from chat or agent workflows. Each server entry in `mcp.json` points to an MCP-compatible API endpoint (like your local Sema4.ai Action Server).

#### Example (`.vscode/mcp.json`):
```json
{
    "servers": {
        "easy-apply-actions": {
            "url": "http://localhost:8080/mcp",
            "type": "http"
        }
    },
    "inputs": []
}
```

### How does MCP work in VS Code?
- **Discovery:** VS Code reads `.vscode/mcp.json` and lists available MCP servers/tools in the Copilot Agent interface.
- **Invocation:** When you ask Copilot to perform a task, it can invoke these tools (actions) via MCP, sending structured requests and receiving responses.
- **Extensibility:** You can add more MCP servers or tools by editing `mcp.json`—no code changes needed.

### Security & Best Practices
- **Trust:** Only add MCP servers from trusted sources. MCP servers can run arbitrary code, so review configurations before enabling.
- **Secrets:** Avoid hardcoding API keys or credentials in `mcp.json`. Use environment variables or input prompts.
- **Team Sharing:** Committing `.vscode/mcp.json` lets your whole team use the same MCP tool setup in VS Code.

### References
- [Model Context Protocol Documentation](https://modelcontextprotocol.io/introduction)
- [VS Code MCP Servers Guide](https://code.visualstudio.com/docs/copilot/customization/mcp-servers)
- [Sema4.ai Action Server](https://github.com/Sema4AI/actions)


Automated LinkedIn job scraping, AI-powered data enrichment, and Easy Apply form filling using OpenAI. Supports both SQLite (embedded) and PostgreSQL (production) databases.

## Features


- **Job Search & Scraping**: Search LinkedIn with filters (Remote, Hybrid, On-site, Easy Apply)
- **AI Enrichment**: OpenAI automatically validates and enriches job data before storage
- **Flexible Database**: SQLite (embedded, zero-config) or PostgreSQL (production-grade)
- **Form Automation**: AI-generated answers for Easy Apply forms
- **Smart Filtering**: Query jobs by company, location, Easy Apply status, and more
- **Data Export**: CSV exports for analysis
- **Production Ready**: Connection pooling, migrations, cloud deployment support

## Quick Start

### 1. Prerequisites

- Python 3.12+
- OpenAI API key (get one at https://platform.openai.com/api-keys)
- LinkedIn account credentials

### 2. Installation

```bash
# Clone or download this repository
cd linkedin-easy-apply

# Install dependencies (using uv, recommended by Sema4AI)
uv pip install -r requirements.txt

# Or using pip
pip install sema4ai-actions robocorp-browser python-dotenv pandas openai beautifulsoup4 psycopg2-binary
```

### 3. Configuration

Create a `.env` file in the project root:

```bash
# Required: LinkedIn credentials
LINKEDIN_USERNAME=your_email@example.com
LINKEDIN_PASSWORD=your_password

# Required: OpenAI API key
OPENAI_API_KEY=sk-proj-your-openai-key-here

# Optional: Customize OpenAI model (default: gpt-4o-mini)
OPENAI_MODEL=gpt-4o-mini

# Optional: Database configuration
DATABASE_TYPE=sqlite  # or "postgres" for production

# SQLite (default) - no setup required
SQLITE_PATH=/path/to/database.sqlite  # Optional custom location

# PostgreSQL (production) - requires setup
# DATABASE_URL=postgresql://user:password@host:5432/linkedin_jobs
```

For PostgreSQL setup and cloud deployment, see [docs/DATABASE_SETUP.md](docs/DATABASE_SETUP.md)

### 4. Run Your First Search

```python
from src.linkedin.linkedin_actions import search_linkedin_easy_apply

# Search for jobs
result = search_linkedin_easy_apply(
    query="Python Developer",
    headless=False,  # Set True to run without browser UI
    max_jobs=25,
    remote=True
)

print(f"Found {result.result['total_jobs']} jobs")
print(f"Easy Apply: {result.result['easy_apply_count']}")
```

This will:
1. Open LinkedIn and search for jobs
2. Scrape job details
3. **Use OpenAI to enrich and validate each job**
4. Store in database (SQLite or PostgreSQL)
5. Export to CSV

## Database Options

### SQLite (Default) - Zero Configuration

Perfect for local development and single-user scenarios:
- ✅ Built into Python, no setup required
- ✅ Single file database (`linkedin_jobs.sqlite`)
- ✅ Fast for local use
- ⚠️ Limited concurrency

```bash
# Default - just run it!
DATABASE_TYPE=sqlite
```

### PostgreSQL - Production Grade

Recommended for production deployments:
- ✅ Excellent concurrency (multiple writers)
- ✅ Cloud-ready (AWS RDS, Google Cloud SQL, Heroku)
- ✅ Connection pooling built-in
- ✅ Better scalability

```bash
DATABASE_TYPE=postgres
DATABASE_URL=postgresql://user:password@host:5432/linkedin_jobs
```

Full setup guide: [docs/DATABASE_SETUP.md](docs/DATABASE_SETUP.md)

## Architecture

### Simple & Modern Stack

```
┌─────────────────┐
│   LinkedIn      │
│   (Web Scrape)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   OpenAI API    │ ◄── Enriches & validates data
│ (Structured Out)│     Generates form answers
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│         Database Layer              │
│  ┌─────────────┐  ┌──────────────┐ │
│  │   SQLite    │  │  PostgreSQL  │ │
│  │  (Default)  │  │ (Production) │ │
│  └─────────────┘  └──────────────┘ │
└─────────────────────────────────────┘
```


### Key Components

* `src/linkedin/search_actions/`: Job scraping actions
* `src/linkedin/ai_actions/`: OpenAI enrichment and profile actions
* `src/linkedin/apply_actions/`: Easy Apply automation
* `src/linkedin/server_actions/`: Server utilities and exports
* `src/linkedin/utils/db.py`: Database abstraction layer (SQLite/PostgreSQL)
* `src/linkedin/utils/db_sqlite.py`: SQLite backend implementation
* `src/linkedin/utils/db_postgres.py`: PostgreSQL backend implementation
* `src/linkedin/utils/openai_client.py`: OpenAI integration for enrichment and form answers
* `src/linkedin/utils/models.py`: Pydantic models for job data
* `linkedin_jobs.sqlite` or PostgreSQL: Your job database (created automatically)

## Usage

### Search Jobs

```python
from src.linkedin.linkedin_actions import search_linkedin_easy_apply

# Basic search
search_linkedin_easy_apply(
    query="DevOps Engineer",
    max_jobs=50
)

# Advanced: Remote jobs only
search_linkedin_easy_apply(
    query="Machine Learning",
    remote=True,
    max_jobs=100,
    headless=True
)

# Hybrid + On-site
search_linkedin_easy_apply(
    query="Product Manager",
    hybrid=True,
    onsite=True,
    max_jobs=25
)
```

### Query Your Jobs

```python
from src.linkedin.db import query_jobs, read_job_by_id

# Get all Easy Apply jobs
easy_jobs = query_jobs(easy_apply_only=True, limit=100)

# Search by company
google_jobs = query_jobs(company="Google", limit=50)

# Get a specific job
job = read_job_by_id("3846477685")
print(job['title'], job['company'], job['salary_range'])
```

### Direct SQL Queries (SQLite/PostgreSQL)

#### SQLite Example
```python
import sqlite3
conn = sqlite3.connect('linkedin_jobs.sqlite')
cursor = conn.cursor()
cursor.execute("""
        SELECT title, company, salary_range, job_url
        FROM job_postings
        WHERE location_type = 'Remote'
            AND salary_range IS NOT NULL
            AND easy_apply = 1
        ORDER BY ai_confidence_score DESC
        LIMIT 20
""")
for row in cursor.fetchall():
        print(row)
conn.close()
```

#### PostgreSQL Example
```python
import psycopg2
conn = psycopg2.connect("postgresql://user:password@host:5432/linkedin_jobs")
cursor = conn.cursor()
cursor.execute("""
        SELECT title, company, salary_range, job_url
        FROM job_postings
        WHERE location_type = 'Remote'
            AND salary_range IS NOT NULL
            AND easy_apply = true
        ORDER BY ai_confidence_score DESC
        LIMIT 20
""")
for row in cursor.fetchall():
        print(row)
conn.close()
```

### Phase 2: Enrich & Generate Answers

```python
from src.linkedin.linkedin_actions import enrich_and_generate_answers

# Run after search_linkedin_easy_apply completes
response = enrich_and_generate_answers(
    run_id="ffdb84f4-2a1e-4d9f-92e5-0eb5f41b5c8e",  # use run_id from phase 1
    limit=10,                     # optional: cap jobs per batch
    enrich_jobs=True,             # set False to skip job-level enrichment
    generate_answers=True,        # set False to only refresh enrichment metadata
    force_answer_regeneration=False
)

print(response.result["message"])
print(response.result["answers_generated"], "answer sets generated")
```

### Apply to Jobs

```python
from src.linkedin.linkedin_actions import apply_linkedin_easy_apply

apply_linkedin_easy_apply(
    job_url="https://www.linkedin.com/jobs/view/3846477685",
    headless=False,
    allow_submit=False,  # Set True to actually submit
    email="john@example.com",
    phone="5551234567",
    phone_country="United States (+1)",
    answers={
        "sponsorship_required": "No",
        "authorized_to_work": "Yes",
        "years_experience": "5"
    }
)
```

## Actions API

### `search_linkedin_easy_apply()`

Search and scrape LinkedIn jobs.

**Parameters:**
- `query` (str): Search query (job title, skills, company)
- `headless` (bool): Run browser in headless mode
- `max_jobs` (int): Maximum jobs to scrape
- `remote` (bool): Filter for remote jobs
- `hybrid` (bool): Filter for hybrid jobs
- `onsite` (bool): Filter for on-site jobs

**Returns:**
- `job_ids_found`: List of all scraped job IDs
- `easy_apply_job_ids`: List of Easy Apply job IDs
- `db_records_written`: Number of records written to database
- `csv_exported`: Path to exported CSV file
- `pending_enrichment_job_ids`: Easy Apply jobs queued for `enrich_and_generate_answers`
- `pending_enrichment_count`: Count of jobs still needing enrichment/answers
- `message`: Summary with next-step reminder

### `enrich_and_generate_answers()`

Run Phase 2 processing on previously scraped jobs. Enrichment and answer generation can be toggled independently to optimize cost/performance.

**Parameters:**
- `run_id` (str, optional): Process jobs from a specific search run
- `job_ids` (List[str], optional): Explicit job IDs to process
- `limit` (int, optional): Maximum number of jobs to handle this run
- `enrich_jobs` (bool): Run OpenAI job enrichment (default `True`)
- `generate_answers` (bool): Generate Easy Apply answers (default `True`)
- `force_reprocess` (bool): Re-run enrichment even if up-to-date
- `force_answer_regeneration` (bool): Regenerate answers even when a recent set exists

**Returns:**
- `processed`: Number of jobs processed this batch
- `enriched`: Count of jobs with refreshed enrichment metadata
- `answers_generated`: Count of new/updated answer sets stored in `enriched_answers`
- `skipped`: Jobs not processed (with reasons)
- `failed`: Jobs that encountered errors (with diagnostic info)
- `settings`: Echo of the parameters used

### `apply_linkedin_easy_apply()`

Apply to a job via Easy Apply.

**Parameters:**
- `job_url` (str): Full LinkedIn job URL
- `headless` (bool): Run browser in headless mode
- `allow_submit` (bool): Actually submit the application
- `email` (str): Your email address
- `phone` (str): Your phone number
- `phone_country` (str): Country code label (e.g., "United States (+1)")
- `answers` (dict): Form answers mapping field_id/name to value

**Returns:**
- `applied`: Whether application was submitted
- `progressed_but_not_submitted`: Filled form but didn't submit
- `fill_summary`: Details of which fields were filled

### `update_job_fit_status()`

Manually override AI-generated fit analysis for jobs. Useful for correcting AI decisions or bulk-updating job fit status.

**Parameters:**
- `job_ids` (List[str]): List of LinkedIn job IDs to update (e.g., `["3846477685", "3912345678"]`)
- `mark_as_good_fit` (bool): Set `True` to mark as good fit, `False` for bad fit (default: `True`)
- `fit_score` (float, optional): Fit score between 0.0-1.0 (defaults to 0.8 for good fit, 0.3 for bad fit)

**Returns:**
- `success`: Whether the update succeeded
- `updated_count`: Number of jobs actually updated
- `changes_applied`: The fit status and score applied
- `verification_sample`: Sample job showing the updated values

**Example Usage:**

```python
from src.linkedin.ai_actions.enrichment import update_job_fit_status

# Mark multiple jobs as good fits with default high score
result = update_job_fit_status(
    job_ids=["3846477685", "3912345678", "3998877665"],
    mark_as_good_fit=True
)

# Mark jobs as bad fits
result = update_job_fit_status(
    job_ids=["9999999"],
    mark_as_good_fit=False
)

# Set custom fit score
result = update_job_fit_status(
    job_ids=["3846477685"],
    mark_as_good_fit=True,
    fit_score=0.95
)
```

## Database Schema

`job_postings` is the source of truth for scraped job details plus enrichment metadata (fit score, confidence, timestamps).
`enriched_answers` stores every AI-generated answer set (answers, confidence, token usage). Downstream automation should reference `enriched_answers` when filling forms; `job_postings.answers_json` remains as a legacy cache.

Key fields in `job_postings` table:

```sql
CREATE TABLE job_postings (
    job_id VARCHAR PRIMARY KEY,
    title VARCHAR,
    company VARCHAR,
    job_url VARCHAR,
    
    -- Location
    location_raw VARCHAR,
    location_type VARCHAR,  -- Remote, Hybrid, On-site
    location_city VARCHAR,
    location_state VARCHAR,
    
    -- AI Enrichment
    experience_level VARCHAR,
    required_skills TEXT,  -- JSON array
    employment_type VARCHAR,
    salary_range VARCHAR,
    ai_confidence_score DOUBLE,  -- 0.0-1.0
    
    -- Form Automation
    questions_json TEXT,      -- Form questions
    answers_json TEXT,        -- AI-generated answers
    
    -- Metadata
    easy_apply BOOLEAN,
    scraped_at TIMESTAMP,
    ai_enriched_at TIMESTAMP
)
```

## OpenAI Integration

### How It Works

1. **Job Enrichment**: After scraping, OpenAI processes each job to:
   - Validate title and company name
   - Parse location into structured fields
   - Extract experience level and seniority
   - Identify required skills from job description
   - Determine employment type (Full-time, Contract, etc.)
   - Extract salary range if mentioned
   - Assign confidence score (0.0-1.0)

2. **Form Answer Generation**: When applying, OpenAI:
   - Analyzes form questions
   - Matches with your profile
   - Generates appropriate answers
   - Handles multiple choice, text, and yes/no questions

### Cost Estimate

Using `gpt-4o-mini` (default, most cost-effective):

- **Job Enrichment**: ~$0.0006 per job
- **Form Answers**: ~$0.001 per application
- **1000 jobs + 100 applications**: ~$0.60 + $0.10 = **$0.70 total**

Much cheaper than maintaining database infrastructure!

## Tips & Best Practices

### 1. Browser Context Persistence

Login once, reuse forever:

```python
from src.linkedin.linkedin_actions import set_browser_context

# Do this once
set_browser_context(headless_mode=False)
# Complete any verification if prompted

# Now all subsequent searches will reuse this login
search_linkedin_easy_apply(query="...", headless=True)
```

### 2. Batch Answers Without Re-Enrichment

If you only need to refresh form answers (for example, prompts changed but job metadata is still accurate), call:

```python
enrich_and_generate_answers(run_id=run_id, enrich_jobs=False, generate_answers=True, force_answer_regeneration=True)
```

Skipping enrichment keeps costs low while still updating `enriched_answers`.

### 3. Rate Limiting

Be respectful to LinkedIn:

```python
# Instead of scraping 1000 jobs at once
for query in ["Python Developer", "Data Scientist", "DevOps"]:
    search_linkedin_easy_apply(query=query, max_jobs=25)
    time.sleep(60)  # Wait between searches
```

### 4. Review AI-Generated Answers

Before submitting:

```python
answers = generate_answers(questions, profile, job)

# Check unanswered fields
if answers.unanswered_fields:
    print("Manual attention needed:", answers.unanswered_fields)

# Check confidence
if answers.confidence < 0.7:
    print("Low confidence - review answers manually")
```

### 5. Backup Your Data

```bash
# Simple backup
cp linkedin_jobs.sqlite backups/linkedin_jobs_$(date +%Y%m%d).sqlite

# Or export to CSV
sqlite3 linkedin_jobs.sqlite ".headers on" ".mode csv" "SELECT * FROM job_postings;" > backup_job_postings.csv
```

## Troubleshooting

### "OpenAI API key required"

Add to `.env`:
```bash
OPENAI_API_KEY=sk-proj-your-key-here
```

### "Easy Apply button not found"

This job might not have Easy Apply enabled. Check:
```python
job = read_job_by_id("job_id")
print(job['easy_apply'])  # Should be True
```

### "SQLite database locked"

Another process has the database open:
```bash
lsof linkedin_jobs.sqlite  # Check what's using it
```

### Low AI Confidence Scores

The job description might be vague or incomplete. You can:
- Review jobs with `ai_needs_review = true`
- Use higher quality model: `OPENAI_MODEL=gpt-4o`



## Project Structure

```
linkedin-easy-apply/
├── src/linkedin/
│   ├── ai_actions/              # AI enrichment and profile actions
│   ├── apply_actions/           # Easy Apply automation actions
│   ├── search_actions/          # Job search and scraping actions
│   ├── server_actions/          # Server utilities and exports
│   └── utils/                   # Database, OpenAI, models, tools
├── linkedin_jobs.sqlite         # Your job database (created automatically)
├── package.yaml                 # Sema4AI dependencies
├── .env                         # Your credentials (create this)
├── README.md                    # This file
```

## Environment Variables Reference

```bash
# Required
LINKEDIN_USERNAME=your_email@example.com
LINKEDIN_PASSWORD=your_password
OPENAI_API_KEY=sk-proj-your-key

# Optional
OPENAI_MODEL=gpt-4o-mini              # Default: gpt-4o-mini
SQLITE_PATH=/custom/path.sqlite       # Default: ./linkedin_jobs.sqlite
DATABASE_TYPE=sqlite                  # or "postgres"
DATABASE_URL=postgresql://user:password@host:5432/linkedin_jobs
```

## Development

### Running Tests

```bash
pytest tests/
```

### Type Checking

```bash
mypy src/
```

### Code Style

```bash
ruff check src/ tests/
ruff format src/ tests/
```


## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request


## Acknowledgments

- Built with [Sema4.ai Actions](https://sema4.ai/)
- Browser automation via [Robocorp Browser](https://github.com/robocorp/robocorp)
- AI powered by [OpenAI](https://openai.com/)


---

Note: This tool is for personal use and job search automation. Always respect LinkedIn's Terms of Service and use responsibly.
