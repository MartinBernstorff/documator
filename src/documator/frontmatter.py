import re
from dataclasses import dataclass
from typing import NewType

from iterpy import Arr

from documator.parsing import Markdown

SkillName = NewType("SkillName", str)
DeclaredLine = NewType("DeclaredLine", str)

_BLOCK = re.compile(
    r"---[ \t]*\n(?P<declared>.*?)^---[ \t]*(?:\n|\Z)", re.DOTALL | re.MULTILINE
)


# Declared keys are kept as raw lines: the loader is the authority on their shape, so
# nothing here needs to understand YAML beyond spotting which key a line opens.
@dataclass(frozen=True, slots=True)
class Template:
    declared: tuple[DeclaredLine, ...]
    body: Markdown


# The preamble is kept verbatim rather than re-emitted from the declared lines, so a
# passthrough render hands back the exact bytes the author wrote.
@dataclass(frozen=True, slots=True)
class Partition:
    preamble: Markdown
    body: Markdown


def partition(source: Markdown) -> Partition:
    block = _BLOCK.match(source)
    if block is None:
        return Partition(Markdown(""), source)
    return Partition(Markdown(source[: block.end()]), Markdown(source[block.end() :]))


def split(source: Markdown) -> Template:
    block = _BLOCK.match(source)
    if block is None:
        return Template((), source)
    declared = Arr(block["declared"].splitlines()).map(DeclaredLine).to_list()
    return Template(tuple(declared), Markdown(source[block.end() :]))


def declares_name(declared: tuple[DeclaredLine, ...]) -> bool:
    return Arr(declared).any(lambda line: _opens(line, "name"))


# A present key is intent to fill it, so quotes around nothing count as empty too.
def declares_empty_description(declared: tuple[DeclaredLine, ...]) -> bool:
    return Arr(declared).any(
        lambda line: (
            re.fullmatch(
                r"""description[ \t]*:[ \t]*('[ \t]*'|"[ \t]*")?[ \t]*""", line
            )
            is not None
        )
    )


def compose(
    name: SkillName, declared: tuple[DeclaredLine, ...], body: Markdown
) -> Markdown:
    described = (
        list(declared)
        if Arr(declared).any(lambda line: _opens(line, "description"))
        else [DeclaredLine(f"description: {name}"), *declared]
    )
    lines = Arr([DeclaredLine(f"name: {name}"), *described]).map(
        lambda line: line + "\n"
    )
    return Markdown(f"---\n{''.join(lines)}---\n{body}")


def _opens(line: DeclaredLine, key: str) -> bool:
    return re.match(rf"{key}[ \t]*:", line) is not None
