import os

# Tests that care about the write build their own app with a recorder; without
# this, every other test would write rows to the development database.
os.environ.setdefault("REQUEST_LOG_PERSIST_ENABLED", "false")
