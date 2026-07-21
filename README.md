# FastAPI Backend Template

A clone-and-launch starter for FastAPI backends: async SQLAlchemy 2.0 + PostgreSQL,
Alembic migrations, JWT authentication, a layered (Router → Service → Repository)
architecture, and a test-first setup.

## Architecture

```
Request → Router (HTTP) → Service (business logic) → Repository (DB) → PostgreSQL
```

- `app/api/v1/routes` — HTTP layer (validation, status codes), no business logic.
- `app/services` — business rules, HTTP-agnostic, raises domain exceptions.
- `app/repositories` — the only layer that queries the database.
- `app/models` — SQLAlchemy ORM entities.
- `app/schemas` — Pydantic request/response contracts.
- `app/core` — config, security (JWT + password hashing), domain exceptions.
- `app/db` — declarative base and async session factory.

The transaction boundary is the request: `get_session` commits on success and rolls
back on error, so services and repositories only `flush`. Domain exceptions
(`NotFoundError`, `ConflictError`, `AuthError`) are mapped to HTTP responses by
handlers registered in `app/main.py`.

An example `Item` resource (owned by a `User`, JWT-protected) demonstrates the full
slice end to end.

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- A reachable PostgreSQL instance

## Setup

Install dependencies and create your environment file:

```bash
uv sync
cp .env.example .env          # then edit credentials
```

Create the database role and databases (adjust names/password to taste, then keep
`.env` in sync):

```bash
sudo -u postgres psql \
  -c "CREATE ROLE fastapi_user LOGIN PASSWORD 'secret123' CREATEDB;" \
  -c "CREATE DATABASE fastapi_db OWNER fastapi_user;" \
  -c "CREATE DATABASE fastapi_db_test OWNER fastapi_user;"
```

Apply migrations:

```bash
uv run alembic upgrade head
```

## Run the dev server

```bash
uv run fastapi dev app/main.py
```

Open http://127.0.0.1:8000/docs for the interactive API.

## Test-driven development

The suite uses a real PostgreSQL test database (`TEST_DATABASE_URL`) with a per-test
transaction that is rolled back — fast and fully isolated. The schema is created
once per test session with `Base.metadata.create_all`; Alembic remains the source of
truth for the real database.

Red → green → refactor:

1. Write a failing test under `tests/unit` (logic, mocked repository) or
   `tests/integration` (routes through the test DB).
2. Run it and watch it fail.
3. Write the minimal code to pass.
4. Refactor with the test as a safety net.

```bash
uv run pytest                       # whole suite
uv run pytest tests/unit -v         # fast unit tests
uv run pytest path::test_name -v    # a single test
```

## Adding a new resource

Copy the `Item` slice, renaming across the layers:

1. `app/models/<name>.py` — ORM model (register it in `app/models/__init__.py`).
2. `app/schemas/<name>.py` — Pydantic schemas.
3. `app/repositories/<name>_repo.py` — queries.
4. `app/services/<name>_service.py` — business rules.
5. `app/api/v1/routes/<name>.py` — routes; include it in `app/api/v1/router.py`.
6. Add a dependency provider in `app/api/deps.py`.
7. Write unit + integration tests first.

## Migrations

```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
uv run alembic downgrade -1
```

## Quality tooling

```bash
uv run pre-commit install     # enable hooks (once)
uv run ruff check .           # lint
uv run ruff format .          # format
uv run mypy app               # type-check
```

## Project layout

```
app/
  main.py                 # app factory; routers + exception handlers
  core/                   # config, security, exceptions
  db/                     # declarative base, async session
  api/
    deps.py               # shared dependencies (session, current user, services)
    v1/
      router.py           # aggregates all v1 routers
      routes/             # auth, users, items
  models/                 # SQLAlchemy models
  schemas/                # Pydantic schemas
  repositories/           # database access
  services/               # business logic
alembic/                  # migration environment + versions
tests/
  unit/                   # logic with mocked repositories
  integration/            # routes through the test database
```
