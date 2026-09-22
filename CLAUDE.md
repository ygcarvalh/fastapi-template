# FastAPI Template

Read `CONTRIBUTING.md` before changing anything. It is short, and it is where the conventions live. `README.md` explains why each piece is built the way it is.

The ones that are easiest to get wrong:

- **Dependencies point inward: `Router → Service → Repository → PostgreSQL`.** A route validates, calls one service and shapes the response; it holds no business rule and never touches a session or a model query. A service raises domain exceptions from `core/exceptions.py` and knows nothing about HTTP. Only `repositories/` queries the database. See "Layout".
- **A service depends on a Protocol, never on a concrete repository.** The interface it needs goes in `services/protocols.py`, and `api/deps.py` is the only place that wires a real repository in. That is what lets `tests/unit` drive the logic against the typed fakes in `tests/unit/fakes.py`.
- **A repository extends `CrudRepository[Model]`, and `SoftDeleteRepository[Model]` too when the model carries `SoftDeleteMixin`.** Between them they supply `get`, `create`, `save`, `delete` and `soft_delete` on top of `BaseRepository`'s session, flush, refresh, rowcount and batch-delete plumbing, so a new repository writes queries and nothing else. Do not re-implement `create`, `save`, `delete` or `soft_delete`, and do not re-add a `__init__`, a `cast(CursorResult[Any], ...)` or a hand-rolled batch delete. A repository whose model has no single-row CRUD shape at all, an append-only log like `AuditLogRepository` or `RequestLogRepository`, stays on bare `BaseRepository`. Override `_flush` when a write needs its own failure translation, the way `ItemRepository` turns a `StaleDataError` into a 412.
- **A paginated read that cannot count uses `cursor_slice`.** Fetch `limit + 1` rows in the repository and hand the result to `cursor_slice` from `schemas/pagination.py`; it drops the extra row and turns it into the next cursor. Counting a table that grows without bound is the thing the cursor exists to avoid, so do not add a `total` to one of those endpoints.
- **A token that may be used once goes through `SingleUseTokenIssuer`.** Email confirmation and password reset both issue through it, so the cooldown, the revocation of earlier tokens and the hashing stay in one place. Use `redeem` to resolve a token back to its row and its user.
- **A failure is named by a code, not by a sentence.** Every way a resource can refuse gets an entry in `core/error_codes.py`, because the frontend translates the code and shows the message only as a fallback. A new raise site with no code is a string the reader cannot have in their own language.
- **Never edit a migration that already landed.** Generate a new one. `tests/integration/test_migration_drift.py` provisions a throwaway database, applies every migration and diffs the result against `Base.metadata`, so a model changed without a migration fails the suite.
- **Write the test first.** New behavior needs a test; a bug fix needs the regression test that fails before the fix. `uv run pytest --cov` fails under 90%.

These five commands are the whole gate, and there is no CI workflow behind them:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests
uv run pytest --cov
uv run pip-audit
```

`mypy` runs in strict mode and `tests/` is covered by it too. The suite needs a reachable `TEST_DATABASE_URL` whose role has `CREATEDB`, or Docker for the testcontainers fallback.

Commits are Conventional Commits, header only, imperative mood, no trailing period, 50 characters or fewer. Put the reasoning in the pull request.
