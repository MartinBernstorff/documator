import logging
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from pydantic import RootModel, ValidationError

from documator.domain import ExitCode, InputDir, OutputDir
from documator.render import DEFAULT_TIMEOUT
from documator.render import render as _render

app = typer.Typer(name="documator", add_completion=False)


def _parsed[T: RootModel[Path]](model: type[T]) -> Callable[[str], T]:
    def parse(raw: str) -> T:
        try:
            return model(Path(raw))
        except ValidationError as error:
            reasons = "; ".join(problem["msg"] for problem in error.errors())
            raise typer.BadParameter(reasons) from error

    return parse


@app.callback()
def root() -> None: ...


@app.command()
def render(
    input_dir: Annotated[InputDir, typer.Argument(parser=_parsed(InputDir))],
    output_dir: Annotated[OutputDir, typer.Argument(parser=_parsed(OutputDir))],
) -> None:
    raise typer.Exit(_render(input_dir, output_dir, DEFAULT_TIMEOUT))


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    command = typer.main.get_command(app)
    try:
        return command.main(args=argv, standalone_mode=False) or 0
    except typer.BadParameter as error:
        error.show()
        return ExitCode(error.exit_code)
