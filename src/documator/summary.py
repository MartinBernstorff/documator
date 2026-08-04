import logging
from dataclasses import dataclass
from typing import NewType, Protocol

from iterpy import Arr

log = logging.getLogger("documator")

Count = NewType("Count", int)
Produced = NewType("Produced", int)
Noun = NewType("Noun", str)


# Everything the summary replays was already logged once where it arose, so a problem
# only has to render itself the same way twice.
class Reportable(Protocol):
    def __str__(self) -> str: ...


# Severity is the wrapper rather than a field, so a caller cannot build a problem
# without deciding how loudly it speaks.
@dataclass(frozen=True, slots=True)
class Warned:
    problem: Reportable

    def level(self) -> int:
        return logging.WARNING

    def __str__(self) -> str:
        return str(self.problem)


@dataclass(frozen=True, slots=True)
class Errored:
    problem: Reportable

    def level(self) -> int:
        return logging.ERROR

    def __str__(self) -> str:
        return str(self.problem)


type Problem = Warned | Errored


@dataclass(frozen=True, slots=True)
class Tally:
    count: Count
    noun: Noun

    def __str__(self) -> str:
        return f"{self.count} {self.noun}{'' if self.count == 1 else 's'}"


def summarise(produced: Produced, problems: list[Problem]) -> None:
    warnings = Arr(problems).filter(lambda p: isinstance(p, Warned)).to_list()
    errors = Arr(problems).filter(lambda p: isinstance(p, Errored)).to_list()
    # WARNING sorts below ERROR numerically, so the count inherits the worst thing it
    # counts and survives exactly as long as the problems it is describing.
    log.log(
        max((problem.level() for problem in problems), default=logging.INFO),
        "%s, %s, %s",
        Tally(Count(produced), Noun("file")),
        Tally(Count(len(warnings)), Noun("warning")),
        Tally(Count(len(errors)), Noun("error")),
    )
    # Warnings first and errors last, in discovery order, so the summary reads in the
    # same sequence as the lines it is summarising and the worst news ends up nearest
    # the prompt.
    for problem in [*warnings, *errors]:
        log.log(problem.level(), "%s", problem)
