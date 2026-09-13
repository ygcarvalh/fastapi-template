import argparse
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bootstrap.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bootstrap", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bootstrap = _load()


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        'name = "fastapi-template"\nfastapi-template = "app.cli.main:cli"\n'
    )
    (tmp_path / "compose.yaml").write_text("name: fastapi-template\n")
    (tmp_path / ".env.example").write_text(
        f"SERVICE_NAME=fastapi-template\nSECRET_KEY={bootstrap.SECRET_PLACEHOLDER}\n"
    )
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## 1.1.0\n- something\n")
    return tmp_path


@pytest.mark.parametrize("name", ["shop", "my-shop", "shop2026"])
def test_a_usable_project_name_is_accepted(name: str) -> None:
    assert bootstrap.valid_name(name) == name


@pytest.mark.parametrize(
    "name", ["My-Shop", "sh", "-shop", "shop-", "shop_name", "a" * 60]
)
def test_a_name_that_would_break_a_package_is_refused(name: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        bootstrap.valid_name(name)


def test_every_mention_of_the_template_is_renamed(clone: Path) -> None:
    bootstrap.bootstrap(clone, "shop")

    assert "fastapi-template" not in (clone / "pyproject.toml").read_text()
    assert 'name = "shop"' in (clone / "pyproject.toml").read_text()
    assert (clone / "compose.yaml").read_text() == "name: shop\n"


def test_the_generated_env_carries_a_real_secret(clone: Path) -> None:
    bootstrap.bootstrap(clone, "shop")

    written = (clone / ".env").read_text()
    assert bootstrap.SECRET_PLACEHOLDER not in written
    assert "SERVICE_NAME=shop" in written
    secret = next(
        line for line in written.splitlines() if line.startswith("SECRET_KEY=")
    )
    assert len(secret.removeprefix("SECRET_KEY=")) == 64


def test_two_runs_never_generate_the_same_secret(clone: Path, tmp_path: Path) -> None:
    bootstrap.bootstrap(clone, "shop")
    first = (clone / ".env").read_text()
    (clone / ".env").unlink()
    bootstrap.bootstrap(clone, "shop")

    assert (clone / ".env").read_text() != first


def test_an_env_that_already_exists_is_never_overwritten(clone: Path) -> None:
    (clone / ".env").write_text("SECRET_KEY=mine\n")

    done = bootstrap.bootstrap(clone, "shop")

    assert (clone / ".env").read_text() == "SECRET_KEY=mine\n"
    assert any("already exists" in line for line in done)


def test_the_changelog_starts_empty(clone: Path) -> None:
    bootstrap.bootstrap(clone, "shop")

    assert "1.1.0" not in (clone / "CHANGELOG.md").read_text()
    assert (clone / "CHANGELOG.md").read_text().startswith("# Changelog")


def test_a_clone_missing_a_file_still_bootstraps(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('name = "fastapi-template"\n')

    done = bootstrap.bootstrap(tmp_path, "shop")

    assert "renamed pyproject.toml" in done
