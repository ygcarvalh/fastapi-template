# Changelog

All notable changes to this template. Generated from Conventional Commits with [git-cliff](https://git-cliff.org). Clear this file when you start a project from the template.

## 1.0.0 - 2026-09-11

### Bug fixes

- Normalize email addresses to lowercase
- Rate limit the logout endpoint
- Refresh an item after a partial update

### Documentation

- Describe the security review and new settings

### Features

- Refuse request bodies above a size limit
- Send Cache-Control no-store on responses
- Allow named CORS origins via CORS_ORIGINS

### Miscellaneous

- [fastapi] initial template project
- Add psql service and bind db to loopback
- Wire commit-msg and pip-audit hooks
- Refresh the locked dependency set

### Refactoring

- Move account use cases into services
- Group core into http and observability
- Fold the email lookup protocol
