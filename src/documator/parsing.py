import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import NewType

from iterpy import Arr

from documator.execution import Command
from documator.transclusion import Reference
from documator.variables import VariableName, VariableValue

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


class DeclarationWithoutValue(StructuralError):
    message = "variable declaration has no value"


@dataclass(frozen=True, slots=True)
class PassthroughBlock:
    text: Markdown


# A block that can fail keeps its source, because the failure is reported by handing the
# author back what they wrote.
@dataclass(frozen=True, slots=True)
class ExecutableBlock:
    text: Markdown
    command: Command


@dataclass(frozen=True, slots=True)
class DeclarationBlock:
    text: Markdown
    name: VariableName
    value: VariableValue


@dataclass(frozen=True, slots=True)
class TransclusionBlock:
    reference: Reference


@dataclass(frozen=True, slots=True)
class StructuralErrorBlock:
    text: Markdown
    reason: type[StructuralError]


type Block = (
    PassthroughBlock
    | ExecutableBlock
    | DeclarationBlock
    | TransclusionBlock
    | StructuralErrorBlock
)


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
    return Arr(_segments(lines)).map(_to_blocks).flatten().to_list()


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


def _to_blocks(segment: _Segment) -> list[Block]:
    if isinstance(segment, _Prose):
        return _split_embeds(_joined(segment.lines))
    if not segment.closed:
        return [StructuralErrorBlock(_joined(segment.lines), UnterminatedFence)]
    return [_classify(segment.lines)]


# Only prose is split: inside a fence an embed is code being quoted, not a transclusion.
def _split_embeds(prose: Markdown) -> list[Block]:
    # The single capture group makes split alternate literal text with each reference.
    return (
        Arr(re.split(r"!\[\[([^\[\]\n]*)\]\]", prose))
        .enumerate()
        .filter(lambda part: _is_embed(part) or bool(part[1]))
        .map(_prose_or_embed)
        .to_list()
    )


def _is_embed(part: tuple[int, str]) -> bool:
    return part[0] % 2 == 1


def _prose_or_embed(part: tuple[int, str]) -> Block:
    if _is_embed(part):
        return TransclusionBlock(Reference(part[1]))
    return PassthroughBlock(Markdown(part[1]))


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
    return _command_or_declaration(
        _joined(fence), commands[0].removeprefix("!").strip()
    )


# Only an `=` marks a declaration, so `var` stays available as a command of its own.
def _command_or_declaration(text: Markdown, command: str) -> Block:
    declaration = re.match(
        r"var\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=(?P<value>.*)$", command
    )
    if declaration is None:
        return ExecutableBlock(text, Command(command))
    value = declaration["value"].strip()
    if not value:
        return StructuralErrorBlock(text, DeclarationWithoutValue)
    return DeclarationBlock(
        text, VariableName(declaration["name"]), VariableValue(value)
    )


def _joined(lines: list[Line]) -> Markdown:
    return Markdown("".join(lines))


def _is_command(line: Line) -> bool:
    return line.startswith("!") and not line.startswith("!!")


def _unescape(line: Line) -> Line:
    return Line(line.removeprefix("!")) if line.startswith("!!") else line
