import re
from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

from documator.execution import Command

Markdown = NewType("Markdown", str)
Line = NewType("Line", str)
LineIndex = NewType("LineIndex", int)
Delimiter = NewType("Delimiter", str)

_FENCE = re.compile(r"^(?P<delimiter>`{3,}|~{3,})")
_BANG = "!"
_ESCAPED_BANG = "!!"


class StructuralError(StrEnum):
    MULTIPLE_COMMANDS = "more than one command line in a single block"
    COMMAND_WITH_OTHER_CONTENT = "a command line alongside other content"
    UNTERMINATED_FENCE = "fenced block is never closed"


@dataclass(frozen=True, slots=True)
class PassthroughBlock:
    text: Markdown


@dataclass(frozen=True, slots=True)
class ExecutableBlock:
    command: Command


@dataclass(frozen=True, slots=True)
class StructuralErrorBlock:
    text: Markdown
    reason: StructuralError


type Block = PassthroughBlock | ExecutableBlock | StructuralErrorBlock


def parse(source: Markdown) -> list[Block]:
    lines = [Line(line) for line in source.splitlines(keepends=True)]
    blocks: list[Block] = []
    prose: list[Line] = []
    index = LineIndex(0)
    while index < len(lines):
        opening = _FENCE.match(lines[index])
        if opening is None:
            prose.append(lines[index])
            index = LineIndex(index + 1)
            continue
        if prose:
            blocks.append(PassthroughBlock(_joined(prose)))
            prose = []
        close = _index_after_fence(lines, index, Delimiter(opening["delimiter"]))
        end = LineIndex(len(lines)) if close is None else close
        fence = lines[index:end]
        blocks.append(
            _structural_error(fence, StructuralError.UNTERMINATED_FENCE)
            if close is None
            else _classify(fence)
        )
        index = end
    if prose:
        blocks.append(PassthroughBlock(_joined(prose)))
    return blocks


def _index_after_fence(
    lines: list[Line], opened_at: LineIndex, delimiter: Delimiter
) -> LineIndex | None:
    char = delimiter[0]
    for offset in range(opened_at + 1, len(lines)):
        candidate = lines[offset].rstrip()
        if len(candidate) >= len(delimiter) and candidate == char * len(candidate):
            return LineIndex(offset + 1)
    return None


def _classify(fence: list[Line]) -> Block:
    content = fence[1:-1]
    commands = [line for line in content if _is_command(line)]
    if not commands:
        return PassthroughBlock(
            _joined([fence[0], *map(_unescape, content), fence[-1]])
        )
    if len(commands) > 1:
        return _structural_error(fence, StructuralError.MULTIPLE_COMMANDS)
    if len([line for line in content if line.strip()]) > 1:
        return _structural_error(fence, StructuralError.COMMAND_WITH_OTHER_CONTENT)
    return ExecutableBlock(Command(commands[0].removeprefix(_BANG).strip()))


def _structural_error(
    fence: list[Line], reason: StructuralError
) -> StructuralErrorBlock:
    return StructuralErrorBlock(_joined(fence), reason)


def _joined(lines: list[Line]) -> Markdown:
    return Markdown("".join(lines))


def _is_command(line: Line) -> bool:
    return line.startswith(_BANG) and not line.startswith(_ESCAPED_BANG)


def _unescape(line: Line) -> Line:
    return Line(line.removeprefix(_BANG)) if line.startswith(_ESCAPED_BANG) else line
