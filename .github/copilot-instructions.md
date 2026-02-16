# Claw Journal Copilot Instructions

You are an expert developer working on **Claw Journal**, an observability and analytics backend for OpenClaw. This project is a local Python service that parses logs, tracks token usage/costs, and provides a web dashboard.

## Tech Stack & Environment
- **Language**: Python 3.9+ (Active use of `from __future__ import annotations`).
- **Web Framework**: FastAPI (`claw_journal.api`).
- **Database**: SQLite with raw SQL (`claw_journal.storage`). No ORM.
- **Models**: Python `dataclasses` (`claw_journal.models`).
- **Testing**: `pytest` (future).

## Coding Guidelines

### 1. Python Style & Typing
- **Type Hints**: Always use strict type hints for function arguments and return values.
  - Use modern syntax: `list[str] | None` instead of `List[str], Optional[str]`.
  - Always include `from __future__ import annotations` at the top of every file.
- **Dataclasses**: Prefer standard library `@dataclass` for internal data structures over Pydantic or raw dictionaries.
- **Imports**: Organize imports: standard library first, then third-party, then local application imports.

### 2. Architecture & Patterns
- **Layered Architecture**: Respect the separation of concerns:
  - `api.py`: FastAPI routes and HTTP handling.
  - `service.py`: Business logic and orchestration.
  - `storage.py`: Database interaction (Repository pattern).
  - `ingest.py`: Log parsing and ingestion loops.
- **Database Access**:
  - Use the existing `UsageRepository` class in `storage.py`.
  - Write **raw SQL** queries. Do NOT introduce an ORM (like SQLAlchemy or Peewee).
  - Use context managers (`with self._connect() as conn:`) to ensure connections are closed.
  - Creating the schema should be idempotent (`CREATE TABLE IF NOT EXISTS`).

### 3. API & Dashboard
- **FastAPI**: Use dependency injection for services where possible, or pass manually in `main.py` factory functions.
- **HTML/Frontend**: For the MVP, HTML is embedded directly in Python strings within `api.py` (or potential template files). Keep it simple and dependency-free (no complex Jinja2 setup unless requested).

### 4. Logging & Config
- Use the standard `logging` module.
- Configuration is loaded via `os.environ` or `.env` files (handled in `config.py`). strictly typed config objects are preferred.

## Constraints
- **Dependencies**: Minimize new dependencies. Stick to `fastapi`, `uvicorn`, and the standard library unless a new requirement absolutely demands it.
- **Async**: The project currently uses synchronous definitions for many components (SQLite is blocking). Be mindful when mixing `async def` routes with blocking DB calls; run them in thread pools if necessary or keep them synchronous if performance permits for local use.
