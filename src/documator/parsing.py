import functools
import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import NewType

from iterpy import Arr

from documator.execution import Command
from documator.transclusion import Reference
from documator.variables import VariableName, VariableValue

Markdown = NewType("Markdown", str)
Line = NewType("Line", str)
LineIndex = NewType("LineIndex", int)
TokenIndex = NewType("TokenIndex", int)
Delimiter = NewType("Delimiter", str)
SpanContent = NewType("SpanContent", str)


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


# Carries its source for the same reason a fenced command does.
@dataclass(frozen=True, slots=True)
class ExecutableSpan:
    text: Markdown
    command: Command


@dataclass(frozen=True, slots=True)
class TransclusionBlock:
    reference: Reference


# Carries its source, because a reference that resolves to nothing is reported by
# handing the author back the link they wrote.
@dataclass(frozen=True, slots=True)
class LinkBlock:
    text: Markdown
    reference: Reference


@dataclass(frozen=True, slots=True)
class StructuralErrorBlock:
    text: Markdown
    reason: type[StructuralError]


type Block = (
    PassthroughBlock
    | ExecutableBlock
    | DeclarationBlock
    | ExecutableSpan
    | TransclusionBlock
    | LinkBlock
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
        delimiter = opening_delimiter(lines[index])
        # A delimiter that closes its own bang span on this line is a span, not a fence
        # that happens to never close.
        if delimiter is None or opens_a_bang_span(lines[index]):
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
        return _split_prose(_joined(segment.lines))
    if not segment.closed:
        return [StructuralErrorBlock(_joined(segment.lines), UnterminatedFence)]
    return [_classify(segment.lines)]


@dataclass(frozen=True, slots=True)
class _Span:
    content: SpanContent
    text: Markdown
    after: TokenIndex


# Spans are found before embeds, so a command's content reaches the shell intact.
def _split_prose(prose: Markdown) -> list[Block]:
    return _merged(Arr(_pieces(prose)).map(_piece_to_blocks).flatten().to_list())


# Quoting a span cuts prose at every backtick; merging puts back the runs no other block
# came between, so the block list stays as coarse as the source that produced it.
def _merged(blocks: list[Block]) -> list[Block]:
    return functools.reduce(_absorbed, blocks, [])


def _absorbed(merged: list[Block], block: Block) -> list[Block]:
    previous = merged[-1] if merged else None
    if not isinstance(block, PassthroughBlock) or not isinstance(
        previous, PassthroughBlock
    ):
        return [*merged, block]
    return [*merged[:-1], PassthroughBlock(Markdown(previous.text + block.text))]


# A link is prose documentation writes *about*, so a code span quotes it. An embed is
# not: it keeps splitting inside a span, the way it always has.
class Links(StrEnum):
    RESOLVED = auto()
    QUOTED = auto()


@dataclass(frozen=True, slots=True)
class _Quoted:
    text: Markdown


def _piece_to_blocks(piece: Markdown | ExecutableSpan | _Quoted) -> list[Block]:
    if isinstance(piece, ExecutableSpan):
        return [piece]
    if isinstance(piece, _Quoted):
        return _split_embeds(piece.text, Links.QUOTED)
    return _split_embeds(piece, Links.RESOLVED)


def _pieces(prose: Markdown) -> Iterator[Markdown | ExecutableSpan | _Quoted]:
    tokens = _tokens(prose)
    literal: list[str] = []
    index = TokenIndex(0)
    while index < len(tokens):
        span = _closed_span(tokens, index)
        command = None if span is None else _spanned_command(span.content)
        if span is None:
            literal.append(tokens[index])
            index = TokenIndex(index + 1)
            continue
        if literal:
            yield Markdown("".join(literal))
            literal = []
        yield (
            _Quoted(Markdown(_unescaped(span)))
            if command is None
            else ExecutableSpan(span.text, command)
        )
        index = span.after
    if literal:
        yield Markdown("".join(literal))


# Maximal runs, so a delimiter can be compared to a closing run by equality.
def _tokens(prose: Markdown) -> list[str]:
    return re.findall(r"`+|[^`]+", prose)


def _closed_span(tokens: list[str], opened_at: TokenIndex) -> _Span | None:
    delimiter = tokens[opened_at]
    if not delimiter.startswith("`"):
        return None
    closings = (
        TokenIndex(offset)
        for offset in range(opened_at + 1, len(tokens))
        if tokens[offset] == delimiter
    )
    closed_at = next(closings, None)
    if closed_at is None:
        return None
    content = SpanContent("".join(tokens[opened_at + 1 : closed_at]))
    if "\n" in content:
        return None
    return _Span(
        content,
        Markdown("".join(tokens[opened_at : closed_at + 1])),
        TokenIndex(closed_at + 1),
    )


def _spanned_command(content: SpanContent) -> Command | None:
    # A leading `![[` is the embed sigil, so it stays a transclusion rather than
    # becoming a command that shells out to `[[Note]]`.
    if not _is_bang_span(content) or content.startswith(("!!", "![[")):
        return None
    command = content.removeprefix("!").strip()
    return Command(command) if command else None


def _is_bang_span(content: SpanContent) -> bool:
    return content.startswith("!")


def _unescaped(span: _Span) -> str:
    if not span.content.startswith("!!"):
        return span.text
    # The delimiter is backticks only, so the first bang in the text is the escape.
    return span.text.replace("!", "", 1)


# Scoped to the leading run: a span later on the line is part of a fence's info string,
# and demoting that whole fence to prose would execute its body.
def opens_a_bang_span(line: Line) -> bool:
    span = _closed_span(_tokens(Markdown(line)), TokenIndex(0))
    return span is not None and _is_bang_span(span.content)


# Only prose is split: inside a fence an embed is code being quoted, not a transclusion.
def _split_embeds(prose: Markdown, links: Links) -> list[Block]:
    # The single capture group makes split alternate literal text with each reference.
    parts = (
        Arr(re.split(r"!\[\[([^\[\]\n]*)\]\]", prose))
        .enumerate()
        .filter(lambda part: _is_captured(part) or bool(part[1]))
        .to_list()
    )
    return [block for part in parts for block in _prose_or_embed(part, links)]


def _is_captured(part: tuple[int, str]) -> bool:
    return part[0] % 2 == 1


# Embeds are split first, so what reaches a link is never the tail of an `![[embed]]`.
def _prose_or_embed(part: tuple[int, str], links: Links) -> list[Block]:
    if _is_captured(part):
        return [TransclusionBlock(Reference(part[1]))]
    text = Markdown(part[1])
    if links is Links.QUOTED:
        return [PassthroughBlock(text)]
    return _split_links(text)


def _split_links(prose: Markdown) -> list[Block]:
    return (
        Arr(re.split(r"\[\[([^\[\]\n]*)\]\]", prose))
        .enumerate()
        .filter(lambda part: _is_captured(part) or bool(part[1]))
        .map(_prose_or_link)
        .to_list()
    )


def _prose_or_link(part: tuple[int, str]) -> Block:
    if _is_captured(part):
        return LinkBlock(Markdown(f"[[{part[1]}]]"), Reference(part[1]))
    return PassthroughBlock(Markdown(part[1]))


def opening_delimiter(line: Line) -> Delimiter | None:
    opening = re.match(r"^(?P<delimiter>`{3,}|~{3,})", line)
    return None if opening is None else Delimiter(opening["delimiter"])


def _index_after_fence(
    lines: list[Line], opened_at: LineIndex, delimiter: Delimiter
) -> LineIndex | None:
    closings = (
        LineIndex(offset + 1)
        for offset, line in enumerate(lines)
        if offset > opened_at and closes(line, delimiter)
    )
    return next(closings, None)


def closes(line: Line, delimiter: Delimiter) -> bool:
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
