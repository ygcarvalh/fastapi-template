import argparse
import re
import secrets
import sys
from pathlib import Path

TEMPLATE_NAME = "fastapi-template"
SECRET_PLACEHOLDER = "change-me-in-production-to-a-random-32-byte-string"  # noqa: S105
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,48}[a-z0-9]$")
SECRET_KEY_BYTES = 32

CHANGELOG_HEADER = """# Changelog

All notable changes to this project. Generated from Conventional Commits with
[git-cliff](https://git-cliff.org).
"""

RENAMED_FILES = (
    "pyproject.toml",
    "compose.yaml",
    ".env.example",
    "alembic.ini",
)

NEXT_STEPS = """
Done. What is left:
  1. docker compose up -d db
  2. uv sync
  3. uv run alembic upgrade head
  4. uv run fastapi dev app/main.py
"""


def valid_name(name: str) -> str:
    if not NAME_PATTERN.match(name):
        raise argparse.ArgumentTypeError(
            "a project name is lowercase letters, digits and dashes, "
            "3 to 50 characters, starting with a letter"
        )
    return name


def rename(text: str, new_name: str) -> str:
    return text.replace(TEMPLATE_NAME, new_name)


def with_generated_secret(text: str) -> str:
    return text.replace(SECRET_PLACEHOLDER, secrets.token_hex(SECRET_KEY_BYTES))


def rename_files(root: Path, new_name: str) -> list[str]:
    touched = []
    for name in RENAMED_FILES:
        path = root / name
        if not path.exists():
            continue
        original = path.read_text()
        renamed = rename(original, new_name)
        if renamed != original:
            path.write_text(renamed)
            touched.append(name)
    return touched


def write_env(root: Path, new_name: str) -> bool:
    target = root / ".env"
    example = root / ".env.example"
    if target.exists() or not example.exists():
        return False
    target.write_text(with_generated_secret(rename(example.read_text(), new_name)))
    return True


def reset_changelog(root: Path) -> bool:
    path = root / "CHANGELOG.md"
    if not path.exists():
        return False
    path.write_text(CHANGELOG_HEADER)
    return True


def bootstrap(root: Path, new_name: str) -> list[str]:
    done = [f"renamed {file}" for file in rename_files(root, new_name)]
    if write_env(root, new_name):
        done.append("wrote .env with a generated SECRET_KEY")
    else:
        done.append(".env was left alone because it already exists")
    if reset_changelog(root):
        done.append("emptied CHANGELOG.md")
    return done


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Turn this clone into a project of your own."
    )
    parser.add_argument(
        "name",
        nargs="?",
        default=root.name,
        type=valid_name,
        help="the project name, lowercase with dashes",
    )
    arguments = parser.parse_args(argv)

    for line in bootstrap(root, arguments.name):
        print(line)
    print(NEXT_STEPS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
