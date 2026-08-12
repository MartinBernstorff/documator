import re
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import dropwhile
from typing import NewType

from iterpy import Arr

from documator.frontmatter import partition
from documator.parsing import (
    Delimiter,
    Line,
    LineIndex,
    Markdown,
    closes,
    opening_delimiter,
    opens_a_bang_span,
)
from documator.transclusion import (
    AmbiguousSection,
    HeadingText,
    NoSection,
    SectionFailure,
    Target,
)

HeadingLevel = NewType("HeadingLevel", int)


@dataclass(frozen=True, slots=True)
class _Heading:
    level: HeadingLevel
    text: HeadingText
    at: LineIndex


@dataclass(frozen=True, slots=True)
class _Prose:
    line: Line
    at: LineIndex


# Inside a fence a `#` is code being quoted, so a section documenting shell comments
# neither truncates itself nor lends out half an open fence.
def _scanned(lines: list[Line]) -> Iterator[_Heading]:
    fence: Delimiter | None = None
    above: _Prose | None = None
    for offset, line in enumerate(lines):
        at = LineIndex(offset)
        if fence is not None:
            fence = None if closes(line, fence) else fence
            above = None
            continue
        opening = opening_delimiter(line)
        if opening is not None and not opens_a_bang_span(line):
            fence = opening
            above = None
            continue
        found = _heading(at, line) or _underlined(above, line)
        if found is not None:
            yield found
        above = _Prose(line, at)


def _heading(at: LineIndex, line: Line) -> _Heading | None:
    opened = re.match(
        r"(?P<hashes>#{1,6})(?:[ \t]+(?P<text>.*?))?[ \t]*$", line.strip()
    )
    if opened is None:
        return None
    level = HeadingLevel(len(opened["hashes"]))
    return _Heading(level, _closed(Line(opened["text"] or "")), at)


# The heading is the line above its rule, so the section it opens starts there and takes
# the underline with it. A rule under nothing — a blank line, a fence, the note's own
# opening `---` — is a thematic break rather than a heading.
def _underlined(above: _Prose | None, line: Line) -> _Heading | None:
    rule = re.fullmatch(r"(?P<mark>=+|-+)[ \t]*", line.strip())
    if above is None or rule is None:
        return None
    if not above.line.strip() or _heading(above.at, above.line) is not None:
        return None
    level = HeadingLevel(1 if rule["mark"].startswith("=") else 2)
    return _Heading(level, _closed(above.line), above.at)


# A closed ATX heading names the same section as an open one, so the trailing run goes.
def _closed(text: Line) -> HeadingText:
    return HeadingText(re.sub(r"[ \t]+#+$", "", text.strip()))


def section(source: Markdown, target: Target) -> Markdown | SectionFailure:
    lines = _lines(partition(source).body)
    headings = list(_scanned(lines))
    reached = _walk(headings, target, LineIndex(len(lines)))
    if not isinstance(reached, _Extent):
        return reached
    return _trimmed(_kept(lines, headings, reached))


# A note's own body is its whole-note extent, so the same rule drops its marked
# sections. A body carrying none is handed back byte for byte, since trimming a note
# that asked for nothing would rewrite the trailing air of every note in the vault.
def emitted(body: Markdown) -> Markdown:
    lines = _lines(body)
    whole = _Extent(LineIndex(0), LineIndex(len(lines)), HeadingLevel(0))
    kept = _kept(lines, list(_scanned(lines)), whole)
    return body if kept == lines else _trimmed(kept)


def _lines(body: Markdown) -> list[Line]:
    return [Line(line) for line in body.splitlines(keepends=True)]


@dataclass(frozen=True, slots=True)
class _Extent:
    start: LineIndex
    end: LineIndex
    depth: HeadingLevel


# The path walked so far travels with the extent, so a miss can name what it
# looked under.
@dataclass(frozen=True, slots=True)
class _Reached:
    extent: _Extent
    searched: Target


def _walk(
    headings: list[_Heading], target: Target, total: LineIndex
) -> _Extent | SectionFailure:
    reached = _Reached(
        _Extent(LineIndex(0), total, HeadingLevel(0)), Target.whole(target.note)
    )
    for wanted in target.path:
        stepped = _step(headings, reached, wanted)
        if not isinstance(stepped, _Reached):
            return stepped
        reached = stepped
    return reached.extent


def _step(
    headings: list[_Heading], reached: _Reached, wanted: HeadingText
) -> _Reached | SectionFailure:
    inside = _nested(headings, reached.extent)
    matches = Arr(inside).filter(lambda heading: heading.text == wanted).to_list()
    if not matches:
        available = tuple(heading.text for heading in inside)
        return NoSection(reached.searched, wanted, available)
    if len(matches) > 1:
        return AmbiguousSection(reached.searched, wanted)
    found = matches[0]
    return _Reached(
        _Extent(found.at, _end(headings, found, reached.extent.end), found.level),
        reached.searched.into(found.text),
    )


# Only a heading nested deeper than its parent can be that parent's subsection.
def _nested(headings: list[_Heading], extent: _Extent) -> list[_Heading]:
    return (
        Arr(headings)
        .filter(lambda heading: extent.start <= heading.at < extent.end)
        .filter(lambda heading: heading.level > extent.depth)
        .to_list()
    )


def _end(headings: list[_Heading], found: _Heading, limit: LineIndex) -> LineIndex:
    following = (
        Arr(headings)
        .filter(lambda heading: found.at < heading.at < limit)
        .filter(lambda heading: heading.level <= found.level)
        .to_list()
    )
    return following[0].at if following else limit


# A `_`-marked heading is scratch the author keeps beside the work, so the section it
# opens emits nothing. Only sections nested *inside* the extent go: an extent's own root
# is not nested in itself, so an embed naming a marked section directly still gets it.
# Read off the authored text rather than the match key, which strips `_` as emphasis.
def _kept(lines: list[Line], headings: list[_Heading], extent: _Extent) -> list[Line]:
    dropped = (
        Arr(_nested(headings, extent))
        .filter(lambda heading: heading.text.root.startswith("_"))
        .map(lambda heading: range(heading.at, _end(headings, heading, extent.end)))
        .to_list()
    )
    return [
        lines[at]
        for at in range(extent.start, extent.end)
        if not any(at in span for span in dropped)
    ]


# Trailing air belongs to whatever followed the section in its own note, not the
# host. The last line keeps its own trailing spaces: two of them are a hard break.
def _trimmed(lines: list[Line]) -> Markdown:
    kept = dropwhile(lambda line: not line.strip(), reversed(lines))
    return Markdown("".join(reversed(list(kept))).rstrip("\r\n") + "\n")
