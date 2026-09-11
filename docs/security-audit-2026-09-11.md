# Security review, 2026-09-11

A pass over the template before the 1.0.0 tag, done alongside the same pass on `angular-template`. It covers the code under `app/`, the compose file, the container image, the hooks, and the locked dependency set. The frontend sibling's `SECURITY.md` was read as a list of what a client expects from this API.

## What was checked and found sound

- `uv run pip-audit` reports no known vulnerabilities in the lock file, before and after the refresh recorded in this release.
- `.env` is ignored by git and excluded from the image; the tracked `.env.example` holds placeholders only.
- Every route outside `PUBLIC_OPERATIONS` requires a bearer token, enforced by `tests/integration/test_route_policy.py`.
- Items are scoped to their owner in the repository query, so a caller cannot read or edit another account's rows by guessing an id.
- Access and refresh tokens each check their `typ` claim, so one cannot stand in for the other.
- Login pays for a bcrypt verification whether or not the account exists, so response time does not reveal existence.
- The error envelope drops the submitted `input` from 422 bodies, and the access log records metadata only.
- The inbound `X-Request-ID` is filtered to `[A-Za-z0-9_-]{1,64}` before it reaches a log line.
- The image runs as an unprivileged user, both base images are pinned by digest, and the build stage stays out of the runtime stage.

## Findings and what changed

| Severity | Finding | Resolution |
| --- | --- | --- |
| Medium | No bound on the request body. An anonymous `POST /api/v1/users` carrying an enormous body was read into memory before validation ran. | `MAX_REQUEST_BODY_BYTES`, 1 MiB by default, enforced in `app/core/http/body_limit.py`. A declared length above it answers 413 before the route; a streamed body is cut off where it passes the limit. |
| Medium | Email addresses were compared as sent. `Ada@Example.com` and `ada@example.com` registered two accounts, and login demanded the exact case used at signup. | Lowercased in `UserCreate`, `UserUpdate` and `AuthService.authenticate`. Migration `0a456e5b983c` lowercases stored rows and fails where two active accounts collide, so a human decides which survives. |
| Medium | The rate limiter and the request log keyed on `request.client.host`. Behind a reverse proxy every caller shared the proxy's address, and turning on proxy headers without naming the proxy would have let a caller pick its own. | Compose starts uvicorn with `--proxy-headers` and passes `FORWARDED_ALLOW_IPS` through, empty by default, so `X-Forwarded-For` is ignored until a proxy is named. Documented in the pre-deploy checklist. |
| Low | `POST /api/v1/auth/logout` was public and unthrottled: an unauthenticated database write at the caller's pace. | Shares `LOGIN_RATE_LIMIT` with login, refresh and password change. |
| Low | Responses carried no `Cache-Control`. Token and profile bodies could be kept by an intermediary. | `Cache-Control: no-store` on every response, asserted with the other hardening headers. |
| Low | The database port was published on every interface with a default password in the compose file. | Published on `127.0.0.1` only. |
| Low | Cross-origin deployments had to hand-edit `app/main.py`, and the frontend's `SECURITY.md` notes that a missing `Access-Control-Expose-Headers` silently hides the correlation ID. | `CORS_ORIGINS` adds `CORSMiddleware` for named origins, no credentials, `X-Request-ID` exposed. A `*` refuses to start. |
| Info | `SECURITY.md` and `.env.example` still described refresh tokens as stateless and unrevocable, which stopped being true when `refresh_tokens` was added. | Both corrected. |
| Info | Outdated dependencies: alembic, pyjwt, sqlalchemy, pwdlib, pydantic-settings, ruff, mypy, pre-commit. | Lock refreshed within the existing floors; the suite and `pip-audit` pass on the result. |

## Parity with the frontend siblings

`angular-template` gates commits with commitlint on a `commit-msg` hook and runs its audit by hand. This repository had `scripts/check-commit-messages.sh` but nothing ran it. The script now accepts a message file as well as a range, `.pre-commit-config.yaml` runs it at `commit-msg`, and `pip-audit` runs at push whenever the lock changed.

## Architecture pass

A read of every module after the findings above, recorded here because the fixes changed the layout.

- `PATCH /items/{id}` answered with the `updated_at` the row had before the write, because `ItemService.update` mutated the object and let the request commit later. It now writes the item back through the repository, which flushes and refreshes, the way `UserService.update` already did.
- `DELETE /users/me` and `POST /auth/password` each called two services from the route. Deactivation now lives in `UserService.deactivate` and the password change in `AuthService.change_password`, so the rule that items go with the account and refresh tokens go with the password has one home.
- `app/core/request_recorder.py` imported repositories and services from inside `core`. It moved to `app/api/request_recorder.py`, next to the composition root, and the middleware keeps only the `RequestRecorder` callable type.
- `app/core` had grown to thirteen flat modules. The middleware stack is now `app/core/http` and logging, correlation IDs, the access log and metrics are `app/core/observability`; domain exceptions stayed in `app/core/exceptions.py`, with the HTTP handlers split out to `app/core/http/errors.py`.
- `SupportsFindUserByEmail` in `protocols.py` had no user besides `UserRepositoryProtocol` and was folded into it.

## Standing debt

Nothing here blocked the tag. Each item is a decision for the project that copies the template rather than for the template.

- **Rate limits count per address, not per account.** A distributed guess against one account is limited only by how many addresses the attacker has. A per-account lockout or a slower hash after repeated failures needs a place to store the count, and the in-memory limiter is not it.
- **The rate limiter is in-process.** Documented in `SECURITY.md`: point slowapi at Redis before running more than one worker.
- **A body that streams in without `Content-Length` is refused only when the route reads it.** FastAPI reads the body inside the route handler, so a `GET` carrying a chunked body is never read and never refused. Nothing is buffered either, so the exposure is a connection held open, which uvicorn's own timeouts bound.
- **`/metrics` and `/health/ready` are public.** Meant for a scraper and a load balancer on the internal network; keep them off the public listener at the proxy.
- **Access tokens outlive a password change** for the rest of their 30 minutes. `SECURITY.md` names the fix: a `password_changed_at` column compared against `iat`.
- **Registration reveals whether an address is taken.** A deliberate trade for a usable signup form, described in `README.md` along with what closing it would cost.
- **The refresh token is not rotated.** Deliberate, because the frontends refresh from two places. `SECURITY.md` describes when to change that.
- **No `TrustedHostMiddleware`.** The application never builds a URL from the `Host` header, so a forged one has nothing to poison. Add it if a redirect or an email link ever derives from the request.
- **Tokens carry no `iss` or `aud`.** Each environment has its own `SECRET_KEY`, which is what keeps a staging token out of production; the claims would add a second line of defense for the case where a key is reused by mistake.
