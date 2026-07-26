from pathlib import Path

import typer

from documator.domain import InputDir, OutputDir
from documator.render import DEFAULT_TIMEOUT
from documator.render import render as _render

app = typer.Typer(name="documator", add_completion=False)


@app.callback()
def root() -> None: ...


@app.command()
def render(input_dir: Path, output_dir: Path) -> None:
    code = _render(InputDir(input_dir), OutputDir(output_dir), DEFAULT_TIMEOUT)
    raise typer.Exit(code)


def main(argv: list[str] | None = None) -> int:
    command = typer.main.get_command(app)
    return command.main(args=argv, standalone_mode=False) or 0
