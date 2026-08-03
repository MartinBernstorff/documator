import logging
from collections.abc import Callable
from typing import Annotated

import typer
from pydantic import BaseModel, ValidationError

from documator.domain import ExitCode, InputDir, OutputDir, TimeoutSeconds
from documator.engine import DEFAULT_TIMEOUT
from documator.render import render as _render
from documator.skills import skills as _skills
from documator.watch import watch as _watch

app = typer.Typer(name="documator", add_completion=False)


def _parsed[T: BaseModel](model: type[T]) -> Callable[[str], T]:
    def parse(raw: str) -> T:
        try:
            return model.model_validate(raw)
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
    watch: Annotated[bool, typer.Option("--watch")] = False,
    timeout: Annotated[
        TimeoutSeconds,
        typer.Option("--timeout", metavar="SECONDS", parser=_parsed(TimeoutSeconds)),
    ] = DEFAULT_TIMEOUT,
) -> None:
    run = _watch if watch else _render
    raise typer.Exit(run(input_dir, output_dir, timeout))


@app.command()
def skills(
    input_dir: Annotated[InputDir, typer.Argument(parser=_parsed(InputDir))],
    output_dir: Annotated[OutputDir, typer.Argument(parser=_parsed(OutputDir))],
    timeout: Annotated[
        TimeoutSeconds,
        typer.Option("--timeout", metavar="SECONDS", parser=_parsed(TimeoutSeconds)),
    ] = DEFAULT_TIMEOUT,
) -> None:
    raise typer.Exit(_skills(input_dir, output_dir, timeout))


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        # WARNING is the widest level we emit; padding keeps the messages aligned.
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    command = typer.main.get_command(app)
    # Standalone mode makes click print its own usage errors, but it exits rather
    # than returning, so the code comes back as a SystemExit.
    try:
        command.main(args=argv)
    except SystemExit as exit_signal:
        code = exit_signal.code
        return ExitCode(code if isinstance(code, int) else 0)
    return ExitCode(0)
