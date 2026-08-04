import logging
from collections.abc import Callable
from typing import Annotated

import colorlog
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


# Raising the level rather than dropping the handler, so a quiet run still says the one
# thing worth interrupting for: silence means the run was clean.
@app.callback()
def root(
    quiet: Annotated[bool, typer.Option("--quiet")] = False,
) -> None:
    if quiet:
        logging.getLogger("documator").setLevel(logging.WARNING)


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
    if watch:
        raise typer.Exit(_watch(_render, input_dir, output_dir, timeout))
    raise typer.Exit(_render(input_dir, output_dir, timeout))


@app.command()
def skills(
    input_dir: Annotated[InputDir, typer.Argument(parser=_parsed(InputDir))],
    output_dir: Annotated[OutputDir, typer.Argument(parser=_parsed(OutputDir))],
    watch: Annotated[bool, typer.Option("--watch")] = False,
    timeout: Annotated[
        TimeoutSeconds,
        typer.Option("--timeout", metavar="SECONDS", parser=_parsed(TimeoutSeconds)),
    ] = DEFAULT_TIMEOUT,
) -> None:
    if watch:
        raise typer.Exit(_watch(_skills, input_dir, output_dir, timeout))
    raise typer.Exit(_skills(input_dir, output_dir, timeout))


def main(argv: list[str] | None = None) -> int:
    handler = logging.StreamHandler()
    handler.setFormatter(
        colorlog.ColoredFormatter(
            # WARNING is the widest level we emit; padding keeps the messages aligned.
            "%(log_color)s%(asctime)s %(levelname)-7s %(message)s",
            datefmt="%H:%M:%S",
            # Colour is for a human reading a terminal; a pipe gets the plain text.
            no_color=not handler.stream.isatty(),
        )
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    command = typer.main.get_command(app)
    # Standalone mode makes click print its own usage errors, but it exits rather
    # than returning, so the code comes back as a SystemExit.
    try:
        command.main(args=argv)
    except SystemExit as exit_signal:
        code = exit_signal.code
        return ExitCode(code if isinstance(code, int) else 0)
    return ExitCode(0)
