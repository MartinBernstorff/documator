import logging
from collections.abc import Callable
from typing import NewType, TextIO, override

import colorlog
from iterpy import Arr

LogLevel = NewType("LogLevel", int)
Count = NewType("Count", int)
Noun = NewType("Noun", str)
Tally = NewType("Tally", str)
Report = NewType("Report", str)


# INFO is the bulk of a run, so only the levels worth noticing carry colour.
def _level_colours() -> dict[str, str]:
    return {"WARNING": "yellow", "ERROR": "red", "CRITICAL": "bold_red"}


# colorlog reads the stream to decide whether escape codes reach it at all, which is
# where `NO_COLOR`, `FORCE_COLOR` and the tty check all live.
def _formatter(stream: TextIO) -> colorlog.ColoredFormatter:
    return colorlog.ColoredFormatter(
        # WARNING is the widest level we emit; padding keeps the messages aligned.
        "%(log_color)s%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        log_colors=_level_colours(),
        stream=stream,
    )


def _plural(count: Count, noun: Noun) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _counted(
    problems: list[logging.LogRecord], within: Callable[[LogLevel], bool]
) -> Count:
    return Count(
        len(
            Arr(problems)
            .filter(lambda record: within(LogLevel(record.levelno)))
            .to_list()
        )
    )


def _tally(problems: list[logging.LogRecord]) -> Tally:
    counts = (
        Arr(
            [
                (
                    _counted(problems, lambda level: level < logging.ERROR),
                    Noun("warning"),
                ),
                (
                    _counted(problems, lambda level: level >= logging.ERROR),
                    Noun("error"),
                ),
            ]
        )
        .filter(lambda counted: counted[0] > 0)
        .map(lambda counted: _plural(*counted))
        .to_list()
    )
    return Tally(", ".join(counts) if counts else "no warnings or errors")


# A long run scrolls its own detail away, so problems are replayed at the end — errors
# last, where the terminal leaves them in view.
class Summary(logging.Handler):
    def __init__(self, stream: TextIO) -> None:
        super().__init__()
        self.setFormatter(_formatter(stream))
        # The heading takes the colour of the worst problem below it, so a clean run —
        # which has none, and reports at INFO — is the only one that comes out green.
        self._heading = colorlog.ColoredFormatter(
            "%(log_color)s%(message)s",
            log_colors={"INFO": "green", **_level_colours()},
            stream=stream,
        )
        self._seen = Count(0)
        self._problems: list[logging.LogRecord] = []

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self._seen = Count(self._seen + 1)
        if record.levelno >= logging.WARNING:
            self._problems.append(record)

    def report(self) -> Report:
        # A run that logged nothing said nothing worth summarising, which keeps `--help`
        # and usage errors clean.
        if self._seen == 0:
            return Report("")
        ordered = sorted(self._problems, key=lambda record: record.levelno)
        worst = ordered[-1].levelno if ordered else logging.INFO
        heading = self._heading.format(
            logging.LogRecord(
                "documator", worst, "", 0, f"── {_tally(ordered)} ──", None, None
            )
        )
        return Report("\n".join(["", heading, *map(self.format, ordered), ""]))

    def forget(self) -> None:
        self._seen = Count(0)
        self._problems = []


def configure(stream: TextIO) -> Summary:
    console = logging.StreamHandler(stream)
    console.setFormatter(_formatter(stream))
    summary = Summary(stream)
    logging.basicConfig(level=logging.INFO, handlers=[console, summary], force=True)
    return summary


# A watching session has no end of its own, so each pass reports and starts clean.
def drain(stream: TextIO) -> None:
    for handler in logging.getLogger().handlers:
        if isinstance(handler, Summary):
            stream.write(handler.report())
            handler.forget()
