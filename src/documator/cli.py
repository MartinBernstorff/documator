import logging
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from pydantic import RootModel, ValidationError

# Typer vendors its own click, so the UsageError it raises is not the one `import
# click` resolves to.
from typer._click.exceptions import UsageError

from documator.domain import ExitCode, InputDir, OutputDir, TimeoutSeconds
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


def _parsed_timeout(raw: str) -> TimeoutSeconds:
    try:
        seconds = TimeoutSeconds(float(raw))
    except ValueError as error:
        raise typer.BadParameter(
            f"timeout is not a number of seconds: {raw}"
        ) from error
    if seconds <= 0:
        raise typer.BadParameter(f"timeout must be positive: {raw}")
    return seconds


@app.callback()
def root() -> None: ...


@app.command()
def render(
    input_dir: Annotated[InputDir, typer.Argument(parser=_parsed(InputDir))],
    output_dir: Annotated[OutputDir, typer.Argument(parser=_parsed(OutputDir))],
    timeout: Annotated[
        TimeoutSeconds, typer.Option(parser=_parsed_timeout)
    ] = TimeoutSeconds(10.0),
) -> None:
    raise typer.Exit(_render(input_dir, output_dir, timeout))


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    command = typer.main.get_command(app)
    try:
        return command.main(args=argv, standalone_mode=False) or 0
    except UsageError as error:
        error.show()
        return ExitCode(error.exit_code)
