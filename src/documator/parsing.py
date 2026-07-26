import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import NewType

from iterpy import Arr

from documator.execution import Command

Markdown = NewType("Markdown", str)
Line = NewType("Line", str)
LineIndex = NewType("LineIndex", int)
Delimiter = NewType("Delimiter", str)


class StructuralError(ValueError):
    message: str

    def __init__(self) -> None:
        super().__init__(self.message)


class MultipleCommands(StructuralError):
    message = "more than one command line in a single block"


class CommandWithOtherContent(StructuralError):
    message = "a command line alongside other content"


class UnterminatedFence(StructuralError):
    message = "fenced block is never closed"


@dataclass(frozen=True, slots=True)
class PassthroughBlock:
    text: Markdown


@dataclass(frozen=True, slots=True)
class ExecutableBlock:
    command: Command


@dataclass(frozen=True, slots=True)
class StructuralErrorBlock:
    text: Markdown
    reason: type[StructuralError]


type Block = PassthroughBlock | ExecutableBlock | StructuralErrorBlock


@dataclass(frozen=True, slots=True)
class _Prose:
    lines: list[Line]


@dataclass(frozen=True, slots=True)
class _Fence:
    lines: list[Line]
    closed: bool


type _Segment = _Prose | _Fence


def parse(source: Markdown) -> list[Block]:
    lines = [Line(line) for line in source.splitlines(keepends=True)]
    return Arr(_segments(lines)).map(_to_block).to_list()


def _segments(lines: list[Line]) -> Iterator[_Segment]:
    prose: list[Line] = []
    index = LineIndex(0)
    while index < len(lines):
        delimiter = _opening_delimiter(lines[index])
        if delimiter is None:
            prose.append(lines[index])
            index = LineIndex(index + 1)
            continue
        if prose:
            yield _Prose(prose)
            prose = []
        close = _index_after_fence(lines, index, delimiter)
        end = LineIndex(len(lines)) if close is None else close
        yield _Fence(lines[index:end], closed=close is not None)
        index = end
    if prose:
        yield _Prose(prose)


def _to_block(segment: _Segment) -> Block:
    if isinstance(segment, _Prose):
        return PassthroughBlock(_joined(segment.lines))
    if not segment.closed:
        return StructuralErrorBlock(_joined(segment.lines), UnterminatedFence)
    return _classify(segment.lines)


def _opening_delimiter(line: Line) -> Delimiter | None:
    opening = re.match(r"^(?P<delimiter>`{3,}|~{3,})", line)
    return None if opening is None else Delimiter(opening["delimiter"])


def _index_after_fence(
    lines: list[Line], opened_at: LineIndex, delimiter: Delimiter
) -> LineIndex | None:
    closings = (
        LineIndex(offset + 1)
        for offset, line in enumerate(lines)
        if offset > opened_at and _closes(line, delimiter)
    )
    return next(closings, None)


def _closes(line: Line, delimiter: Delimiter) -> bool:
    candidate = line.rstrip()
    return len(candidate) >= len(delimiter) and candidate == delimiter[0] * len(
        candidate
    )


def _classify(fence: list[Line]) -> Block:
    content = Arr(fence[1:-1])
    commands = content.filter(_is_command).to_list()
    if not commands:
        return PassthroughBlock(
            _joined([fence[0], *content.map(_unescape).to_list(), fence[-1]])
        )
    if len(commands) > 1:
        return StructuralErrorBlock(_joined(fence), MultipleCommands)
    if content.filter(lambda line: bool(line.strip())).len() > 1:
        return StructuralErrorBlock(_joined(fence), CommandWithOtherContent)
    return ExecutableBlock(Command(commands[0].removeprefix("!").strip()))


def _joined(lines: list[Line]) -> Markdown:
    return Markdown("".join(lines))


def _is_command(line: Line) -> bool:
    return line.startswith("!") and not line.startswith("!!")


def _unescape(line: Line) -> Line:
    return Line(line.removeprefix("!")) if line.startswith("!!") else line
