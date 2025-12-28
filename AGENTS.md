# Repository Guidelines

## Project Structure & Module Organization
- `src/linkedin/` holds the action server logic: `search_actions/`, `apply_actions/`, `ai_actions/`, `server_actions/`, and shared utilities in `utils/`.
- `tests/` contains pytest suites for DB helpers, SQLite behavior, and formatting utilities.
- `retro-ui/` is the optional Node/Express + static UI client.
- `sql/` contains schema and analysis queries; `scripts/` has database utilities; `docs/` and `devdata/` include reference material and sample inputs.
- Root-level Docker assets live in `Dockerfile`, `docker-compose.yml`, and `Makefile`.

## Build, Test, and Development Commands
- `make build` / `make run`: build and run the action server container locally.
- `make compose-up` / `make compose-down`: start/stop the full stack (Postgres + action server + retro UI).
- `pytest tests/`: run the Python test suite.
- `mypy src/`: static type checking for the Python code.
- `ruff check src/ tests/` and `ruff format src/ tests/`: lint and format Python.
- `cd retro-ui && npm install && npm start`: run the retro UI locally (listens on `http://localhost:3001`).

## Coding Style & Naming Conventions
- Python: 4-space indentation; `snake_case` functions/modules, `PascalCase` classes, constants in `UPPER_SNAKE_CASE`.
- JS/CSS (retro UI): 4-space indentation; `camelCase` variables/functions; CSS classes in `kebab-case`.
- Prefer `ruff format` for Python formatting and keep utilities in `src/linkedin/utils/` reusable.

## Testing Guidelines
- Use pytest in `tests/` with `test_*.py` naming.
- Keep tests fast and local; avoid hitting real LinkedIn or OpenAI services.
- If you add DB logic, extend the SQLite tests and keep fixtures isolated per test.

## Commit & Pull Request Guidelines
- Recent commits mix conventional commits (`feat(scope): ...`) and plain imperative subjects. Use a short, imperative summary and add a scope when it helps clarity.
- PRs should include a clear description, test results (or why not run), and screenshots/gifs for `retro-ui/` changes.
- Link related issues and call out any config or schema changes explicitly.

## Security & Configuration Tips
- Store credentials in `.env` (e.g., `LINKEDIN_USERNAME`, `OPENAI_API_KEY`) and never commit secrets or local SQLite databases.
- Validate `DATABASE_TYPE` and `DATABASE_URL` changes with `docker compose` if you touch DB logic.
