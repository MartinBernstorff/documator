import logging
from pathlib import Path

import typer

# typer vendors its own click, so the upstream click.UsageError never matches.
from typer._click.exceptions import UsageError

from documator.domain import InputDir, OutputDir
from documator.render import DEFAULT_TIMEOUT, EXIT_OPERATIONAL_ERROR
from documator.render import render as _render

app = typer.Typer(name="documator", add_completion=False)


@app.callback()
def root() -> None: ...


@app.command()
def render(input_dir: Path, output_dir: Path) -> None:
    code = _render(InputDir(input_dir), OutputDir(output_dir), DEFAULT_TIMEOUT)
    raise typer.Exit(code)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    command = typer.main.get_command(app)
    try:
        return command.main(args=argv, standalone_mode=False) or 0
    except UsageError as error:
        error.show()
        return EXIT_OPERATIONAL_ERROR
