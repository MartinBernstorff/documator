from pathlib import Path

import typer
from pydantic import ValidationError

from documator.domain import OPERATIONAL_ERROR, InputDir, OutputDir
from documator.render import DEFAULT_TIMEOUT
from documator.render import render as _render

app = typer.Typer(name="documator", add_completion=False)


@app.callback()
def root() -> None: ...


@app.command()
def render(input_dir: Path, output_dir: Path) -> None:
    try:
        source, destination = InputDir(input_dir), OutputDir(output_dir)
    except ValidationError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(OPERATIONAL_ERROR) from error
    raise typer.Exit(_render(source, destination, DEFAULT_TIMEOUT))


def main(argv: list[str] | None = None) -> int:
    command = typer.main.get_command(app)
    return command.main(args=argv, standalone_mode=False) or 0
