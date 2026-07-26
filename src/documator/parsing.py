import re
from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

from documator.execution import Command

Markdown = NewType("Markdown", str)

_FENCE = re.compile(r"^(?P<delimiter>`{3,}|~{3,})(?P<info>.*)$")
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
    lines = source.splitlines(keepends=True)
    blocks: list[Block] = []
    prose: list[str] = []
    index = 0
    while index < len(lines):
        opening = _FENCE.match(lines[index].rstrip("\n"))
        if opening is None:
            prose.append(lines[index])
            index += 1
            continue
        if prose:
            blocks.append(PassthroughBlock(Markdown("".join(prose))))
            prose = []
        close = _close_of(lines, index, opening["delimiter"])
        end = len(lines) if close is None else close
        fence = lines[index:end]
        blocks.append(
            StructuralErrorBlock(
                Markdown("".join(fence)), StructuralError.UNTERMINATED_FENCE
            )
            if close is None
            else _classify(fence)
        )
        index = end
    if prose:
        blocks.append(PassthroughBlock(Markdown("".join(prose))))
    return blocks


def _close_of(lines: list[str], opened_at: int, delimiter: str) -> int | None:
    char = delimiter[0]
    for offset in range(opened_at + 1, len(lines)):
        candidate = lines[offset].rstrip()
        if len(candidate) >= len(delimiter) and candidate == char * len(candidate):
            return offset + 1
    return None


def _classify(fence: list[str]) -> Block:
    content = fence[1:-1]
    commands = [line for line in content if _is_command(line)]
    if not commands:
        return PassthroughBlock(
            Markdown("".join([fence[0], *map(_unescape, content), fence[-1]]))
        )
    if len(commands) > 1:
        return StructuralErrorBlock(
            Markdown("".join(fence)), StructuralError.MULTIPLE_COMMANDS
        )
    if len([line for line in content if line.strip()]) > 1:
        return StructuralErrorBlock(
            Markdown("".join(fence)), StructuralError.COMMAND_WITH_OTHER_CONTENT
        )
    return ExecutableBlock(Command(commands[0].removeprefix(_BANG).strip()))


def _is_command(line: str) -> bool:
    return line.startswith(_BANG) and not line.startswith(_ESCAPED_BANG)


def _unescape(line: str) -> str:
    return line.removeprefix(_BANG) if line.startswith(_ESCAPED_BANG) else line
