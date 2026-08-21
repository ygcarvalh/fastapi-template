from app.main import app

PUBLIC_OPERATIONS = {
    ("post", "/api/v1/auth/login"),
    ("post", "/api/v1/auth/refresh"),
    ("post", "/api/v1/users"),
    ("post", "/api/v1/auth/logout"),
    ("get", "/health"),
    ("get", "/health/ready"),
    ("get", "/metrics"),
}

MINIMUM_DISCOVERED_OPERATIONS = 16


def _operations() -> dict[tuple[str, str], bool]:
    schema = app.openapi()
    return {
        (method, path): bool(operation.get("security"))
        for path, operations in schema["paths"].items()
        for method, operation in operations.items()
    }


def test_the_inventory_actually_discovers_the_routes() -> None:
    operations = _operations()

    assert len(operations) >= MINIMUM_DISCOVERED_OPERATIONS
    assert ("get", "/api/v1/items") in operations
    assert ("get", "/api/v1/users/me") in operations
    assert ("patch", "/api/v1/users/me") in operations
    assert ("post", "/api/v1/auth/password") in operations
    assert ("get", "/api/v1/requests") in operations


def test_every_route_is_protected_or_explicitly_public() -> None:
    unprotected = {
        operation
        for operation, is_protected in _operations().items()
        if not is_protected and operation not in PUBLIC_OPERATIONS
    }

    assert unprotected == set()


def test_the_public_allowlist_has_no_stale_entries() -> None:
    assert set(_operations()) >= PUBLIC_OPERATIONS
