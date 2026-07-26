from importlib.metadata import version as _version

import typer

app = typer.Typer(name="documator")


def _version_callback(show: bool) -> None:
    if show:
        typer.echo(f"documator {_version('documator')}")
        raise typer.Exit


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    show_version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True
    ),
) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo("Hello from documator!")


def main(argv: list[str] | None = None) -> int:
    command = typer.main.get_command(app)
    return command.main(args=argv, standalone_mode=False) or 0
