import asyncio
from collections.abc import Coroutine
from typing import Any

import typer

from app.cli import actions
from app.core.exceptions import DomainError
from app.db.session import dispose_engine

cli = typer.Typer(help="Administrative commands for this deployment.")


def _run[T](work: Coroutine[Any, Any, T]) -> T:
    async def runner() -> T:
        try:
            return await work
        finally:
            await dispose_engine()

    try:
        return asyncio.run(runner())
    except DomainError as error:
        raise typer.BadParameter(error.detail) from error


@cli.command("create-superuser", help="Register an account holding every permission.")
def create_superuser(
    email: str = typer.Option(..., prompt=True),
    password: str = typer.Option(..., prompt=True, hide_input=True),
) -> None:
    typer.echo(_run(actions.create_superuser(email, password)))


@cli.command("grant-role", help="Give an account a role it does not hold yet.")
def grant_role(email: str, role: str) -> None:
    typer.echo(_run(actions.grant_role(email, role)))


@cli.command("verify-email", help="Confirm an address without sending mail.")
def verify_email(email: str) -> None:
    typer.echo(_run(actions.verify_email(email)))


@cli.command(help="Write the base roles and permissions into an empty database.")
def seed() -> None:
    typer.echo(_run(actions.seed()))


@cli.command(help="Run every retention job once and report what it removed.")
def prune() -> None:
    typer.echo(_run(actions.prune()))


if __name__ == "__main__":
    cli()
