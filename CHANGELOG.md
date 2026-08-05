# Changelog

All notable changes to this template. Generated from Conventional Commits with
[git-cliff](https://git-cliff.org). Clear this file when you start a project from
the template.

## Unreleased

### Bug fixes

- Close login user-enumeration timing oracle
- Bound password length to bcrypt input limit
- Harden secret key and JWT algorithm config
- Correct PATCH omitted vs null semantics
- Dispose the database engine on shutdown
- Make test database url optional
- Stop leaking details in error responses

### Features

- Add fastapi template
- Add database readiness probe
- Paginate the item listing
- Containerize the app and database
- Harden headers, docs gating, rate limits

### Miscellaneous

- Lint async and ruff-specific rules
- Add coverage, changelog, and audit tools

### Refactoring

- Invert service repository dependency
- Make private routes protected by default

### Tests

- Detect drift between models and migrations
- Cover auth failures and transaction boundary

### Ci

- Add pipeline, changelog, and license
